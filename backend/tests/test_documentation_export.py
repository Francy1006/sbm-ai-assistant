from __future__ import annotations

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

from app.api.routes.documentation import router
from app.schemas.documentation import DocumentationExportRequest
from app.services.contexts.file_discovery_service import (
    ContextValidationError,
)
from app.services.contexts.models import RetrievedContextChunk
from app.services.documentation.documentation_export_service import (
    export_documentation,
)
from app.services.documentation.documentation_index_service import (
    index_documentation_source,
)
from app.services.documentation.documentation_retrieval_service import (
    build_documentation_query,
    retrieve_relevant_documentation_chunks,
)
from app.services.documentation.markdown_chunk_service import (
    split_documentation_markdown,
)
from app.services.documentation.models import DocumentationSource
from app.services.qdrant_service import (
    create_collection,
    scroll_all_points,
)


DOCUMENTATION_FILES = (
    "architecture.md",
    "business.md",
    "data-architecture.md",
    "security-devsecops.md",
    "devops-deployment.md",
    "qa-testing.md",
    "ai-engineering.md",
    "roadmap.md",
)


def _documentation_markdown(
    title: str,
    marker: str = "Validated content.",
) -> str:
    return (
        f"# {title}\n\n"
        "> **Last updated:** 2026-07-30\n"
        ">\n"
        "> **Purpose:** Test documentation fixture\n"
        ">\n"
        "> **Source of truth:** Git Markdown and validated evidence\n\n"
        "## Overview\n\n"
        f"{marker}\n\n"
        "## Document boundary\n\n"
        "This file excludes unsupported implementation claims.\n"
    )


