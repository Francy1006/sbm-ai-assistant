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
from app.schemas.contexts import ContextExportRequest, ContextExportResponse
from app.services.contexts.context_export_service import (
    _validate_project_tree_evidence,
    export_contexts,
)
from app.services.contexts.context_index_service import (
    _deactivate_obsolete_path_points,
    index_context_source,
)
from app.services.contexts.contract_registry import (
    LIFECYCLE_PHASES,
    PATCH_DEFINITIONS,
    build_contract_version,
    canonical_projects,
    patch_target_file,
    supported_patch_paths,
    supported_patch_paths_for_project,
    validate_format_context,
)
from app.services.contexts.context_retrieval_service import (
    retrieve_relevant_context_chunks,
)
from app.services.contexts.file_discovery_service import (
    ContextValidationError,
    discover_context_sources,
    validate_export_paths,
)
from app.services.contexts.markdown_chunk_service import (
    split_markdown_into_chunks,
)
from app.services.contexts.zip_export_service import create_context_package
from app.services.contexts.models import (
    ContextSource,
    FullContextFile,
    RetrievedContextChunk,
)
from app.services.qdrant_service import create_collection, scroll_all_points
from app.services.project_registry import (
    ProjectRegistryError,
    repository_to_runtime_path,
    runtime_to_repository_path,
)


GLOBAL_SOURCE_FILES = (
    ("context/PROJECT_CONTEXT.md", "context/PROJECT_CONTEXT.md"),
    ("context/README.md", "context/README.md"),
    ("context/SUITE_CONTEXT.md", "context/SUITE_CONTEXT.md"),
    ("context/BUSINESS_CONTEXT.md", "context/BUSINESS_CONTEXT.md"),
    ("context/QA_CONTEXT.md", "context/QA_CONTEXT.md"),
    ("context/COMPLETED_OBJECTIVES.md", "context/COMPLETED_OBJECTIVES.md"),
    ("context/SECURITY_CONTEXT.md", "context/SECURITY_CONTEXT.md"),
    ("context/DATA_CONTEXT.md", "context/DATA_CONTEXT.md"),
    ("context/DECISIONS_CONTEXT.md", "context/DECISIONS_CONTEXT.md"),
    ("context/SYS_PROMPT.md", "context/SYS_PROMPT.md"),
    ("context/FORMAT_CONTEXT.md", "context/FORMAT_CONTEXT.md"),
)


def _valid_format_contract(project_name: str = "dp-api") -> str:
    titles = (
        "Global rules",
        "Global `PROJECT_CONTEXT.md`",
        "Global `COMPLETED_OBJECTIVES.md`",
        "Global `SUITE_CONTEXT.md`",
        "Global `BUSINESS_CONTEXT.md`",
        "Global `QA_CONTEXT.md`",
        "Global `SECURITY_CONTEXT.md`",
        "Global `DATA_CONTEXT.md`",
        "Global `DECISIONS_CONTEXT.md`",
        "Global `SYS_PROMPT.md`",
        "Project `context/PROJECT_CONTEXT.md`",
        "Project `context/QA_CONTEXT.md`",
        "Project `context/DEPLOY_CONTEXT.md`",
        "Project and suite `README.md`",
    )
    sections = ["# FORMAT_CONTEXT.md", ""]
    for number, title in enumerate(titles, start=1):
        sections.extend([f"## {number}. {title}", ""])
        if number == 14:
            sections.extend(["README headings are repository-owned.", ""])
    sections.append("### Output patch mappings")
    sections.append("")
    for path, definition in PATCH_DEFINITIONS.items():
        target = patch_target_file(path, project_name)
        sections.extend([path, f"→ {target}", ""])
    return "\n".join(sections)

PROJECT_FILES = (
    "README.md",
    "context/PROJECT_CONTEXT.md",
    "context/QA_CONTEXT.md",
    "context/DEPLOY_CONTEXT.md",
)


def _write_markdown(path: Path, title: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        _valid_format_contract()
        if path.name == "FORMAT_CONTEXT.md"
        else f"# {title}\n\nContenido de prueba."
    )
    path.write_text(content, encoding="utf-8")


def _export_contexts_at(request: ContextExportRequest, suite_root: Path):
    with patch(
        "app.services.contexts.context_export_service."
        "CONTEXT_UPGRADE_SUITE_CONTEXT_ROOT",
        str(suite_root / "context"),
    ):
        return export_contexts(request)


