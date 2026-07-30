from __future__ import annotations

import hashlib
import json
import stat
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo

from app.services.contexts.file_discovery_service import (
    ContextValidationError,
)
from app.services.documentation.documentation_upgrade_service import (
    DocumentationUpgradeOperationalError,
    upgrade_documentation,
)


ARCHITECTURE = "documentation/architecture.md"
BUSINESS = "documentation/business.md"
DATA_ARCHITECTURE = "documentation/data-architecture.md"
SECURITY_DEVSECOPS = "documentation/security-devsecops.md"
DEVOPS_DEPLOYMENT = "documentation/devops-deployment.md"
QA_TESTING = "documentation/qa-testing.md"
AI_ENGINEERING = "documentation/ai-engineering.md"
ROADMAP = "documentation/roadmap.md"

EXECUTIVE_README = "EXECUTIVE_README.md"
COMMIT_MESSAGE = "COMMIT_MESSAGE.md"
USER_PROMPT = "USER_PROMPT.md"


def _write(
    path: Path,
    content: str,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    path.write_text(
        content,
        encoding="utf-8",
    )


def _valid_document(
    title: str,
    marker: str,
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


class UpgradeEnvironment:
    def __init__(
        self,
        root: Path,
    ) -> None:
        self.documentation_root = (
            root
            / "context"
            / "documentation"
        )
        self.input_directory = (
            self.documentation_root
            / "input"
        )
        self.backup_root = (
            self.documentation_root
            / "backup"
        )

        self.input_directory.mkdir(
            parents=True
        )
        self.backup_root.mkdir(
            parents=True
        )

        self.targets = {
            ARCHITECTURE: (
                self.documentation_root
                / "architecture.md"
            ),
            BUSINESS: (
                self.documentation_root
                / "business.md"
            ),
            DATA_ARCHITECTURE: (
                self.documentation_root
                / "data-architecture.md"
            ),
            SECURITY_DEVSECOPS: (
                self.documentation_root
                / "security-devsecops.md"
            ),
            DEVOPS_DEPLOYMENT: (
                self.documentation_root
                / "devops-deployment.md"
            ),
            QA_TESTING: (
                self.documentation_root
                / "qa-testing.md"
            ),
            AI_ENGINEERING: (
                self.documentation_root
                / "ai-engineering.md"
            ),
            ROADMAP: (
                self.documentation_root
                / "roadmap.md"
            ),
        }

        for archive_path, target in (
            self.targets.items()
        ):
            _write(
                target,
                _valid_document(
                    target.stem,
                    f"old:{archive_path}",
                ),
            )

        _write(
            self.documentation_root
            / "FORMAT_CONTEXT.md",
            _valid_document(
                "FORMAT_CONTEXT.md",
                "Protected format.",
            ),
        )
        _write(
            self.documentation_root
            / "SYS_PROMPT.md",
            _valid_document(
                "SYS_PROMPT.md",
                "Protected prompt.",
            ),
        )

    @property
    def zip_path(self) -> Path:
        return (
            self.input_directory
            / "documentation-upgrade.zip"
        )

    def run(self):
        return upgrade_documentation(
            input_directory=str(
                self.input_directory
            ),
            documentation_root=str(
                self.documentation_root
            ),
            backup_root=str(
                self.backup_root
            ),
            now=lambda: datetime(
                2026,
                7,
                30,
                10,
                11,
                12,
            ),
        )


def _create_upgrade_zip(
    path: Path,
    files: dict[str, str],
    updated_files: list[str],
    manifest_updates: dict | None = None,
) -> None:
    manifest = {
        "project_name": "dp-api",
        "workflow": "documentation-upgrade",
        "execution_mode": "evidence",
        "user_prompt_file": None,
        "output_filename": (
            "documentation-upgrade.zip"
        ),
        "documentation_root": "documentation",
        "allowed_files": [
            *files,
            "manifest.json",
        ],
        "updated_files": updated_files,
        "content_hashes": {
            name: hashlib.sha256(
                content.encode("utf-8")
            ).hexdigest()
            for name, content
            in files.items()
        },
        "commit": {
            "type": "docs",
            "scope": "documentation",
            "subject": (
                "update project documentation"
            ),
        },
        "rag": {
            "collection_name": (
                "sbm_documentation"
            ),
            "retrieved_chunk_count": 4,
        },
        "evidence": {
            "git_diff": True,
            "git_log": True,
            "qa_results": True,
            "project_tree": True,
        },
    }

    if manifest_updates:
        manifest.update(
            manifest_updates
        )

    with ZipFile(
        path,
        mode="w",
    ) as archive:
        for name, content in files.items():
            archive.writestr(
                name,
                content,
            )

        archive.writestr(
            "manifest.json",
            json.dumps(
                manifest,
                ensure_ascii=False,
            ),
        )


class DocumentationUpgradeTests(
    unittest.TestCase
):
    def test_valid_zip_creates_backup_replaces_and_cleans_input(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp:
            environment = UpgradeEnvironment(
                Path(temp)
            )
            old_mode = stat.S_IMODE(
                environment.targets[
                    ARCHITECTURE
                ].stat().st_mode
            )
            files = {
                ARCHITECTURE: (
                    _valid_document(
                        "Architecture",
                        "Updated architecture.",
                    )
                ),
                EXECUTIVE_README: (
                    "Documentation upgrade summary"
                ),
                COMMIT_MESSAGE: (
                    "docs(documentation): "
                    "update architecture"
                ),
            }

            _create_upgrade_zip(
                environment.zip_path,
                files,
                list(files),
            )

            response = environment.run()

            self.assertEqual(
                response.project_name,
                "dp-api",
            )
            self.assertEqual(
                response.workflow,
                "documentation-upgrade",
            )
            self.assertTrue(
                response.input_cleaned
            )
            self.assertFalse(
                environment.zip_path.exists()
            )
            self.assertEqual(
                environment.targets[
                    ARCHITECTURE
                ].read_text(
                    encoding="utf-8"
                ),
                files[ARCHITECTURE],
            )
            self.assertEqual(
                stat.S_IMODE(
                    environment.targets[
                        ARCHITECTURE
                    ].stat().st_mode
                ),
                old_mode,
            )

            backup = Path(
                response.backup_directory
            )

            self.assertEqual(
                backup.name,
                (
                    "20260730_101112_000000_"
                    "dp-api"
                ),
            )
            self.assertTrue(
                (
                    backup
                    / "previous"
                    / ARCHITECTURE
                ).is_file()
            )
            self.assertTrue(
                (
                    backup
                    / "applied"
                    / ARCHITECTURE
                ).is_file()
            )
            self.assertTrue(
                (
                    backup
                    / EXECUTIVE_README
                ).is_file()
            )
            self.assertTrue(
                (
                    backup
                    / COMMIT_MESSAGE
                ).is_file()
            )
            self.assertTrue(
                (
                    backup
                    / "manifest.json"
                ).is_file()
            )

    def test_user_guided_zip_accepts_prompt(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp:
            environment = UpgradeEnvironment(
                Path(temp)
            )
            files = {
                ROADMAP: _valid_document(
                    "Roadmap",
                    "Updated roadmap.",
                ),
                USER_PROMPT: (
                    "Update only the validated "
                    "roadmap section."
                ),
            }

            _create_upgrade_zip(
                environment.zip_path,
                files,
                list(files),
                manifest_updates={
                    "execution_mode": (
                        "user-guided"
                    ),
                    "user_prompt_file": (
                        USER_PROMPT
                    ),
                },
            )

            response = environment.run()
            backup = Path(
                response.backup_directory
            )

            self.assertTrue(
                response.input_cleaned
            )
            self.assertEqual(
                (
                    backup
                    / USER_PROMPT
                ).read_text(
                    encoding="utf-8"
                ),
                files[USER_PROMPT],
            )

    def test_user_prompt_is_rejected_in_evidence_mode(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp:
            environment = UpgradeEnvironment(
                Path(temp)
            )
            _create_upgrade_zip(
                environment.zip_path,
                {
                    ARCHITECTURE: (
                        _valid_document(
                            "Architecture",
                            "Updated.",
                        )
                    ),
                    USER_PROMPT: "Prompt",
                },
                [
                    ARCHITECTURE,
                    USER_PROMPT,
                ],
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "USER_PROMPT.md is not allowed",
            ):
                environment.run()

    def test_user_guided_mode_requires_prompt_file(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp:
            environment = UpgradeEnvironment(
                Path(temp)
            )
            _create_upgrade_zip(
                environment.zip_path,
                {
                    ARCHITECTURE: (
                        _valid_document(
                            "Architecture",
                            "Updated.",
                        )
                    )
                },
                [ARCHITECTURE],
                manifest_updates={
                    "execution_mode": (
                        "user-guided"
                    ),
                    "user_prompt_file": (
                        USER_PROMPT
                    ),
                },
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "USER_PROMPT.md is required",
            ):
                environment.run()

    def test_absent_zip_is_rejected(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp:
            environment = UpgradeEnvironment(
                Path(temp)
            )

            with self.assertRaises(
                ContextValidationError
            ):
                environment.run()

    def test_multiple_zips_are_rejected(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp:
            environment = UpgradeEnvironment(
                Path(temp)
            )
            environment.zip_path.write_bytes(
                b"one"
            )
            (
                environment.input_directory
                / "other.zip"
            ).write_bytes(
                b"two"
            )

            with self.assertRaises(
                ContextValidationError
            ):
                environment.run()

    def test_wrong_zip_name_is_rejected(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp:
            environment = UpgradeEnvironment(
                Path(temp)
            )
            (
                environment.input_directory
                / "other.zip"
            ).write_bytes(
                b"zip"
            )

            with self.assertRaises(
                ContextValidationError
            ):
                environment.run()

    def test_corrupt_zip_is_rejected_and_retained(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp:
            environment = UpgradeEnvironment(
                Path(temp)
            )
            environment.zip_path.write_bytes(
                b"not-a-zip"
            )

            with self.assertRaises(
                ContextValidationError
            ):
                environment.run()

            self.assertTrue(
                environment.zip_path.exists()
            )

    def test_path_traversal_is_rejected(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp:
            environment = UpgradeEnvironment(
                Path(temp)
            )

            with ZipFile(
                environment.zip_path,
                "w",
            ) as archive:
                archive.writestr(
                    "../escape.md",
                    "unsafe",
                )
                archive.writestr(
                    "manifest.json",
                    "{}",
                )

            with self.assertRaises(
                ContextValidationError
            ):
                environment.run()

            self.assertFalse(
                (
                    Path(temp)
                    / "escape.md"
                ).exists()
            )

    def test_zip_symlink_is_rejected(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp:
            environment = UpgradeEnvironment(
                Path(temp)
            )
            symlink = ZipInfo(
                ARCHITECTURE
            )
            symlink.create_system = 3
            symlink.external_attr = (
                stat.S_IFLNK | 0o777
            ) << 16

            with ZipFile(
                environment.zip_path,
                "w",
            ) as archive:
                archive.writestr(
                    symlink,
                    "architecture.md",
                )
                archive.writestr(
                    "manifest.json",
                    "{}",
                )

            with self.assertRaises(
                ContextValidationError
            ):
                environment.run()

    def test_missing_manifest_is_rejected(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp:
            environment = UpgradeEnvironment(
                Path(temp)
            )

            with ZipFile(
                environment.zip_path,
                "w",
            ) as archive:
                archive.writestr(
                    ARCHITECTURE,
                    _valid_document(
                        "Architecture",
                        "Updated.",
                    ),
                )

            with self.assertRaises(
                ContextValidationError
            ):
                environment.run()

    def test_protected_format_file_is_rejected(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp:
            environment = UpgradeEnvironment(
                Path(temp)
            )
            protected = (
                "documentation/"
                "FORMAT_CONTEXT.md"
            )
            _create_upgrade_zip(
                environment.zip_path,
                {
                    protected: (
                        _valid_document(
                            "FORMAT_CONTEXT.md",
                            "Forbidden.",
                        )
                    )
                },
                [protected],
            )

            with self.assertRaises(
                ContextValidationError
            ):
                environment.run()

    def test_protected_system_prompt_is_rejected(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp:
            environment = UpgradeEnvironment(
                Path(temp)
            )
            protected = (
                "documentation/"
                "SYS_PROMPT.md"
            )
            _create_upgrade_zip(
                environment.zip_path,
                {
                    protected: (
                        _valid_document(
                            "SYS_PROMPT.md",
                            "Forbidden.",
                        )
                    )
                },
                [protected],
            )

            with self.assertRaises(
                ContextValidationError
            ):
                environment.run()

    def test_non_markdown_file_is_rejected(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp:
            environment = UpgradeEnvironment(
                Path(temp)
            )
            invalid = (
                "documentation/"
                "architecture.txt"
            )
            _create_upgrade_zip(
                environment.zip_path,
                {invalid: "invalid"},
                [invalid],
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "must use .md",
            ):
                environment.run()

    def test_hash_mismatch_is_rejected(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp:
            environment = UpgradeEnvironment(
                Path(temp)
            )
            content = _valid_document(
                "Architecture",
                "Updated.",
            )
            _create_upgrade_zip(
                environment.zip_path,
                {ARCHITECTURE: content},
                [ARCHITECTURE],
                manifest_updates={
                    "content_hashes": {
                        ARCHITECTURE: (
                            "0" * 64
                        )
                    }
                },
            )

            with self.assertRaises(
                ContextValidationError
            ):
                environment.run()

    def test_manifest_updated_files_must_match_zip(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp:
            environment = UpgradeEnvironment(
                Path(temp)
            )
            _create_upgrade_zip(
                environment.zip_path,
                {
                    ARCHITECTURE: (
                        _valid_document(
                            "Architecture",
                            "Updated.",
                        )
                    )
                },
                [BUSINESS],
            )

            with self.assertRaises(
                ContextValidationError
            ):
                environment.run()

    def test_information_only_zip_is_rejected(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp:
            environment = UpgradeEnvironment(
                Path(temp)
            )
            _create_upgrade_zip(
                environment.zip_path,
                {
                    EXECUTIVE_README: (
                        "Executive"
                    ),
                    COMMIT_MESSAGE: (
                        "docs: report"
                    ),
                },
                [
                    EXECUTIVE_README,
                    COMMIT_MESSAGE,
                ],
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "at least one documentation file",
            ):
                environment.run()

    def test_missing_metadata_is_rejected(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp:
            environment = UpgradeEnvironment(
                Path(temp)
            )
            invalid = (
                "# Architecture\n\n"
                "## Overview\n\n"
                "Updated.\n\n"
                "## Document boundary\n\n"
                "Boundary.\n"
            )
            _create_upgrade_zip(
                environment.zip_path,
                {ARCHITECTURE: invalid},
                [ARCHITECTURE],
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "metadata is missing",
            ):
                environment.run()

    def test_multiple_level_one_headings_are_rejected(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp:
            environment = UpgradeEnvironment(
                Path(temp)
            )
            invalid = (
                _valid_document(
                    "Architecture",
                    "Updated.",
                )
                + "\n# Duplicate title\n"
            )
            _create_upgrade_zip(
                environment.zip_path,
                {ARCHITECTURE: invalid},
                [ARCHITECTURE],
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "exactly one level-one heading",
            ):
                environment.run()

    def test_missing_document_boundary_is_rejected(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp:
            environment = UpgradeEnvironment(
                Path(temp)
            )
            invalid = _valid_document(
                "Architecture",
                "Updated.",
            ).replace(
                "## Document boundary",
                "## Scope",
            )
            _create_upgrade_zip(
                environment.zip_path,
                {ARCHITECTURE: invalid},
                [ARCHITECTURE],
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "document boundary",
            ):
                environment.run()

    def test_all_authorized_documentation_files_can_be_replaced(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp:
            environment = UpgradeEnvironment(
                Path(temp)
            )
            files = {
                archive_path: (
                    _valid_document(
                        Path(
                            archive_path
                        ).stem,
                        f"updated:{archive_path}",
                    )
                )
                for archive_path
                in environment.targets
            }

            _create_upgrade_zip(
                environment.zip_path,
                files,
                list(files),
            )

            response = environment.run()

            self.assertEqual(
                response.updated_files,
                list(files),
            )

            for archive_path, content in (
                files.items()
            ):
                self.assertEqual(
                    environment.targets[
                        archive_path
                    ].read_text(
                        encoding="utf-8"
                    ),
                    content,
                )

    def test_partial_update_replaces_only_selected_file(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp:
            environment = UpgradeEnvironment(
                Path(temp)
            )
            original_business = (
                environment.targets[
                    BUSINESS
                ].read_text(
                    encoding="utf-8"
                )
            )
            updated_architecture = (
                _valid_document(
                    "Architecture",
                    "Updated architecture.",
                )
            )

            _create_upgrade_zip(
                environment.zip_path,
                {
                    ARCHITECTURE: (
                        updated_architecture
                    )
                },
                [ARCHITECTURE],
            )

            response = environment.run()

            self.assertEqual(
                environment.targets[
                    ARCHITECTURE
                ].read_text(
                    encoding="utf-8"
                ),
                updated_architecture,
            )
            self.assertEqual(
                environment.targets[
                    BUSINESS
                ].read_text(
                    encoding="utf-8"
                ),
                original_business,
            )

            backup = Path(
                response.backup_directory
            )
            self.assertFalse(
                (
                    backup
                    / "previous"
                    / BUSINESS
                ).exists()
            )

    def test_replacement_failure_rolls_back_and_retains_input(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp:
            environment = UpgradeEnvironment(
                Path(temp)
            )
            original_architecture = (
                environment.targets[
                    ARCHITECTURE
                ].read_text(
                    encoding="utf-8"
                )
            )
            original_business = (
                environment.targets[
                    BUSINESS
                ].read_text(
                    encoding="utf-8"
                )
            )

            _create_upgrade_zip(
                environment.zip_path,
                {
                    ARCHITECTURE: (
                        _valid_document(
                            "Architecture",
                            "Updated architecture.",
                        )
                    ),
                    BUSINESS: (
                        _valid_document(
                            "Business",
                            "Updated business.",
                        )
                    ),
                },
                [
                    ARCHITECTURE,
                    BUSINESS,
                ],
            )

            from app.services.documentation import (
                documentation_upgrade_service,
            )

            original_replace = (
                documentation_upgrade_service.
                _atomic_replace_file
            )

            def fail_second(
                source: Path,
                target: Path,
            ):
                if (
                    target
                    == environment.targets[
                        BUSINESS
                    ].resolve()
                    and "previous"
                    not in source.parts
                ):
                    raise OSError(
                        "simulated failure"
                    )

                return original_replace(
                    source,
                    target,
                )

            with patch(
                "app.services.documentation."
                "documentation_upgrade_service."
                "_atomic_replace_file",
                side_effect=fail_second,
            ):
                with self.assertRaises(
                    DocumentationUpgradeOperationalError
                ):
                    environment.run()

            self.assertEqual(
                environment.targets[
                    ARCHITECTURE
                ].read_text(
                    encoding="utf-8"
                ),
                original_architecture,
            )
            self.assertEqual(
                environment.targets[
                    BUSINESS
                ].read_text(
                    encoding="utf-8"
                ),
                original_business,
            )
            self.assertTrue(
                environment.zip_path.exists()
            )


if __name__ == "__main__":
    unittest.main()
