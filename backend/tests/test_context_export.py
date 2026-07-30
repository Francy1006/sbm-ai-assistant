import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile

from fastapi import FastAPI
from fastapi.testclient import TestClient
from qdrant_client.models import Distance

from app.api.routes.contexts import router
from app.schemas.contexts import ContextExportRequest
from app.services.contexts.context_export_service import export_contexts
from app.services.contexts.context_index_service import index_context_source
from app.services.contexts.context_retrieval_service import (
    retrieve_relevant_context_chunks,
)
from app.services.contexts.file_discovery_service import (
    ContextValidationError,
    validate_export_paths,
)
from app.services.contexts.markdown_chunk_service import (
    split_markdown_into_chunks,
)
from app.services.contexts.models import (
    ContextSource,
    RetrievedContextChunk,
)
from app.services.qdrant_service import create_collection, scroll_all_points


GLOBAL_SOURCE_FILES = (
    ("context/PROJECT_CONTEXT.md", "context/PROJECT_CONTEXT.md"),
    ("context/README.md", "context/README.md"),
    ("context/SUITE_CONTEXT.md", "context/SUITE_CONTEXT.md"),
    ("context/BUSINESS_CONTEXT.md", "context/BUSINESS_CONTEXT.md"),
    ("context/QA_CONTEXT.md", "context/QA_CONTEXT.md"),
    ("context/SYS_PROMPT.md", "context/SYS_PROMPT.md"),
    ("context/FORMAT_CONTEXT.md", "context/FORMAT_CONTEXT.md"),
)

PROJECT_FILES = (
    "README.md",
    "context/PROJECT_CONTEXT.md",
    "context/QA_CONTEXT.md",
    "context/DEPLOY_CONTEXT.md",
)