class ContextExportEndpointTests(unittest.TestCase):
    def test_contract_endpoint_uses_runtime_registry(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            context_root = Path(temporary_directory) / "context"
            format_path = context_root / "FORMAT_CONTEXT.md"
            _write_markdown(format_path, "FORMAT_CONTEXT.md")
            app = FastAPI()
            app.include_router(router)

            with patch(
                "app.api.routes.contexts."
                "CONTEXT_UPGRADE_SUITE_CONTEXT_ROOT",
                str(context_root),
            ):
                response = TestClient(app).get("/contexts/contract")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.json(),
                {
                    "contract_version": build_contract_version(
                        format_path.read_text(encoding="utf-8")
                    ),
                    "supported_patch_paths": supported_patch_paths(),
                    "lifecycle_phases": list(LIFECYCLE_PHASES),
                    "canonical_projects": canonical_projects(),
                },
            )

    def test_export_blocks_format_backend_divergence(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            suite_root = Path(temporary_directory) / "SBM-SUITE"
            context_root = suite_root / "context"
            project_root = suite_root / "dp" / "DP-API"
            output_root = context_root / "output"
            context_root.mkdir(parents=True)
            project_root.mkdir(parents=True)
            output_root.mkdir()
            format_path = context_root / "FORMAT_CONTEXT.md"
            format_path.write_text(
                _valid_format_contract().replace(
                    "## 14. Project and suite `README.md`",
                    "## 13. Project and suite `README.md`",
                ),
                encoding="utf-8",
            )
            request = ContextExportRequest(
                project_name="dp-api",
                workflow="context-deploy",
                lifecycle_phase="implementation-progress",
                objectives=[{"objective_id": "OBJ-001"}],
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "FORMAT_CONTEXT.md/backend contract divergence",
            ):
                _export_contexts_at(request, suite_root)


    def test_endpoint_exports_only_allowlisted_files_and_manifest(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            suite_root = Path(temporary_directory) / "SBM-SUITE"
            project_root = suite_root / "dp" / "DP-API"
            output_directory = suite_root / "context" / "output"
            output_directory.mkdir(parents=True)
            (output_directory / "SYS_PROMPT.md").write_text(
                "# Runtime prompt\n",
                encoding="utf-8",
            )

            with ZipFile(
                output_directory / "context-package.zip",
                mode="w",
            ) as stale_archive:
                stale_archive.writestr(
                    "SBM-SUITE/context/PROJECT_CONTEXT.md",
                    "stale",
                )
                stale_archive.writestr(
                    "SBM-SUITE/context/README.md",
                    "stale",
                )

            for source_path, archive_path in GLOBAL_SOURCE_FILES:
                _write_markdown(suite_root / source_path, archive_path)

            for relative_path in PROJECT_FILES:
                _write_markdown(project_root / relative_path, relative_path)

            _write_markdown(project_root / "src/secret.py", "not exported")
            (suite_root / "context" / "project-tree.txt").write_text(
                "SBM-SUITE/\n├── context/\n└── dp/\n    └── DP-API/\n",
                encoding="utf-8",
            )
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
                "lifecycle_phase": "implementation-progress",
                "execution_mode": "evidence",
                "objectives": [{"objective_id": "OBJ-001"}],
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
                        "SBM-SUITE/dp/DP-API/context/"
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
                patch(
                    "app.services.contexts.context_export_service."
                    "CONTEXT_UPGRADE_SUITE_CONTEXT_ROOT",
                    str(suite_root / "context"),
                ),
            ):
                response = TestClient(app).post(
                    "/contexts/export",
                    json=request_body,
                )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["status"], "completed")
            self.assertEqual(
                payload["lifecycle_phase"],
                "implementation-progress",
            )
            self.assertEqual(payload["execution_mode"], "evidence")
            self.assertEqual(payload["objectives"], [{"objective_id": "OBJ-001"}])
            self.assertEqual(payload["indexed_source_count"], 15)
            self.assertEqual(payload["collection_name"], "sbm_contexts")
            self.assertEqual(payload["errors"], [])
            self.assertTrue(payload["upload_zip_path"].endswith(
                "context-deploy-package.zip"
            ))
            with ZipFile(suite_root / payload["upload_zip_path"]) as upload_archive:
                self.assertEqual(
                    set(upload_archive.namelist()),
                    {
                        "context-export-response.json",
                        "context-package.zip",
                        "SYS_PROMPT.md",
                    },
                )
                embedded_response = json.loads(
                    upload_archive.read(
                        "context-export-response.json"
                    ).decode("utf-8")
                )
                self.assertEqual(embedded_response, payload)
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

            with ZipFile(suite_root / payload["context_zip_path"]) as archive:
                names = set(archive.namelist())
                expected_names = {
                    "retrieved-context.md",
                    "change-summary.md",
                    "changed-files.txt",
                    "git-diff.patch",
                    "git-log.txt",
                    "qa-results.md",
                    "project-tree.txt",
                    "FORMAT_CONTEXT.md",
                    "manifest.json",
                    "SBM-SUITE/context/PROJECT_CONTEXT.md",
                    "SBM-SUITE/context/README.md",
                    "SBM-SUITE/context/SUITE_CONTEXT.md",
                    "SBM-SUITE/context/COMPLETED_OBJECTIVES.md",
                    "SBM-SUITE/context/BUSINESS_CONTEXT.md",
                    "SBM-SUITE/context/QA_CONTEXT.md",
                    "SBM-SUITE/context/SECURITY_CONTEXT.md",
                    "SBM-SUITE/context/DATA_CONTEXT.md",
                    "SBM-SUITE/context/DECISIONS_CONTEXT.md",
                    (
                        "SBM-SUITE/dp/DP-API/context/"
                        "PROJECT_CONTEXT.md"
                    ),
                    "SBM-SUITE/dp/DP-API/README.md",
                    "SBM-SUITE/dp/DP-API/context/QA_CONTEXT.md",
                    "SBM-SUITE/dp/DP-API/context/DEPLOY_CONTEXT.md",
                }
                self.assertEqual(names, expected_names)
                self.assertEqual(
                    archive.read("qa-results.md").decode("utf-8"),
                    "Pruebas focalizadas: OK.\n",
                )
                self.assertNotIn("SBM-SUITE/dp/DP-API/.env", names)
                self.assertNotIn("SBM-SUITE/dp/DP-API/src/secret.py", names)
                self.assertNotIn("SBM-SUITE/context/SYS_PROMPT.md", names)
                self.assertNotEqual(
                    archive.read("SBM-SUITE/context/PROJECT_CONTEXT.md"),
                    b"stale",
                )

                manifest = json.loads(archive.read("manifest.json"))
                self.assertEqual(manifest["project_name"], "dp-api")
                self.assertEqual(len(manifest["contract_version"]), 64)
                self.assertEqual(
                    manifest["supported_patch_paths"],
                    sorted(PATCH_DEFINITIONS),
                )
                self.assertEqual(
                    manifest["canonical_project_path"],
                    "SBM-SUITE/dp/DP-API",
                )
                self.assertEqual(
                    manifest["lifecycle_phase"],
                    "implementation-progress",
                )
                self.assertEqual(manifest["execution_mode"], "evidence")
                self.assertEqual(manifest["objectives"][0]["objective_id"], "OBJ-001")
                self.assertEqual(
                    set(manifest["full_target_files"]),
                    set(manifest["target_content_hashes"]),
                )
                self.assertEqual(
                    set(manifest["full_target_files"]),
                    set(manifest["target_section_hashes"]),
                )
                self.assertEqual(manifest["missing_full_target_files"], [])
                self.assertNotIn(
                    "FORMAT_CONTEXT.md",
                    manifest["full_target_files"],
                )
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
                self.assertEqual(
                    manifest["project_tree"],
                    {
                        "included": True,
                        "source_path": "SBM-SUITE/context/project-tree.txt",
                        "archive_path": "project-tree.txt",
                        "content_hash": hashlib.sha256(
                            (
                                "SBM-SUITE/\n"
                                "├── context/\n"
                                "└── dp/\n"
                                "    └── DP-API/\n"
                            ).encode("utf-8")
                        ).hexdigest(),
                    },
                )
                self.assertEqual(
                    archive.read("project-tree.txt").decode("utf-8"),
                    "SBM-SUITE/\n├── context/\n└── dp/\n    └── DP-API/\n",
                )
                self.assertIn(
                    "Estructura actual de SBM Suite:",
                    manifest["query"],
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
                            "SBM-SUITE/dp/DP-API/context/"
                            "PROJECT_CONTEXT.md"
                        ),
                    },
                )
                expected_full_contexts = {
                    "FORMAT_CONTEXT.md",
                    "SBM-SUITE/context/PROJECT_CONTEXT.md",
                    "SBM-SUITE/context/README.md",
                    "SBM-SUITE/context/COMPLETED_OBJECTIVES.md",
                    "SBM-SUITE/context/SUITE_CONTEXT.md",
                    "SBM-SUITE/context/BUSINESS_CONTEXT.md",
                    "SBM-SUITE/context/QA_CONTEXT.md",
                    "SBM-SUITE/context/SECURITY_CONTEXT.md",
                    "SBM-SUITE/context/DATA_CONTEXT.md",
                    "SBM-SUITE/context/DECISIONS_CONTEXT.md",
                    (
                        "SBM-SUITE/dp/DP-API/context/"
                        "PROJECT_CONTEXT.md"
                    ),
                    "SBM-SUITE/dp/DP-API/README.md",
                    "SBM-SUITE/dp/DP-API/context/QA_CONTEXT.md",
                    "SBM-SUITE/dp/DP-API/context/DEPLOY_CONTEXT.md",
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
                    expected_full_contexts | {"project-tree.txt"},
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


    def test_export_requires_project_tree_evidence(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            suite_root = Path(temporary_directory) / "SBM-SUITE"
            project_root = suite_root / "dp" / "DP-API"
            output_directory = suite_root / "context" / "output"
            output_directory.mkdir(parents=True)
            (output_directory / "SYS_PROMPT.md").write_text(
                "# Runtime prompt\n",
                encoding="utf-8",
            )

            for source_path, archive_path in GLOBAL_SOURCE_FILES:
                _write_markdown(suite_root / source_path, archive_path)

            for relative_path in PROJECT_FILES:
                _write_markdown(project_root / relative_path, relative_path)

            request = ContextExportRequest(
                project_name="dp-api",
                workflow="context-deploy",
                lifecycle_phase="implementation-progress",
                objectives=[{"objective_id": "OBJ-001"}],
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
                with self.assertRaisesRegex(
                    ContextValidationError,
                    "project-tree.txt is required as structural evidence",
                ):
                    _export_contexts_at(request, suite_root)

    def test_export_rejects_project_tree_symlink(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            suite_root = Path(temporary_directory) / "SBM-SUITE"
            project_root = suite_root / "dp" / "DP-API"
            output_directory = suite_root / "context" / "output"
            output_directory.mkdir(parents=True)
            (output_directory / "SYS_PROMPT.md").write_text(
                "# Runtime prompt\n",
                encoding="utf-8",
            )

            for source_path, archive_path in GLOBAL_SOURCE_FILES:
                _write_markdown(suite_root / source_path, archive_path)

            for relative_path in PROJECT_FILES:
                _write_markdown(project_root / relative_path, relative_path)

            real_tree = project_root / "real-tree.txt"
            real_tree.write_text("SBM-SUITE/\n", encoding="utf-8")
            (suite_root / "context" / "project-tree.txt").symlink_to(real_tree)

            request = ContextExportRequest(
                project_name="dp-api",
                workflow="context-deploy",
                lifecycle_phase="implementation-progress",
                objectives=[{"objective_id": "OBJ-001"}],
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
            ):
                with self.assertRaises(Exception):
                    _export_contexts_at(request, suite_root)

    def test_suite_context_export_resolves_canonical_registry_identity(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            suite_root = Path(temporary_directory) / "SBM-SUITE"
            output_directory = suite_root / "context" / "output"
            output_directory.mkdir(parents=True)
            (output_directory / "SYS_PROMPT.md").write_text(
                "# Runtime prompt\n",
                encoding="utf-8",
            )
            for source_path, archive_path in GLOBAL_SOURCE_FILES:
                _write_markdown(suite_root / source_path, archive_path)
            (suite_root / "context" / "FORMAT_CONTEXT.md").write_text(
                _valid_format_contract(),
                encoding="utf-8",
            )
            (suite_root / "context" / "project-tree.txt").write_text(
                "SBM-SUITE/\n- context/\n",
                encoding="utf-8",
            )
            request = ContextExportRequest(
                project_name="sbm-suite-context",
                workflow="context-deploy",
                lifecycle_phase="implementation-progress",
                objectives=[{"objective_id": "OBJ-CTX-001"}],
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
                response = _export_contexts_at(request, suite_root)

            with ZipFile(suite_root / response.context_zip_path) as archive:
                manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(manifest["project_name"], "sbm-suite-context")
            self.assertEqual(
                manifest["canonical_project_path"],
                "SBM-SUITE/context",
            )
            self.assertNotIn(
                "patches/project-context.json",
                manifest["supported_patch_paths"],
            )
            self.assertFalse(
                any(
                    "/context/context/" in path
                    for path in manifest["full_target_files"]
                )
            )


class ContextExportRequestTests(unittest.TestCase):
    @staticmethod
    def _qa_decision(
        status: str,
        applicable: bool,
        evidence: str,
    ) -> dict:
        return {
            "status": status,
            "applicable": applicable,
            "workflow_path": "scripts/qa-check.sh",
            "evidence_file": "qa-results.md",
            "evidence_sha256": hashlib.sha256(
                evidence.encode("utf-8")
            ).hexdigest(),
            "reason": (
                "applicable QA workflow executed with canonical evidence"
                if applicable
                else "no applicable QA workflow is currently defined"
            ),
        }

    @staticmethod
    def _planning_objective(objective_id: str = "OBJ-001") -> dict:
        return {
            "objective_id": objective_id,
            "objective": f"Objective {objective_id}",
            "status": "pending",
            "priority": 5,
            "target_date": "N/A",
            "branch": "FEATURE-enable-material",
        }

    def _request(self, lifecycle_phase: str, user_prompt=None):
        if lifecycle_phase == "planning-activation":
            objectives = [self._planning_objective()]
        elif lifecycle_phase == "objective-activation":
            objectives = [
                {
                    **self._planning_objective(),
                    "status": "active",
                }
            ]
        else:
            objectives = [{"objective_id": "OBJ-001"}]
        request_fields = {}
        if lifecycle_phase == "implementation-closure":
            canonical_qa_results = (
                "# QA Results\n\n"
                "QA status: not-applicable\n"
            )
            request_fields = {
                "qa_results": canonical_qa_results.rstrip("\n"),
                "qa": self._qa_decision(
                    "not-applicable",
                    False,
                    canonical_qa_results,
                ),
            }
        return ContextExportRequest(
            project_name="dp-api",
            workflow="context-deploy",
            lifecycle_phase=lifecycle_phase,
            execution_mode=(
                "user-guided"
                if user_prompt and user_prompt.strip()
                else "evidence"
            ),
            objectives=objectives,
            user_prompt=user_prompt,
            **request_fields,
        )

    @staticmethod
    def _closure_response() -> ContextExportResponse:
        return ContextExportResponse(
            status="completed",
            project_name="dp-api",
            workflow="context-deploy",
            lifecycle_phase="implementation-closure",
            execution_mode="evidence",
            objectives=[{"objective_id": "OBJ-001"}],
            context_zip_path="context/output/context-package.zip",
            upload_zip_path="context/output/context-deploy-package.zip",
            indexed_source_count=0,
            chunk_count=0,
            collection_name="sbm_contexts",
            errors=[],
        )

    def test_planning_without_user_prompt_is_accepted(self):
        request = self._request("planning-activation")
        self.assertIsNone(request.user_prompt)
        self.assertEqual(request.execution_mode, "evidence")

    def test_user_prompt_requires_user_guided_execution_mode(self):
        request = self._request(
            "planning-activation",
            "Create the confirmed objective batch.",
        )
        self.assertEqual(request.execution_mode, "user-guided")

        with self.assertRaisesRegex(ValueError, "execution_mode must be"):
            ContextExportRequest(
                project_name="dp-api",
                workflow="context-deploy",
                lifecycle_phase="planning-activation",
                execution_mode="evidence",
                objectives=[self._planning_objective()],
                user_prompt="Create the confirmed objective batch.",
            )

    def test_user_guided_requires_user_prompt(self):
        with self.assertRaisesRegex(ValueError, "execution_mode must be"):
            ContextExportRequest(
                project_name="dp-api",
                workflow="context-deploy",
                lifecycle_phase="planning-activation",
                execution_mode="user-guided",
                objectives=[self._planning_objective()],
            )

    def test_planning_batch_is_accepted(self):
        request = ContextExportRequest(
            project_name="dp-api",
            workflow="context-deploy",
            lifecycle_phase="planning-activation",
            objectives=[
                self._planning_objective("OBJ-001"),
                {
                    **self._planning_objective("OBJ-002"),
                    "branch": "FEATURE-enable-orders",
                },
            ],
        )
        self.assertEqual(len(request.objectives), 2)

    def test_planning_rejects_missing_required_field_in_any_objective(self):
        invalid = self._planning_objective("OBJ-002")
        invalid.pop("priority")
        with self.assertRaisesRegex(ValueError, "missing required planning fields"):
            ContextExportRequest(
                project_name="dp-api",
                workflow="context-deploy",
                lifecycle_phase="planning-activation",
                objectives=[self._planning_objective(), invalid],
            )

    def test_planning_rejects_duplicate_objective_ids(self):
        with self.assertRaisesRegex(ValueError, "duplicate objective_id"):
            ContextExportRequest(
                project_name="dp-api",
                workflow="context-deploy",
                lifecycle_phase="planning-activation",
                objectives=[
                    self._planning_objective(),
                    self._planning_objective(),
                ],
            )

    def test_objective_activation_is_distinct_from_planning_creation(self):
        request = self._request("objective-activation")

        self.assertEqual(request.lifecycle_phase, "objective-activation")
        self.assertEqual(request.objectives[0].status, "active")
        self.assertEqual(
            request.objectives[0].model_dump(exclude_none=True),
            {
                **self._planning_objective(),
                "status": "active",
            },
        )

    def test_objective_activation_manifest_preserves_explicit_transition(self):
        request = self._request("objective-activation")
        objective = request.objectives[0].model_dump(exclude_none=True)

        with tempfile.TemporaryDirectory() as temporary_directory:
            package_path = create_context_package(
                output_directory=Path(temporary_directory),
                project_name="dp-api",
                query="Activate existing pending objective.",
                retrieved_chunks=[],
                change_summary="Pending to active.",
                changed_files=[],
                git_diff="",
                git_log="",
                qa_results="",
                project_tree="",
                top_k=8,
                full_context_files=[
                    FullContextFile(
                        source_path=Path(temporary_directory) / "FORMAT_CONTEXT.md",
                        archive_path="FORMAT_CONTEXT.md",
                        content="# FORMAT_CONTEXT.md\n",
                    ),
                    FullContextFile(
                        source_path=Path(temporary_directory) / "PROJECT_CONTEXT.md",
                        archive_path="SBM-SUITE/context/PROJECT_CONTEXT.md",
                        content="# PROJECT_CONTEXT.md\n",
                    ),
                ],
                missing_full_context_files=[],
                contract_version="a" * 64,
                supported_patch_paths=sorted(PATCH_DEFINITIONS),
                canonical_project_path="SBM-SUITE/dp/DP-API",
                lifecycle_phase=request.lifecycle_phase,
                execution_mode=request.execution_mode,
                objectives=[objective],
            )

            with ZipFile(package_path) as archive:
                manifest = json.loads(archive.read("manifest.json"))

        self.assertEqual(manifest["lifecycle_phase"], "objective-activation")
        self.assertEqual(manifest["objectives"], [objective])
        self.assertEqual(manifest["objectives"][0]["status"], "active")

    def test_objective_activation_rejects_pending_requested_status(self):
        with self.assertRaisesRegex(
            ValueError,
            "requested status must be active",
        ):
            ContextExportRequest(
                project_name="dp-api",
                workflow="context-deploy",
                lifecycle_phase="objective-activation",
                objectives=[self._planning_objective()],
            )

    def test_objective_activation_rejects_multiple_objectives(self):
        with self.assertRaisesRegex(ValueError, "requires exactly one objective"):
            ContextExportRequest(
                project_name="dp-api",
                workflow="context-deploy",
                lifecycle_phase="objective-activation",
                objectives=[
                    {**self._planning_objective("OBJ-001"), "status": "active"},
                    {
                        **self._planning_objective("OBJ-002"),
                        "status": "active",
                        "branch": "FEATURE-enable-orders",
                    },
                ],
            )

    def test_progress_rejects_multiple_objectives(self):
        with self.assertRaisesRegex(ValueError, "exactly one objective"):
            ContextExportRequest(
                project_name="dp-api",
                workflow="context-deploy",
                lifecycle_phase="implementation-progress",
                objectives=[
                    {"objective_id": "OBJ-001"},
                    {"objective_id": "OBJ-002"},
                ],
            )

    def test_closure_accepts_not_applicable_qa_at_endpoint(self):
        app = FastAPI()
        app.include_router(router)
        request = self._request("implementation-closure")

        with patch(
            "app.api.routes.contexts.export_contexts",
            return_value=self._closure_response(),
        ) as export_mock:
            response = TestClient(app).post(
                "/contexts/export",
                json=request.model_dump(mode="json"),
            )

        self.assertEqual(response.status_code, 200)
        received = export_mock.call_args.args[0]
        self.assertEqual(received.qa.model_dump(), request.qa.model_dump())
        self.assertTrue(received.qa_results.endswith("\n"))

    def test_closure_accepts_passed_qa_at_endpoint(self):
        evidence = "# QA Results\n\nOverall status: passed\n"
        request = self._request("implementation-closure").model_dump()
        request["qa_results"] = evidence
        request["qa"] = self._qa_decision("passed", True, evidence)
        app = FastAPI()
        app.include_router(router)

        with patch(
            "app.api.routes.contexts.export_contexts",
            return_value=self._closure_response(),
        ):
            response = TestClient(app).post(
                "/contexts/export",
                json=request,
            )

        self.assertEqual(response.status_code, 200)

    def test_closure_rejects_noncanonical_qa_status(self):
        request = self._request("implementation-closure").model_dump()
        request["qa"]["status"] = "success"
        app = FastAPI()
        app.include_router(router)

        response = TestClient(app).post("/contexts/export", json=request)

        self.assertEqual(response.status_code, 422)

    def test_closure_rejects_incoherent_qa_applicability(self):
        request = self._request("implementation-closure").model_dump()
        request["qa"]["applicable"] = True
        app = FastAPI()
        app.include_router(router)

        response = TestClient(app).post("/contexts/export", json=request)

        self.assertEqual(response.status_code, 422)

    def test_progress_remains_valid_without_qa(self):
        request = self._request("implementation-progress")

        self.assertIsNone(request.qa)
        self.assertEqual(request.lifecycle_phase, "implementation-progress")

    def test_closure_qa_is_preserved_in_package_manifest(self):
        evidence = "# QA Results\n\nOverall status: passed\n"
        qa = self._qa_decision("passed", True, evidence)
        with tempfile.TemporaryDirectory() as temporary_directory:
            package_path = create_context_package(
                output_directory=Path(temporary_directory),
                project_name="dp-api",
                query="Close objective.",
                retrieved_chunks=[],
                change_summary="Closure.",
                changed_files=[],
                git_diff="",
                git_log="",
                qa_results=evidence,
                project_tree="",
                top_k=8,
                full_context_files=[
                    FullContextFile(
                        source_path=(
                            Path(temporary_directory) / "FORMAT_CONTEXT.md"
                        ),
                        archive_path="FORMAT_CONTEXT.md",
                        content="# FORMAT_CONTEXT.md\n",
                    ),
                ],
                missing_full_context_files=[],
                contract_version="a" * 64,
                supported_patch_paths=sorted(PATCH_DEFINITIONS),
                canonical_project_path="SBM-SUITE/dp/DP-API",
                lifecycle_phase="implementation-closure",
                execution_mode="evidence",
                objectives=[{"objective_id": "OBJ-001"}],
                qa=qa,
            )

            with ZipFile(package_path) as archive:
                manifest = json.loads(archive.read("manifest.json"))
                packaged_evidence = archive.read("qa-results.md").decode()

        self.assertEqual(manifest["qa"], qa)
        self.assertEqual(packaged_evidence, evidence)

    def test_closure_null_user_prompt_does_not_return_http_422(self):
        app = FastAPI()
        app.include_router(router)
        response_payload = self._closure_response()

        with patch(
            "app.api.routes.contexts.export_contexts",
            return_value=response_payload,
        ):
            response = TestClient(app).post(
                "/contexts/export",
                json=self._request(
                    "implementation-closure",
                    None,
                ).model_dump(),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["lifecycle_phase"],
            "implementation-closure",
        )
        self.assertEqual(response.json()["execution_mode"], "evidence")
        self.assertEqual(
            response.json()["objectives"][0]["objective_id"],
            "OBJ-001",
        )


class ContextContractMappingTests(unittest.TestCase):
    def test_project_tree_evidence_uses_only_canonical_repository_paths(self):
        evidence = (
            "SBM-SUITE/\n"
            "- context/\n"
            "  - project-tree.txt [120 bytes]\n"
            "- sbm/\n"
            "  - sbm-ai-assistant/\n"
        )

        self.assertEqual(
            _validate_project_tree_evidence(evidence),
            evidence.strip(),
        )
        for invalid in (
            "/Users/example/SBM-SUITE/context/project-tree.txt\n",
            "SBM-SUITE/\n- /home/example/context/\n",
            "SBM-SUITE/\n- ../outside/\n",
            "C:\\work\\SBM-SUITE\\context\n",
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(
                    ContextValidationError,
                    "canonical root|repository-relative paths",
                ):
                    _validate_project_tree_evidence(invalid)

    def test_lifecycle_phases_separate_creation_from_existing_activation(self):
        self.assertEqual(
            LIFECYCLE_PHASES,
            (
                "planning-activation",
                "objective-activation",
                "implementation-progress",
                "implementation-closure",
            ),
        )

    def test_runtime_and_repository_paths_are_distinct_and_convertible(self):
        self.assertEqual(canonical_projects()["dp-api"], "SBM-SUITE/dp/DP-API")
        self.assertEqual(
            patch_target_file("patches/project-context.json", "dp-api"),
            "SBM-SUITE/dp/DP-API/context/PROJECT_CONTEXT.md",
        )
        self.assertEqual(
            runtime_to_repository_path(
                "/suite/dp/DP-API/context/PROJECT_CONTEXT.md"
            ),
            "SBM-SUITE/dp/DP-API/context/PROJECT_CONTEXT.md",
        )
        self.assertEqual(
            repository_to_runtime_path(
                "SBM-SUITE/dp/DP-API/context/PROJECT_CONTEXT.md"
            ),
            "/suite/dp/DP-API/context/PROJECT_CONTEXT.md",
        )

    def test_path_converters_reject_mixed_representations(self):
        with self.assertRaises(ProjectRegistryError):
            runtime_to_repository_path("SBM-SUITE/dp/DP-API")
        with self.assertRaises(ProjectRegistryError):
            repository_to_runtime_path("/suite/dp/DP-API")

    def test_all_canonical_projects_use_repository_relative_paths(self):
        self.assertEqual(
            canonical_projects(),
            {
                "dp-api": "SBM-SUITE/dp/DP-API",
                "sbm-ai-assistant": "SBM-SUITE/sbm/sbm-ai-assistant",
                "sbm-api": "SBM-SUITE/sbm/SBM-API",
                "sbm-db": "SBM-SUITE/sbm/SBM-DB",
                "sbm-manager": "SBM-SUITE/sbm/SBM-MANAGER",
                "sbm-suite-context": "SBM-SUITE/context",
            },
        )

    def test_suite_context_uses_only_suite_scoped_patches(self):
        self.assertEqual(
            canonical_projects()["sbm-suite-context"],
            "SBM-SUITE/context",
        )
        self.assertNotIn(
            "patches/project-context.json",
            supported_patch_paths_for_project("sbm-suite-context"),
        )
        self.assertIn(
            "patches/global-project-context.json",
            supported_patch_paths_for_project("sbm-suite-context"),
        )
        with self.assertRaises(ProjectRegistryError):
            patch_target_file(
                "patches/project-context.json",
                "sbm-suite-context",
            )

    def test_concrete_dp_api_project_mappings_are_accepted(self):
        validate_format_context(_valid_format_contract("dp-api"))

    def test_concrete_sbm_api_project_mappings_are_accepted(self):
        validate_format_context(_valid_format_contract("sbm-api"))

    def test_concrete_sbm_ai_assistant_project_mappings_are_accepted(self):
        validate_format_context(_valid_format_contract("sbm-ai-assistant"))

    def test_concrete_sbm_manager_project_mappings_are_accepted(self):
        validate_format_context(_valid_format_contract("sbm-manager"))

    def test_concrete_sbm_db_project_mappings_are_accepted(self):
        validate_format_context(_valid_format_contract("sbm-db"))

    def test_incorrect_project_mapping_is_rejected(self):
        contract = _valid_format_contract("dp-api").replace(
            "SBM-SUITE/dp/DP-API/context/PROJECT_CONTEXT.md",
            "SBM-SUITE/dp/WRONG/context/PROJECT_CONTEXT.md",
        )

        with self.assertRaisesRegex(
            ValueError,
            "patch mapping diverges from backend",
        ):
            validate_format_context(contract)

    def test_internal_placeholders_are_resolved_before_comparison(self):
        definition = PATCH_DEFINITIONS["patches/project-context.json"]
        self.assertIn("{project}", definition.target_template)

        validate_format_context(_valid_format_contract("dp-api"))


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
                    "/suite/dp/DP-API/context/PROJECT_CONTEXT.md"
                ),
                "archive_path": (
                    "SBM-SUITE/dp/DP-API/context/"
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
                "project_path": "dp/DP-API",
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
        self.assertLessEqual(len(chunks), 4)
        self.assertEqual(chunks[0].score, 0.97)
        self.assertEqual(
            chunks[0].archive_path,
            "SBM-SUITE/dp/DP-API/context/PROJECT_CONTEXT.md",
        )
        self.assertEqual(chunks[0].content, "Reglas del proyecto.")


class ContextIndexTests(unittest.TestCase):
    def test_obsolete_dp_paths_are_deactivated(self):
        source = ContextSource(
            source_path=Path("/suite/dp/DP-API/README.md"),
            archive_path="SBM-SUITE/dp/DP-API/README.md",
            context_type="project_readme",
            repository="DP-API",
            legacy_source_path="dp/DP-API/README.md",
        )
        obsolete_points = [SimpleNamespace(id="obsolete-point")]

        with (
            patch(
                "app.services.contexts.context_index_service."
                "scroll_all_points",
                return_value=obsolete_points,
            ) as scroll_mock,
            patch(
                "app.services.contexts.context_index_service."
                "deactivate_points",
            ) as deactivate_mock,
        ):
            _deactivate_obsolete_path_points(source, "dp-api")

        filtered_paths = {
            condition.key: condition.match.value
            for call in scroll_mock.call_args_list
            for condition in call.kwargs["scroll_filter"].must
            if condition.key in {"source_path", "archive_path"}
        }
        self.assertEqual(
            filtered_paths,
            {
                "source_path": "/suite/DP-API/README.md",
                "archive_path": "SBM-SUITE/dp-api/README.md",
            },
        )
        self.assertEqual(deactivate_mock.call_count, 2)
        self.assertTrue(
            all(
                call.kwargs["point_ids"] == ["obsolete-point"]
                for call in deactivate_mock.call_args_list
            )
        )

    def test_embeddings_are_generated_in_one_batch_per_source(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_path = Path(temporary_directory) / "README.md"
            markdown = "# One\nText\n\n# Two\nMore text"
            source_path.write_text(markdown, encoding="utf-8")
            source = ContextSource(
                source_path=source_path,
                archive_path="SBM-SUITE/dp/DP-API/README.md",
                context_type="project_readme",
                repository="DP-API",
                legacy_source_path="dp/DP-API/README.md",
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
                archive_path="SBM-SUITE/dp/DP-API/README.md",
                context_type="project_readme",
                repository="DP-API",
                legacy_source_path="dp/DP-API/README.md",
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
                    "archive_path": "SBM-SUITE/context/README.md",
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
                archive_path="SBM-SUITE/dp/DP-API/README.md",
                context_type="project_readme",
                repository="DP-API",
                legacy_source_path="dp/DP-API/README.md",
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
                    "brand",
                    "project_path",
                }
                self.assertTrue(required_metadata.issubset(payload))
                self.assertEqual(payload["workflow"], "context-deploy")
                self.assertEqual(payload["brand"], "dp")
                self.assertEqual(payload["project_path"], "dp/DP-API")
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
    def test_missing_mandatory_full_target_blocks_export(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            suite_root = Path(temporary_directory) / "SBM-SUITE"
            project_root = suite_root / "dp" / "DP-API"
            _write_markdown(suite_root / "context/README.md", "Suite")
            _write_markdown(
                suite_root / "context/FORMAT_CONTEXT.md",
                "Format",
            )
            _write_markdown(project_root / "README.md", "Project")

            request = ContextExportRequest(
                project_name="dp-api",
                workflow="context-deploy",
                lifecycle_phase="implementation-progress",
                objectives=[{"objective_id": "OBJ-001"}],
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
                with self.assertRaisesRegex(
                    ContextValidationError,
                    "Missing mandatory full target files",
                ):
                    _export_contexts_at(request, suite_root)


class ProjectAllowlistTests(unittest.TestCase):
    def test_all_allowlisted_projects_resolve_with_brand_paths(self):
        projects = (
            ("dp-api", "dp", "DP-API"),
            ("sbm-api", "sbm", "SBM-API"),
            ("sbm-db", "sbm", "SBM-DB"),
            ("sbm-manager", "sbm", "SBM-MANAGER"),
            ("sbm-ai-assistant", "sbm", "sbm-ai-assistant"),
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            suite_root = Path(temporary_directory) / "suite"
            context_root = suite_root / "context"
            output_root = context_root / "output"
            output_root.mkdir(parents=True)
            for source_path, _ in GLOBAL_SOURCE_FILES:
                _write_markdown(suite_root / source_path, source_path)

            for project_name, brand, directory_name in projects:
                project_root = suite_root / brand / directory_name
                for relative_path in PROJECT_FILES:
                    _write_markdown(project_root / relative_path, relative_path)

                safe_name, paths = validate_export_paths(
                    project_name=project_name,
                    project_root=str(project_root),
                    source_context_root=str(context_root),
                    format_context_path=str(context_root / "FORMAT_CONTEXT.md"),
                    output_directory=str(output_root / project_name),
                )
                sources, errors = discover_context_sources(safe_name, paths)
                self.assertEqual(errors, [])
                self.assertIn(
                    f"SBM-SUITE/{brand}/{directory_name}/README.md",
                    {source.archive_path for source in sources},
                )

    def test_suite_context_resolves_without_project_local_sources(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            suite_root = Path(temporary_directory) / "suite"
            context_root = suite_root / "context"
            output_root = context_root / "output"
            output_root.mkdir(parents=True)
            for source_path, _ in GLOBAL_SOURCE_FILES:
                _write_markdown(suite_root / source_path, source_path)

            safe_name, paths = validate_export_paths(
                project_name="sbm-suite-context",
                project_root=str(context_root),
                source_context_root=str(context_root),
                format_context_path=str(context_root / "FORMAT_CONTEXT.md"),
                output_directory=str(output_root / "sbm-suite-context"),
            )
            sources, errors = discover_context_sources(safe_name, paths)

            self.assertEqual(errors, [])
            archive_paths = {source.archive_path for source in sources}
            self.assertIn(
                "SBM-SUITE/context/PROJECT_CONTEXT.md",
                archive_paths,
            )
            self.assertFalse(
                any("/context/context/" in path for path in archive_paths)
            )

    def test_project_path_from_another_allowlisted_project_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            suite_root = Path(temporary_directory) / "suite"
            context_root = suite_root / "context"
            wrong_project = suite_root / "sbm" / "SBM-API"
            wrong_project.mkdir(parents=True)
            context_root.mkdir(parents=True)
            _write_markdown(context_root / "FORMAT_CONTEXT.md", "Format")

            with self.assertRaisesRegex(
                ContextValidationError,
                "does not match the project allowlist",
            ):
                validate_export_paths(
                    project_name="dp-api",
                    project_root=str(wrong_project),
                    source_context_root=str(context_root),
                    format_context_path=str(context_root / "FORMAT_CONTEXT.md"),
                    output_directory=str(context_root / "output"),
                )


if __name__ == "__main__":
    unittest.main()
