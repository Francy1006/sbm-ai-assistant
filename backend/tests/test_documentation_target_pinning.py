from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.schemas.documentation import DocumentationExportRequest
from app.services.contexts.file_discovery_service import (
    ContextValidationError,
)
from app.services.documentation.documentation_export_service import (
    export_documentation,
)
from app.services.documentation.documentation_retrieval_service import (
    retrieve_relevant_documentation_chunks,
)


class DocumentationTargetPinningTests(unittest.TestCase):
    def test_required_documentation_target_is_pinned_into_top_k(
        self,
    ):
        devops_points = [
            SimpleNamespace(
                id=f"devops-{index}",
                score=0.99 - (index * 0.01),
                payload={
                    "source_path": "/docs/devops.md",
                    "archive_path": (
                        "documentation/pages/devops.md"
                    ),
                    "section": f"Section {index}",
                    "text": f"DevOps chunk {index}",
                },
            )
            for index in range(8)
        ]
        suite_target = SimpleNamespace(
            id="suite-target",
            score=0.50,
            payload={
                "source_path": "/docs/sbm-suite.md",
                "archive_path": (
                    "documentation/pages/sbm-suite.md"
                ),
                "section": "Architecture",
                "text": "SBM Suite architecture.",
            },
        )

        with (
            patch(
                "app.services.documentation."
                "documentation_retrieval_service."
                "create_embedding",
                return_value=[0.1, 0.2],
            ),
            patch(
                "app.services.documentation."
                "documentation_retrieval_service."
                "search_similar",
                side_effect=[
                    devops_points,
                    [],
                    [suite_target],
                    [],
                ],
            ),
        ):
            chunks = retrieve_relevant_documentation_chunks(
                project_name="sbm-db",
                query=(
                    "Enable SBM-DB and update the "
                    "SBM-Suite diagram"
                ),
                top_k=8,
                allowed_archive_paths=[
                    "documentation/pages/devops.md",
                    "documentation/pages/sbm-suite.md",
                ],
                required_archive_paths=[
                    "documentation/pages/sbm-suite.md",
                ],
            )

        self.assertEqual(len(chunks), 8)
        self.assertTrue(
            any(
                chunk.archive_path
                == "documentation/pages/sbm-suite.md"
                for chunk in chunks
            )
        )

    def test_request_rejects_duplicate_documentation_targets(
        self,
    ):
        with self.assertRaises(ValueError):
            DocumentationExportRequest(
                project_name="sbm-db",
                workflow="documentation-deploy",
                documentation_targets=[
                    "documentation/pages/sbm-suite.md",
                    "documentation/pages/sbm-suite.md",
                ],
            )

    def test_export_rejects_unknown_documentation_target(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            suite_root = root / "SBM-SUITE"
            project_root = suite_root / "sbm" / "SBM-DB"
            documentation_root = (
                suite_root / "context" / "documentation"
            )
            output_directory = documentation_root / "output"
            pages = documentation_root / "pages"
            project_root.mkdir(parents=True)
            output_directory.mkdir(parents=True)
            pages.mkdir(parents=True)

            (documentation_root / "FORMAT_CONTEXT.md").write_text(
                "# FORMAT_CONTEXT.md\n",
                encoding="utf-8",
            )
            (documentation_root / "SYS_PROMPT.md").write_text(
                "# SYS_PROMPT.md\n\nProject {{PROJECT_NAME}}\n",
                encoding="utf-8",
            )
            (pages / "devops.md").write_text(
                "# DevOps\n\n## Overview\n\nCurrent.\n",
                encoding="utf-8",
            )

            request = DocumentationExportRequest(
                project_name="sbm-db",
                workflow="documentation-deploy",
                changed_files=[],
                git_diff="",
                qa_results="",
                documentation_targets=[
                    "documentation/pages/sbm-suite.md"
                ],
            )

            with (
                patch(
                    "app.services.documentation."
                    "documentation_export_service."
                    "index_documentation_source",
                    side_effect=lambda **kwargs: len(
                        kwargs["chunks"]
                    ),
                ),
                patch(
                    "app.services.documentation."
                    "documentation_export_service."
                    "DOCUMENTATION_UPGRADE_DOCUMENTATION_ROOT",
                    str(documentation_root),
                ),
            ):
                with self.assertRaises(ContextValidationError):
                    export_documentation(request)


if __name__ == "__main__":
    unittest.main()