def _write_markdown(path: Path, title: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {title}\n\nContenido de prueba.", encoding="utf-8")


class ContextExportEndpointTests(unittest.TestCase):
    def test_endpoint_exports_only_allowlisted_files_and_manifest(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            suite_root = Path(temporary_directory) / "SBM-SUITE"
            project_root = suite_root / "DP-API"
            output_directory = suite_root / "context" / "output"
            output_directory.mkdir(parents=True)

            with ZipFile(
                output_directory / "context-package.zip",
                mode="w",
            ) as stale_archive:
                stale_archive.writestr(
                    "SBM-SUITE/PROJECT_CONTEXT.md",
                    "stale",
                )
                stale_archive.writestr(
                    "SBM-SUITE/README.md",
                    "stale",
                )

            for source_path, archive_path in GLOBAL_SOURCE_FILES:
                _write_markdown(suite_root / source_path, archive_path)

            for relative_path in PROJECT_FILES:
                _write_markdown(project_root / relative_path, relative_path)

            _write_markdown(project_root / "src/secret.py", "not exported")
            (project_root / ".env").write_text(
                "SECRET=not-exported",
                encoding="utf-8",
            )

            app = FastAPI()
            app.include_router(router)
            indexed_sources = []
            request_body = {
                "project_name": "dp-api",
                "workflow": "context-deploy",
                "project_root": str(project_root),
                "source_context_root": str(suite_root),
                "format_context_path": str(
                    suite_root / "context/FORMAT_CONTEXT.md"
                ),
                "output_directory": str(output_directory),
                "change_summary": "Actualizar exportación RAG.",
                "changed_files": ["backend/app/export.py"],
                "git_diff": "diff --git a/export.py b/export.py",
                "qa_results": "Pruebas focalizadas: OK.",
            }
            retrieved_chunks = [
                RetrievedContextChunk(
                    point_id="global-1",
                    source_path=str(
                        suite_root / "context/SUITE_CONTEXT.md"
                    ),
                    archive_path=(
                        "SBM-SUITE/context/SUITE_CONTEXT.md"
                    ),
                    section="Arquitectura",
                    score=0.95,
                    content="Contexto global recuperado.",
                ),
                RetrievedContextChunk(
                    point_id="project-1",
                    source_path=str(
                        project_root / "context/PROJECT_CONTEXT.md"
                    ),
                    archive_path=(
                        "SBM-SUITE/dp-api/context/"
                        "PROJECT_CONTEXT.md"
                    ),
                    section="Deploy",
                    score=0.91,
                    content="Contexto de proyecto recuperado.",
                ),
            ]

            def fake_index(**kwargs):
                indexed_sources.append(kwargs["source"])
                return len(kwargs["chunks"])

            with (
                patch(
                    "app.services.contexts.context_export_service."
                    "index_context_source",
                    side_effect=fake_index,
                ),
                patch(
                    "app.services.contexts.context_export_service."
                    "retrieve_relevant_context_chunks",
                    return_value=retrieved_chunks,
                ),
                patch(
                    "app.services.contexts.context_export_service."
                    "_collect_git_log",
                    return_value="abc123 Cambio",
                ),
            ):
                response = TestClient(app).post(
                    "/contexts/export",
                    json=request_body,
                )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["status"], "completed")
            self.assertEqual(payload["indexed_source_count"], 11)
            self.assertEqual(payload["collection_name"], "sbm_contexts")
            self.assertEqual(payload["errors"], [])
            self.assertTrue(
                all(
                    source.source_path.is_absolute()
                    and source.source_path.is_relative_to(
                        suite_root.resolve()
                    )
                    for source in indexed_sources
                )
            )
            self.assertTrue(
                all(
                    source.archive_path.startswith("SBM-SUITE/")
                    for source in indexed_sources
                )
            )
            global_mappings = {
                source.archive_path: source.source_path.relative_to(
                    suite_root.resolve()
                ).as_posix()
                for source in indexed_sources
                if source.repository == "SBM-SUITE"
            }
            self.assertEqual(
                global_mappings,
                {
                    f"SBM-SUITE/{archive_path}": source_path
                    for source_path, archive_path in GLOBAL_SOURCE_FILES
                },
            )

            with ZipFile(payload["context_zip_path"]) as archive:
                names = set(archive.namelist())
                expected_names = {
                    "retrieved-context.md",
                    "change-summary.md",
                    "changed-files.txt",
                    "git-diff.patch",
                    "git-log.txt",
                    "qa-results.md",
                    "FORMAT_CONTEXT.md",
                    "manifest.json",
                    "SBM-SUITE/PROJECT_CONTEXT.md",
                    "SBM-SUITE/README.md",
                    "SBM-SUITE/context/SUITE_CONTEXT.md",
                    (
                        "SBM-SUITE/dp-api/context/"
                        "PROJECT_CONTEXT.md"
                    ),
                    "SBM-SUITE/dp-api/README.md",
                }
                self.assertEqual(names, expected_names)
                self.assertNotIn("SBM-SUITE/dp-api/.env", names)
                self.assertNotIn("SBM-SUITE/dp-api/src/secret.py", names)
                protected_full_contexts = {
                    "SBM-SUITE/context/BUSINESS_CONTEXT.md",
                    "SBM-SUITE/context/QA_CONTEXT.md",
                    "SBM-SUITE/context/SYS_PROMPT.md",
                    "SBM-SUITE/dp-api/context/QA_CONTEXT.md",
                    (
                        "SBM-SUITE/dp-api/context/"
                        "DEPLOY_CONTEXT.md"
                    ),
                }
                self.assertTrue(
                    protected_full_contexts.isdisjoint(names)
                )
                self.assertNotEqual(
                    archive.read("SBM-SUITE/PROJECT_CONTEXT.md"),
                    b"stale",
                )

                manifest = json.loads(archive.read("manifest.json"))
                self.assertEqual(manifest["project_name"], "dp-api")
                self.assertEqual(manifest["execution_mode"], "evidence")
                self.assertFalse(manifest["has_user_prompt"])
                self.assertEqual(manifest["chunk_count"], 2)
                self.assertEqual(
                    manifest["retrieved_chunk_count"],
                    2,
                )
                self.assertEqual(
                    manifest["collection_name"],
                    "sbm_contexts",
                )
                self.assertEqual(
                    manifest["top_k"],
                    8,
                )
                self.assertIn(
                    "Actualizar exportación RAG.",
                    manifest["query"],
                )
                self.assertIn(
                    "backend/app/export.py",
                    manifest["query"],
                )
                self.assertIn(
                    "diff --git a/export.py b/export.py",
                    manifest["query"],
                )
                self.assertIn(
                    "Pruebas focalizadas: OK.",
                    manifest["query"],
                )
                self.assertEqual(
                    manifest["embedding_model"],
                    "intfloat/multilingual-e5-large",
                )
                self.assertEqual(
                    manifest["filters_applied"],
                    {
                        "project_name": "dp-api",
                        "workflow": "context-deploy",
                        "is_active": True,
                        "global_repository": "SBM-SUITE",
                        "project_repository": "not SBM-SUITE",
                    },
                )
                self.assertEqual(
                    {
                        source["archive_path"]
                        for source in manifest["retrieved_sources"]
                    },
                    {
                        "SBM-SUITE/context/SUITE_CONTEXT.md",
                        (
                            "SBM-SUITE/dp-api/context/"
                            "PROJECT_CONTEXT.md"
                        ),
                    },
                )
                expected_full_contexts = {
                    "FORMAT_CONTEXT.md",
                    "SBM-SUITE/PROJECT_CONTEXT.md",
                    "SBM-SUITE/README.md",
                    "SBM-SUITE/context/SUITE_CONTEXT.md",
                    (
                        "SBM-SUITE/dp-api/context/"
                        "PROJECT_CONTEXT.md"
                    ),
                    "SBM-SUITE/dp-api/README.md",
                }
                self.assertEqual(
                    {
                        context_file["archive_path"]
                        for context_file in (
                            manifest["full_context_files"]
                        )
                    },
                    expected_full_contexts,
                )
                self.assertEqual(
                    manifest["missing_full_context_files"],
                    [],
                )
                self.assertEqual(
                    set(manifest["content_hashes"]),
                    expected_full_contexts,
                )

                for archive_path, expected_hash in (
                    manifest["content_hashes"].items()
                ):
                    self.assertEqual(
                        expected_hash,
                        hashlib.sha256(
                            archive.read(archive_path)
                        ).hexdigest(),
                    )
                retrieved_context = archive.read(
                    "retrieved-context.md"
                ).decode("utf-8")
                self.assertIn(
                    "SBM-SUITE/context/SUITE_CONTEXT.md",
                    retrieved_context,
                )
                self.assertIn(
                    "Contexto global recuperado.",
                    retrieved_context,
                )
                self.assertIn("Score: 0.950000", retrieved_context)

    def test_endpoint_exports_optional_user_prompt(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            suite_root = Path(temporary_directory) / "SBM-SUITE"
            project_root = suite_root / "DP-API"
            output_directory = suite_root / "context" / "output"
            output_directory.mkdir(parents=True)

            for source_path, archive_path in GLOBAL_SOURCE_FILES:
                _write_markdown(suite_root / source_path, archive_path)

            for relative_path in PROJECT_FILES:
                _write_markdown(project_root / relative_path, relative_path)

            request = ContextExportRequest(
                project_name="dp-api",
                workflow="context-deploy",
                execution_mode="user-guided",
                user_prompt="Planificar integración asincrónica.",
                project_root=str(project_root),
                source_context_root=str(suite_root),
                format_context_path=str(
                    suite_root / "context/FORMAT_CONTEXT.md"
                ),
                output_directory=str(output_directory),
                change_summary="Sin cambios implementados.",
                changed_files=[],
                git_diff="",
                qa_results="",
            )

            with (
                patch(
                    "app.services.contexts.context_export_service."
                    "index_context_source",
                    side_effect=lambda **kwargs: len(kwargs["chunks"]),
                ),
                patch(
                    "app.services.contexts.context_export_service."
                    "retrieve_relevant_context_chunks",
                    return_value=[],
                ),
                patch(
                    "app.services.contexts.context_export_service."
                    "_collect_git_log",
                    return_value="",
                ),
            ):
                response = export_contexts(request)

            with ZipFile(response.context_zip_path) as archive:
                names = set(archive.namelist())
                self.assertIn("USER_PROMPT.md", names)
                self.assertEqual(
                    archive.read("USER_PROMPT.md").decode("utf-8"),
                    "Planificar integración asincrónica.\n",
                )
                manifest = json.loads(archive.read("manifest.json"))
                self.assertEqual(
                    manifest["execution_mode"],
                    "user-guided",
                )
                self.assertTrue(manifest["has_user_prompt"])
                self.assertIn(
                    "Planificar integración asincrónica.",
                    manifest["query"],
                )

    def test_endpoint_rejects_wrong_workflow(self):
        app = FastAPI()
        app.include_router(router)
        response = TestClient(app).post(
            "/contexts/export",
            json={
                "project_name": "dp-api",
                "workflow": "other",
                "project_root": "/tmp/project",
                "source_context_root": "/tmp",
                "format_context_path": "/tmp/context/FORMAT_CONTEXT.md",
                "output_directory": "/tmp/output",
            },
        )

        self.assertEqual(response.status_code, 422)


class ContextPathValidationTests(unittest.TestCase):
    def test_rejects_project_outside_source_root(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            suite_root = base / "suite"
            project_root = base / "outside"
            suite_root.mkdir()
            project_root.mkdir()

            with self.assertRaises(ContextValidationError):
                validate_export_paths(
                    project_name="dp-api",
                    project_root=str(project_root),
                    source_context_root=str(suite_root),
                    format_context_path=str(
                        suite_root / "context/FORMAT_CONTEXT.md"
                    ),
                    output_directory=str(base / "output"),
                )

    def test_rejects_path_traversal_and_unsafe_project_name(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            suite_root = base / "suite"
            project_root = suite_root / "project"
            project_root.mkdir(parents=True)

            with self.assertRaises(ContextValidationError):
                validate_export_paths(
                    project_name="../dp-api",
                    project_root=str(project_root),
                    source_context_root=str(suite_root),
                    format_context_path=str(
                        suite_root / "context/FORMAT_CONTEXT.md"
                    ),
                    output_directory=str(base / "output"),
                )

            with self.assertRaises(ContextValidationError):
                validate_export_paths(
                    project_name="dp-api",
                    project_root=f"{project_root}/../project",
                    source_context_root=str(suite_root),
                    format_context_path=str(
                        suite_root / "context/FORMAT_CONTEXT.md"
                    ),
                    output_directory=str(base / "output"),
                )


class QdrantCollectionTests(unittest.TestCase):
    @patch("app.services.qdrant_service.client")
    def test_creates_context_collection_with_embedding_configuration(
        self,
        client_mock,
    ):
        client_mock.collection_exists.return_value = False

        create_collection(
            collection_name="sbm_contexts",
            vector_size=1024,
            distance=Distance.COSINE,
        )

        client_mock.create_collection.assert_called_once()
        call = client_mock.create_collection.call_args
        self.assertEqual(call.kwargs["collection_name"], "sbm_contexts")
        self.assertEqual(call.kwargs["vectors_config"].size, 1024)
        self.assertEqual(
            call.kwargs["vectors_config"].distance,
            Distance.COSINE,
        )

    @patch("app.services.qdrant_service.client")
    def test_rejects_incompatible_existing_context_collection(
        self,
        client_mock,
    ):
        client_mock.collection_exists.return_value = True
        client_mock.get_collection.return_value = SimpleNamespace(
            config=SimpleNamespace(
                params=SimpleNamespace(
                    vectors=SimpleNamespace(
                        size=384,
                        distance=Distance.COSINE,
                    )
                )
            )
        )

        with self.assertRaises(ValueError):
            create_collection(
                collection_name="sbm_contexts",
                vector_size=1024,
                distance=Distance.COSINE,
            )

    @patch("app.services.qdrant_service.client")
    def test_scroll_rejects_repeated_offsets(self, client_mock):
        client_mock.scroll.side_effect = [
            ([], "repeated-offset"),
            ([], "repeated-offset"),
        ]

        with self.assertRaises(RuntimeError):
            scroll_all_points(
                scroll_filter=SimpleNamespace(),
                collection_name="sbm_contexts",
            )


class ContextRetrievalTests(unittest.TestCase):
    def test_reuses_embedding_searches_both_scopes_and_deduplicates(self):
        global_point = SimpleNamespace(
            id="global",
            score=0.92,
            payload={
                "source_path": "/suite/context/SUITE_CONTEXT.md",
                "archive_path": (
                    "SBM-SUITE/context/SUITE_CONTEXT.md"
                ),
                "section": "Suite",
                "text": "Reglas globales.",
            },
        )
        duplicate_global = SimpleNamespace(
            id="global-copy",
            score=0.80,
            payload=dict(global_point.payload),
        )
        project_point = SimpleNamespace(
            id="project",
            score=0.97,
            payload={
                "source_path": (
                    "/suite/DP-API/context/PROJECT_CONTEXT.md"
                ),
                "archive_path": (
                    "SBM-SUITE/dp-api/context/"
                    "PROJECT_CONTEXT.md"
                ),
                "section": "API",
                "text": "Reglas del proyecto.",
            },
        )

        with (
            patch(
                "app.services.contexts.context_retrieval_service."
                "create_embedding",
                return_value=[0.1, 0.2],
            ) as embedding_mock,
            patch(
                "app.services.contexts.context_retrieval_service."
                "search_similar",
                side_effect=[
                    [global_point, duplicate_global],
                    [project_point],
                ],
            ) as search_mock,
        ):
            chunks = retrieve_relevant_context_chunks(
                project_name="dp-api",
                query="Cambiar endpoint",
                top_k=4,
            )

        embedding_mock.assert_called_once_with("Cambiar endpoint")
        self.assertEqual(search_mock.call_count, 2)
        self.assertTrue(
            all(
                call.kwargs["collection_name"] == "sbm_contexts"
                and call.kwargs["limit"] == 4
                for call in search_mock.call_args_list
            )
        )

        global_filter = search_mock.call_args_list[0].kwargs[
            "query_filter"
        ]
        project_filter = search_mock.call_args_list[1].kwargs[
            "query_filter"
        ]
        global_conditions = {
            condition.key: condition.match.value
            for condition in global_filter.must
        }
        project_conditions = {
            condition.key: condition.match.value
            for condition in project_filter.must
        }
        self.assertEqual(
            global_conditions,
            {
                "project_name": "dp-api",
                "workflow": "context-deploy",
                "is_active": True,
                "repository": "SBM-SUITE",
            },
        )
        self.assertEqual(
            project_conditions,
            {
                "project_name": "dp-api",
                "workflow": "context-deploy",
                "is_active": True,
            },
        )
        self.assertEqual(
            project_filter.must_not[0].match.value,
            "SBM-SUITE",
        )
        self.assertEqual(
            [chunk.point_id for chunk in chunks],
            ["project", "global"],
        )
        self.assertEqual(chunks[0].score, 0.97)
        self.assertEqual(
            chunks[0].archive_path,
            "SBM-SUITE/dp-api/context/PROJECT_CONTEXT.md",
        )
        self.assertEqual(chunks[0].content, "Reglas del proyecto.")


class ContextIndexTests(unittest.TestCase):
    def test_embeddings_are_generated_in_one_batch_per_source(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_path = Path(temporary_directory) / "README.md"
            markdown = "# One\nText\n\n# Two\nMore text"
            source_path.write_text(markdown, encoding="utf-8")
            source = ContextSource(
                source_path=source_path,
                archive_path="SBM-SUITE/dp-api/README.md",
                context_type="project_readme",
                repository="DP-API",
                legacy_source_path="DP-API/README.md",
            )
            chunks = split_markdown_into_chunks(markdown, "README.md")
            embedded_batches = []

            def embed_batch(texts):
                embedded_batches.append(texts)
                return [[0.1, 0.2, 0.3] for _ in texts]

            with (
                patch(
                    "app.services.contexts.context_index_service."
                    "collection_exists",
                    return_value=False,
                ),
                patch(
                    "app.services.contexts.context_index_service."
                    "create_collection"
                ),
                patch(
                    "app.services.contexts.context_index_service."
                    "save_embeddings",
                ),
                patch(
                    "app.services.contexts.context_index_service."
                    "scroll_all_points",
                    return_value=[],
                ),
                patch(
                    "app.services.contexts.context_index_service."
                    "deactivate_points",
                ),
                patch(
                    "app.services.contexts.context_index_service."
                    "update_points_payload",
                ),
            ):
                index_context_source(
                    source=source,
                    markdown=markdown,
                    chunks=chunks,
                    project_name="dp-api",
                    embed_many=embed_batch,
                )

            self.assertEqual(len(embedded_batches), 1)
            self.assertEqual(len(embedded_batches[0]), len(chunks))

    def test_unchanged_source_skips_embeddings_and_upsert(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_path = Path(temporary_directory) / "README.md"
            markdown = "# Section\nText"
            source_path.write_text(markdown, encoding="utf-8")
            source = ContextSource(
                source_path=source_path,
                archive_path="SBM-SUITE/dp-api/README.md",
                context_type="project_readme",
                repository="DP-API",
                legacy_source_path="DP-API/README.md",
            )
            chunks = split_markdown_into_chunks(markdown, "README.md")
            captured_points = []

            with (
                patch(
                    "app.services.contexts.context_index_service."
                    "collection_exists",
                    return_value=False,
                ),
                patch(
                    "app.services.contexts.context_index_service."
                    "create_collection"
                ),
                patch(
                    "app.services.contexts.context_index_service."
                    "save_embeddings",
                    side_effect=lambda points, collection_name: (
                        captured_points.extend(points)
                    ),
                ),
                patch(
                    "app.services.contexts.context_index_service."
                    "scroll_all_points",
                    return_value=[],
                ),
                patch(
                    "app.services.contexts.context_index_service."
                    "deactivate_points",
                ),
                patch(
                    "app.services.contexts.context_index_service."
                    "update_points_payload",
                ),
            ):
                index_context_source(
                    source=source,
                    markdown=markdown,
                    chunks=chunks,
                    project_name="dp-api",
                    embed_many=lambda texts: [
                        [0.1, 0.2, 0.3] for _ in texts
                    ],
                )

            with (
                patch(
                    "app.services.contexts.context_index_service."
                    "collection_exists",
                    return_value=True,
                ),
                patch(
                    "app.services.contexts.context_index_service."
                    "create_collection",
                ),
                patch(
                    "app.services.contexts.context_index_service."
                    "scroll_all_points",
                    return_value=captured_points,
                ),
                patch(
                    "app.services.contexts.context_index_service."
                    "save_embeddings",
                ) as save_mock,
                patch(
                    "app.services.contexts.context_index_service."
                    "update_points_payload",
                ) as update_payload_mock,
            ):
                indexed_count = index_context_source(
                    source=source,
                    markdown=markdown,
                    chunks=chunks,
                    project_name="dp-api",
                    embed_many=lambda texts: self.fail(
                        "unchanged source must not be embedded"
                    ),
                )

            self.assertEqual(indexed_count, len(chunks))
            save_mock.assert_not_called()
            update_payload_mock.assert_called_once()

    def test_archive_path_change_updates_payload_without_reembedding(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_path = (
                Path(temporary_directory)
                / "context"
                / "README.md"
            )
            source_path.parent.mkdir()
            markdown = "# Section\nText"
            source_path.write_text(markdown, encoding="utf-8")
            source = ContextSource(
                source_path=source_path,
                archive_path="SBM-SUITE/context/README.md",
                context_type="suite_readme",
                repository="SBM-SUITE",
                legacy_source_path="README.md",
            )
            chunks = split_markdown_into_chunks(markdown, "README.md")
            source_hash = hashlib.sha256(
                markdown.encode("utf-8")
            ).hexdigest()
            old_point = SimpleNamespace(
                id="old-deterministic-id",
                payload={
                    "archive_path": "SBM-SUITE/README.md",
                    "source_path": str(source_path),
                    "content_hash": source_hash,
                    "chunk_index": chunks[0].chunk_index,
                    "section": chunks[0].section,
                    "is_active": True,
                },
            )

            with (
                patch(
                    "app.services.contexts.context_index_service."
                    "collection_exists",
                    return_value=True,
                ),
                patch(
                    "app.services.contexts.context_index_service."
                    "create_collection",
                ),
                patch(
                    "app.services.contexts.context_index_service."
                    "scroll_all_points",
                    return_value=[old_point],
                ),
                patch(
                    "app.services.contexts.context_index_service."
                    "save_embeddings",
                ) as save_mock,
                patch(
                    "app.services.contexts.context_index_service."
                    "update_points_payload",
                ) as update_payload_mock,
            ):
                indexed_count = index_context_source(
                    source=source,
                    markdown=markdown,
                    chunks=chunks,
                    project_name="dp-api",
                    embed_many=lambda texts: self.fail(
                        "archive-path migration must not re-embed"
                    ),
                )

            self.assertEqual(indexed_count, 1)
            save_mock.assert_not_called()
            update_payload_mock.assert_called_once()
            payload = update_payload_mock.call_args.kwargs["payload"]
            self.assertEqual(
                payload["archive_path"],
                "SBM-SUITE/context/README.md",
            )
            self.assertEqual(payload["source_path"], str(source_path))
            self.assertEqual(payload["context_type"], "suite_readme")

    def test_ids_are_deterministic_and_old_chunks_are_deactivated(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_path = Path(temporary_directory) / "README.md"
            source_path.write_text("# Section\nText", encoding="utf-8")
            source = ContextSource(
                source_path=source_path,
                archive_path="SBM-SUITE/dp-api/README.md",
                context_type="project_readme",
                repository="DP-API",
                legacy_source_path="DP-API/README.md",
            )
            markdown = source_path.read_text(encoding="utf-8")
            chunks = split_markdown_into_chunks(markdown, "README.md")
            saved_batches = []

            def capture_points(points, collection_name):
                saved_batches.append(points)

            with (
                patch(
                    "app.services.contexts.context_index_service."
                    "collection_exists",
                    return_value=False,
                ),
                patch(
                    "app.services.contexts.context_index_service."
                    "create_collection"
                ) as create_collection_mock,
                patch(
                    "app.services.contexts.context_index_service."
                    "save_embeddings",
                    side_effect=capture_points,
                ),
                patch(
                    "app.services.contexts.context_index_service."
                    "scroll_all_points",
                    return_value=[],
                ),
                patch(
                    "app.services.contexts.context_index_service."
                    "deactivate_points"
                ) as deactivate_mock,
            ):
                for _ in range(2):
                    index_context_source(
                        source=source,
                        markdown=markdown,
                        chunks=chunks,
                        project_name="dp-api",
                        embed=lambda text: [0.1, 0.2, 0.3],
                    )

                self.assertEqual(
                    [point.id for point in saved_batches[0]],
                    [point.id for point in saved_batches[1]],
                )
                payload = saved_batches[0][0].payload
                required_metadata = {
                    "project",
                    "project_name",
                    "repository",
                    "context_type",
                    "section",
                    "source_path",
                    "updated_at",
                    "version",
                    "is_active",
                    "content_hash",
                    "workflow",
                }
                self.assertTrue(required_metadata.issubset(payload))
                self.assertEqual(payload["workflow"], "context-deploy")
                self.assertTrue(payload["is_active"])
                self.assertEqual(
                    payload["source_path"],
                    str(source_path),
                )
                create_collection_mock.assert_called_with(
                    collection_name="sbm_contexts",
                    vector_size=3,
                    distance=create_collection_mock.call_args.kwargs[
                        "distance"
                    ],
                )
                deactivate_mock.assert_called_with(
                    point_ids=[],
                    collection_name="sbm_contexts",
                )

                old_id = saved_batches[0][0].id

            with (
                patch(
                    "app.services.contexts.context_index_service."
                    "collection_exists",
                    return_value=False,
                ),
                patch(
                    "app.services.contexts.context_index_service."
                    "create_collection"
                ),
                patch(
                    "app.services.contexts.context_index_service."
                    "save_embeddings",
                ),
                patch(
                    "app.services.contexts.context_index_service."
                    "scroll_all_points",
                    return_value=[
                        SimpleNamespace(
                            id=old_id,
                            payload={"is_active": True},
                        )
                    ],
                ),
                patch(
                    "app.services.contexts.context_index_service."
                    "deactivate_points"
                ) as changed_deactivate_mock,
            ):
                changed_markdown = f"{markdown}\nChanged"
                changed_chunks = split_markdown_into_chunks(
                    changed_markdown,
                    "README.md",
                )
                index_context_source(
                    source=source,
                    markdown=changed_markdown,
                    chunks=changed_chunks,
                    project_name="dp-api",
                    embed=lambda text: [0.1, 0.2, 0.3],
                )

                changed_deactivate_mock.assert_called_once_with(
                    point_ids=[old_id],
                    collection_name="sbm_contexts",
                )


class ContextApplicationTests(unittest.TestCase):
    def test_missing_allowlisted_files_are_reported_without_exporting_others(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            suite_root = Path(temporary_directory) / "SBM-SUITE"
            project_root = suite_root / "DP-API"
            _write_markdown(suite_root / "context/README.md", "Suite")
            _write_markdown(
                suite_root / "context/FORMAT_CONTEXT.md",
                "Format",
            )
            _write_markdown(project_root / "README.md", "Project")

            request = ContextExportRequest(
                project_name="dp-api",
                workflow="context-deploy",
                project_root=str(project_root),
                source_context_root=str(suite_root),
                format_context_path=str(
                    suite_root / "context/FORMAT_CONTEXT.md"
                ),
                output_directory=str(suite_root / "output"),
            )

            with (
                patch(
                    "app.services.contexts.context_export_service."
                    "index_context_source",
                    side_effect=lambda **kwargs: len(
                        kwargs["chunks"]
                    ),
                ),
                patch(
                    "app.services.contexts.context_export_service."
                    "retrieve_relevant_context_chunks",
                    return_value=[],
                ),
            ):
                response = export_contexts(request)

            self.assertEqual(response.indexed_source_count, 3)
            self.assertEqual(len(response.errors), 10)
            self.assertIn(
                "Missing authorized full context file: "
                "SBM-SUITE/PROJECT_CONTEXT.md",
                response.errors,
            )

            with ZipFile(response.context_zip_path) as archive:
                names = set(archive.namelist())
                self.assertIn("SBM-SUITE/README.md", names)
                self.assertIn("SBM-SUITE/dp-api/README.md", names)
                self.assertNotIn(
                    "SBM-SUITE/PROJECT_CONTEXT.md",
                    names,
                )
                self.assertNotIn(
                    "SBM-SUITE/context/SUITE_CONTEXT.md",
                    names,
                )
                manifest = json.loads(
                    archive.read("manifest.json")
                )
                self.assertEqual(
                    set(manifest["missing_full_context_files"]),
                    {
                        "SBM-SUITE/PROJECT_CONTEXT.md",
                        "SBM-SUITE/context/SUITE_CONTEXT.md",
                        (
                            "SBM-SUITE/dp-api/context/"
                            "PROJECT_CONTEXT.md"
                        ),
                    },
                )


if __name__ == "__main__":
    unittest.main()