def _write_documentation(
    path: Path,
    title: str,
    marker: str = "Validated content.",
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    path.write_text(
        _documentation_markdown(
            title,
            marker,
        ),
        encoding="utf-8",
    )


def _prepare_environment(
    temporary_directory: str,
) -> tuple[
    Path,
    Path,
    Path,
    Path,
    Path,
]:
    suite_root = (
        Path(temporary_directory)
        / "SBM-SUITE"
    )
    project_root = suite_root / "dp" / "DP-API"
    documentation_root = (
        suite_root
        / "context"
        / "documentation"
    )
    output_directory = (
        documentation_root / "output"
    )
    output_directory.mkdir(
        parents=True
    )

    for filename in DOCUMENTATION_FILES:
        _write_documentation(
            documentation_root / filename,
            Path(filename).stem.replace(
                "-",
                " ",
            ).title(),
        )

    format_context_path = (
        documentation_root
        / "FORMAT_CONTEXT.md"
    )
    system_prompt_path = (
        documentation_root
        / "SYS_PROMPT.md"
    )

    _write_documentation(
        format_context_path,
        "FORMAT_CONTEXT.md",
    )
    system_prompt_path.write_text(
        (
            "# SYS_PROMPT.md\n\n"
            "Generate validated documentation for {{PROJECT_NAME}}.\n"
        ),
        encoding="utf-8",
    )

    project_root.mkdir(
        parents=True,
        exist_ok=True,
    )
    (
        project_root
        / "project-tree.txt"
    ).write_text(
        "DP-API/\n"
        "├── backend/\n"
        "├── context/\n"
        "└── scripts/\n",
        encoding="utf-8",
    )

    return (
        suite_root,
        project_root,
        documentation_root,
        format_context_path,
        system_prompt_path,
    )


class DocumentationExportEndpointTests(
    unittest.TestCase
):
    def test_endpoint_exports_documentation_package(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp:
            (
                suite_root,
                project_root,
                documentation_root,
                format_context_path,
                system_prompt_path,
            ) = _prepare_environment(temp)
            output_directory = (
                documentation_root / "output"
            )

            app = FastAPI()
            app.include_router(router)

            retrieved_documentation = [
                RetrievedContextChunk(
                    point_id="documentation-1",
                    source_path=str(
                        documentation_root
                        / "architecture.md"
                    ),
                    archive_path=(
                        "documentation/"
                        "architecture.md"
                    ),
                    section="Overview",
                    score=0.96,
                    content=(
                        "Validated architecture "
                        "documentation."
                    ),
                )
            ]
            retrieved_context = [
                RetrievedContextChunk(
                    point_id="context-1",
                    source_path=str(
                        suite_root
                        / "context"
                        / "PROJECT_CONTEXT.md"
                    ),
                    archive_path=(
                        "SBM-SUITE/context/"
                        "PROJECT_CONTEXT.md"
                    ),
                    section="Executive summary",
                    score=0.93,
                    content=(
                        "Validated project context."
                    ),
                )
            ]
            indexed_sources = []

            def fake_index(**kwargs):
                indexed_sources.append(
                    kwargs["source"]
                )
                return len(kwargs["chunks"])

            request_body = {
                "project_name": "dp-api",
                "workflow": (
                    "documentation-deploy"
                ),
                "project_root": str(
                    project_root
                ),
                "documentation_root": str(
                    documentation_root
                ),
                "format_context_path": str(
                    format_context_path
                ),
                "system_prompt_path": str(
                    system_prompt_path
                ),
                "output_directory": str(
                    output_directory
                ),
                "change_summary": (
                    "Update API documentation."
                ),
                "changed_files": [
                    "backend/app/api/products.py"
                ],
                "git_diff": (
                    "diff --git "
                    "a/backend/app/api/products.py "
                    "b/backend/app/api/products.py"
                ),
                "qa_results": (
                    "Focused API tests: passed."
                ),
                "retrieved_context_chunks": [
                    chunk.__dict__
                    for chunk in retrieved_context
                ],
            }

            with (
                patch(
                    "app.services.documentation."
                    "documentation_export_service."
                    "index_documentation_source",
                    side_effect=fake_index,
                ),
                patch(
                    "app.services.documentation."
                    "documentation_export_service."
                    "retrieve_relevant_"
                    "documentation_chunks",
                    return_value=(
                        retrieved_documentation
                    ),
                ),
                patch(
                    "app.services.documentation."
                    "documentation_export_service."
                    "_collect_git_log",
                    return_value=(
                        "abc123 API update"
                    ),
                ),
            ):
                response = TestClient(
                    app
                ).post(
                    "/documentation/export",
                    json=request_body,
                )

            self.assertEqual(
                response.status_code,
                200,
            )
            payload = response.json()
            self.assertEqual(
                payload["status"],
                "completed",
            )
            self.assertEqual(
                payload["workflow"],
                "documentation-deploy",
            )
            self.assertEqual(
                payload["collection_name"],
                "sbm_documentation",
            )
            self.assertEqual(
                payload["errors"],
                [],
            )
            self.assertEqual(
                len(indexed_sources),
                len(DOCUMENTATION_FILES) + 2,
            )

            with ZipFile(
                payload[
                    "documentation_zip_path"
                ]
            ) as archive:
                names = set(
                    archive.namelist()
                )

                self.assertIn(
                    "manifest.json",
                    names,
                )
                self.assertIn(
                    "retrieved-documentation.md",
                    names,
                )
                self.assertIn(
                    "retrieved-context.md",
                    names,
                )
                self.assertIn(
                    "change-summary.md",
                    names,
                )
                self.assertIn(
                    "changed-files.txt",
                    names,
                )
                self.assertIn(
                    "git-diff.patch",
                    names,
                )
                self.assertIn(
                    "git-log.txt",
                    names,
                )
                self.assertIn(
                    "qa-results.md",
                    names,
                )
                self.assertIn(
                    "project-tree.txt",
                    names,
                )
                self.assertIn(
                    "FORMAT_CONTEXT.md",
                    names,
                )
                self.assertIn(
                    "SYS_PROMPT.md",
                    names,
                )

                for filename in (
                    DOCUMENTATION_FILES
                ):
                    self.assertIn(
                        (
                            "documentation/"
                            f"{filename}"
                        ),
                        names,
                    )

                manifest = json.loads(
                    archive.read(
                        "manifest.json"
                    )
                )

                self.assertEqual(
                    manifest["project_name"],
                    "dp-api",
                )
                self.assertEqual(
                    manifest["workflow"],
                    "documentation-deploy",
                )
                self.assertEqual(
                    manifest[
                        "collection_name"
                    ],
                    "sbm_documentation",
                )
                self.assertEqual(
                    manifest[
                        "retrieved_"
                        "documentation_chunk_count"
                    ],
                    1,
                )
                self.assertEqual(
                    manifest[
                        "retrieved_"
                        "context_chunk_count"
                    ],
                    1,
                )
                self.assertEqual(
                    manifest["top_k"],
                    8,
                )
                self.assertTrue(
                    manifest[
                        "project_tree"
                    ]["included"]
                )
                self.assertIn(
                    "Update API documentation.",
                    manifest["query"],
                )
                self.assertIn(
                    (
                        "backend/app/api/"
                        "products.py"
                    ),
                    manifest["query"],
                )
                self.assertIn(
                    "Focused API tests: passed.",
                    manifest["query"],
                )

                expected_tree = (
                    "DP-API/\n"
                    "├── backend/\n"
                    "├── context/\n"
                    "└── scripts/"
                )
                self.assertEqual(
                    manifest[
                        "project_tree"
                    ]["content_hash"],
                    hashlib.sha256(
                        expected_tree.encode(
                            "utf-8"
                        )
                    ).hexdigest(),
                )

    def test_endpoint_rejects_wrong_workflow(
        self,
    ):
        app = FastAPI()
        app.include_router(router)

        response = TestClient(app).post(
            "/documentation/export",
            json={
                "project_name": "dp-api",
                "workflow": "other",
                "project_root": "/tmp/project",
                "documentation_root": (
                    "/tmp/documentation"
                ),
                "format_context_path": (
                    "/tmp/documentation/"
                    "FORMAT_CONTEXT.md"
                ),
                "system_prompt_path": (
                    "/tmp/documentation/"
                    "SYS_PROMPT.md"
                ),
                "output_directory": (
                    "/tmp/output"
                ),
            },
        )

        self.assertEqual(
            response.status_code,
            422,
        )


class DocumentationExportServiceTests(
    unittest.TestCase
):
    def test_export_omits_project_tree_when_missing(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp:
            (
                _,
                project_root,
                documentation_root,
                format_context_path,
                system_prompt_path,
            ) = _prepare_environment(temp)
            (
                project_root
                / "project-tree.txt"
            ).unlink()

            request = DocumentationExportRequest(
                project_name="dp-api",
                workflow=(
                    "documentation-deploy"
                ),
                project_root=str(
                    project_root
                ),
                documentation_root=str(
                    documentation_root
                ),
                format_context_path=str(
                    format_context_path
                ),
                system_prompt_path=str(
                    system_prompt_path
                ),
                output_directory=str(
                    documentation_root
                    / "output"
                ),
                changed_files=[],
                git_diff="",
                qa_results="",
            )

            with (
                patch(
                    "app.services.documentation."
                    "documentation_export_service."
                    "index_documentation_source",
                    side_effect=lambda **kwargs: (
                        len(kwargs["chunks"])
                    ),
                ),
                patch(
                    "app.services.documentation."
                    "documentation_export_service."
                    "retrieve_relevant_"
                    "documentation_chunks",
                    return_value=[],
                ),
                patch(
                    "app.services.documentation."
                    "documentation_export_service."
                    "retrieve_relevant_context_chunks",
                    return_value=[],
                ),
                patch(
                    "app.services.documentation."
                    "documentation_export_service."
                    "_collect_git_log",
                    return_value="",
                ),
            ):
                response = (
                    export_documentation(
                        request
                    )
                )

            with ZipFile(
                response.
                documentation_zip_path
            ) as archive:
                self.assertNotIn(
                    "project-tree.txt",
                    archive.namelist(),
                )
                manifest = json.loads(
                    archive.read(
                        "manifest.json"
                    )
                )
                self.assertFalse(
                    manifest[
                        "project_tree"
                    ]["included"]
                )

    def test_export_rejects_project_tree_symlink(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp:
            (
                _,
                project_root,
                documentation_root,
                format_context_path,
                system_prompt_path,
            ) = _prepare_environment(temp)

            tree_path = (
                project_root
                / "project-tree.txt"
            )
            tree_path.unlink()
            real_tree = (
                project_root
                / "real-tree.txt"
            )
            real_tree.write_text(
                "DP-API/\n",
                encoding="utf-8",
            )
            tree_path.symlink_to(
                real_tree
            )

            request = DocumentationExportRequest(
                project_name="dp-api",
                workflow=(
                    "documentation-deploy"
                ),
                project_root=str(
                    project_root
                ),
                documentation_root=str(
                    documentation_root
                ),
                format_context_path=str(
                    format_context_path
                ),
                system_prompt_path=str(
                    system_prompt_path
                ),
                output_directory=str(
                    documentation_root
                    / "output"
                ),
                changed_files=[],
                git_diff="",
                qa_results="",
            )

            with (
                patch(
                    "app.services.documentation."
                    "documentation_export_service."
                    "index_documentation_source",
                    side_effect=lambda **kwargs: (
                        len(kwargs["chunks"])
                    ),
                ),
                patch(
                    "app.services.documentation."
                    "documentation_export_service."
                    "retrieve_relevant_"
                    "documentation_chunks",
                    return_value=[],
                ),
            ):
                with self.assertRaises(
                    Exception
                ):
                    export_documentation(
                        request
                    )


class DocumentationRetrievalTests(
    unittest.TestCase
):
    def test_query_contains_change_domains_and_project_tree(
        self,
    ):
        query = build_documentation_query(
            project_name="dp-api",
            change_summary=(
                "Update authentication docs."
            ),
            changed_files=[
                "backend/app/auth/views.py",
                "backend/tests/test_auth.py",
            ],
            git_diff=(
                "diff --git a/auth b/auth"
            ),
            qa_results="Auth tests passed.",
            documentation_files=[
                "documentation/"
                "security-devsecops.md"
            ],
            project_tree=(
                "DP-API/\n└── backend/"
            ),
        )

        self.assertIn(
            "Update authentication docs.",
            query,
        )
        self.assertIn(
            "Security and DevSecOps",
            query,
        )
        self.assertIn(
            "QA and Testing",
            query,
        )
        self.assertIn(
            "Current project structure:",
            query,
        )

    def test_retrieval_searches_both_scopes_deduplicates_and_caps_top_k(
        self,
    ):
        global_point = SimpleNamespace(
            id="global",
            score=0.93,
            payload={
                "source_path": (
                    "/suite/context/"
                    "documentation/"
                    "architecture.md"
                ),
                "archive_path": (
                    "documentation/"
                    "architecture.md"
                ),
                "section": "Overview",
                "text": (
                    "Global architecture."
                ),
            },
        )
        duplicate_global = SimpleNamespace(
            id="global-copy",
            score=0.81,
            payload=dict(
                global_point.payload
            ),
        )
        project_point = SimpleNamespace(
            id="project",
            score=0.97,
            payload={
                "source_path": (
                    "/suite/dp/DP-API/"
                    "documentation/api.md"
                ),
                "archive_path": (
                    "documentation/"
                    "projects/dp-api/api.md"
                ),
                "section": "Endpoints",
                "text": (
                    "Project API documentation."
                ),
            },
        )

        with (
            patch(
                "app.services.documentation."
                "documentation_retrieval_service."
                "create_embedding",
                return_value=[0.1, 0.2],
            ) as embedding_mock,
            patch(
                "app.services.documentation."
                "documentation_retrieval_service."
                "search_similar",
                side_effect=[
                    [
                        global_point,
                        duplicate_global,
                    ],
                    [project_point],
                ],
            ) as search_mock,
        ):
            chunks = retrieve_relevant_documentation_chunks(
                project_name="dp-api",
                query="Update API documentation",
                top_k=2,
            )

        embedding_mock.assert_called_once_with(
            "Update API documentation"
        )
        self.assertEqual(
            search_mock.call_count,
            2,
        )
        self.assertTrue(
            all(
                call.kwargs[
                    "collection_name"
                ] == "sbm_documentation"
                and call.kwargs["limit"] == 2
                for call
                in search_mock.call_args_list
            )
        )
        self.assertEqual(
            [
                chunk.point_id
                for chunk in chunks
            ],
            ["project", "global"],
        )
        self.assertEqual(
            len(chunks),
            2,
        )


class DocumentationIndexTests(
    unittest.TestCase
):
    def test_index_uses_documentation_collection_and_metadata(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp:
            source_path = (
                Path(temp)
                / "architecture.md"
            )
            markdown = (
                _documentation_markdown(
                    "Architecture"
                )
            )
            source_path.write_text(
                markdown,
                encoding="utf-8",
            )
            source = DocumentationSource(
                source_path=source_path,
                archive_path=(
                    "documentation/"
                    "architecture.md"
                ),
                documentation_type=(
                    "architecture"
                ),
                repository="SBM-SUITE",
                legacy_source_path=None,
            )
            chunks = (
                split_documentation_markdown(
                    markdown,
                    "architecture.md",
                )
            )
            captured_points = []

            with (
                patch(
                    "app.services.documentation."
                    "documentation_index_service."
                    "collection_exists",
                    return_value=False,
                ),
                patch(
                    "app.services.documentation."
                    "documentation_index_service."
                    "create_collection",
                ) as create_mock,
                patch(
                    "app.services.documentation."
                    "documentation_index_service."
                    "save_embeddings",
                    side_effect=lambda points, collection_name: (
                        captured_points.extend(
                            points
                        )
                    ),
                ),
                patch(
                    "app.services.documentation."
                    "documentation_index_service."
                    "scroll_all_points",
                    return_value=[],
                ),
                patch(
                    "app.services.documentation."
                    "documentation_index_service."
                    "deactivate_points",
                ),
            ):
                indexed_count = (
                    index_documentation_source(
                        source=source,
                        markdown=markdown,
                        chunks=chunks,
                        project_name="dp-api",
                        embed_many=lambda texts: [
                            [0.1, 0.2, 0.3]
                            for _ in texts
                        ],
                    )
                )

            self.assertEqual(
                indexed_count,
                len(chunks),
            )
            self.assertTrue(
                captured_points
            )
            payload = (
                captured_points[0].payload
            )
            self.assertEqual(
                payload["workflow"],
                "documentation-deploy",
            )
            self.assertEqual(
                payload["project_name"],
                "dp-api",
            )
            self.assertEqual(
                payload["repository"],
                "SBM-SUITE",
            )
            self.assertTrue(
                payload["is_active"]
            )
            create_mock.assert_called_once()
            self.assertEqual(
                create_mock.call_args.kwargs[
                    "collection_name"
                ],
                "sbm_documentation",
            )

    def test_collection_configuration_is_validated(
        self,
    ):
        with patch(
            "app.services.qdrant_service.client"
        ) as client_mock:
            client_mock.collection_exists.return_value = (
                False
            )

            create_collection(
                collection_name=(
                    "sbm_documentation"
                ),
                vector_size=1024,
                distance=Distance.COSINE,
            )

            call = (
                client_mock.
                create_collection.call_args
            )
            self.assertEqual(
                call.kwargs[
                    "collection_name"
                ],
                "sbm_documentation",
            )
            self.assertEqual(
                call.kwargs[
                    "vectors_config"
                ].size,
                1024,
            )
            self.assertEqual(
                call.kwargs[
                    "vectors_config"
                ].distance,
                Distance.COSINE,
            )

    def test_scroll_rejects_repeated_offsets(
        self,
    ):
        with patch(
            "app.services.qdrant_service.client"
        ) as client_mock:
            client_mock.scroll.side_effect = [
                ([], "same-offset"),
                ([], "same-offset"),
            ]

            with self.assertRaises(
                RuntimeError
            ):
                scroll_all_points(
                    scroll_filter=(
                        SimpleNamespace()
                    ),
                    collection_name=(
                        "sbm_documentation"
                    ),
                )


class DocumentationSchemaTests(
    unittest.TestCase
):
    def test_request_rejects_duplicate_changed_files(
        self,
    ):
        with self.assertRaises(
            ValueError
        ):
            DocumentationExportRequest(
                project_name="dp-api",
                workflow=(
                    "documentation-deploy"
                ),
                project_root="/tmp/project",
                documentation_root=(
                    "/tmp/documentation"
                ),
                format_context_path=(
                    "/tmp/FORMAT_CONTEXT.md"
                ),
                system_prompt_path=(
                    "/tmp/SYS_PROMPT.md"
                ),
                output_directory="/tmp/output",
                changed_files=[
                    "README.md",
                    "README.md",
                ],
            )

    def test_request_rejects_duplicate_context_chunk_ids(
        self,
    ):
        duplicate = RetrievedContextChunk(
            point_id="same",
            source_path="/tmp/source.md",
            archive_path=(
                "SBM-SUITE/context/"
                "PROJECT_CONTEXT.md"
            ),
            section="Overview",
            score=0.9,
            content="Content",
        )

        with self.assertRaises(
            ValueError
        ):
            DocumentationExportRequest(
                project_name="dp-api",
                workflow=(
                    "documentation-deploy"
                ),
                project_root="/tmp/project",
                documentation_root=(
                    "/tmp/documentation"
                ),
                format_context_path=(
                    "/tmp/FORMAT_CONTEXT.md"
                ),
                system_prompt_path=(
                    "/tmp/SYS_PROMPT.md"
                ),
                output_directory="/tmp/output",
                retrieved_context_chunks=[
                    duplicate,
                    duplicate,
                ],
            )


if __name__ == "__main__":
    unittest.main()
