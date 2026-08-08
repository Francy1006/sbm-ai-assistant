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

from app.services.contexts.file_discovery_service import ContextValidationError
from app.services.documentation.documentation_upgrade_service import (
    DocumentationUpgradeOperationalError,
    upgrade_documentation,
)


ARCHITECTURE = "documentation/architecture.md"
BUSINESS = "documentation/business.md"
ROADMAP = "documentation/roadmap.md"

EXECUTIVE_README = "EXECUTIVE_README.md"
COMMIT_MESSAGE = "COMMIT_MESSAGE.md"
USER_PROMPT = "USER_PROMPT.md"

MAIN_PAGE_HEADINGS = [
    "## 1. Overview",
    "## 2. Scope",
    "## 3. Current state",
    "## 4. Core concepts",
    "## 5. Architecture or operating model",
    "## 6. Components",
    "## 7. Workflows",
    "## 8. Configuration",
    "## 9. Security",
    "## 10. Validation",
    "## 11. Known limitations",
    "## 12. Roadmap",
    "## 13. Related pages",
    "## 14. Subpages",
    "## 15. Document boundary",
]


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _valid_document(title: str, marker: str) -> str:
    blocks = [
        f"# {title}",
        (
            "> **Last updated:** 2026-07-30\n"
            ">\n"
            "> **Purpose:**\n"
            ">\n"
            "> Test documentation fixture\n"
            ">\n"
            "> **Source of truth:**\n"
            ">\n"
            "> Git Markdown and validated evidence"
        ),
    ]

    for heading in MAIN_PAGE_HEADINGS:
        blocks.append(heading)
        blocks.append(
            marker if heading == "## 3. Current state"
            else f"Validated content for {heading}."
        )

    return "\n\n".join(blocks) + "\n"


class UpgradeEnvironment:
    def __init__(self, root: Path) -> None:
        self.documentation_root = root / "context" / "documentation"
        self.input_directory = self.documentation_root / "input"
        self.backup_root = self.documentation_root.parent / "backup"

        self.input_directory.mkdir(parents=True)
        self.backup_root.mkdir(parents=True)

        self.targets = {
            ARCHITECTURE: self.documentation_root / "architecture.md",
            BUSINESS: self.documentation_root / "business.md",
            ROADMAP: self.documentation_root / "roadmap.md",
        }

        for archive_path, target in self.targets.items():
            _write(
                target,
                _valid_document(target.stem, f"old:{archive_path}"),
            )

        _write(
            self.documentation_root / "FORMAT_CONTEXT.md",
            "# FORMAT_CONTEXT.md\n",
        )
        _write(
            self.documentation_root / "SYS_PROMPT.md",
            "# SYS_PROMPT.md\n\n{{PROJECT_NAME}}\n",
        )

    @property
    def zip_path(self) -> Path:
        return self.input_directory / "documentation-upgrade.zip"

    def run(self):
        return upgrade_documentation(
            input_directory=str(self.input_directory),
            documentation_root=str(self.documentation_root),
            backup_root=str(self.backup_root),
            now=lambda: datetime(2026, 7, 30, 10, 11, 12),
        )


def _create_upgrade_zip(
    path: Path,
    documentation_files: dict[str, str],
    *,
    execution_mode: str = "evidence",
    user_prompt: str | None = None,
    manifest_updates: dict | None = None,
) -> None:
    files = {
        EXECUTIVE_README: "Documentation upgrade summary\n",
        COMMIT_MESSAGE: (
            "docs(documentation): update project documentation\n"
        ),
        **documentation_files,
    }

    if user_prompt is not None:
        files[USER_PROMPT] = user_prompt

    manifest = {
        "project_name": "dp-api",
        "workflow": "documentation-upgrade",
        "execution_mode": execution_mode,
        "user_prompt_file": USER_PROMPT if user_prompt is not None else None,
        "output_filename": "documentation-upgrade.zip",
        "documentation_root": "documentation",
        "allowed_files": [*files, "manifest.json"],
        "updated_files": list(files),
        "content_hashes": {
            name: hashlib.sha256(content.encode("utf-8")).hexdigest()
            for name, content in files.items()
        },
        "commit": {
            "type": "docs",
            "scope": "documentation",
            "subject": "update project documentation",
            "message_file": COMMIT_MESSAGE,
        },
        "rag": {
            "collection_name": "sbm_documentation",
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
        manifest.update(manifest_updates)

    with ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
        archive.writestr("manifest.json", json.dumps(manifest))


class DocumentationUpgradeTests(unittest.TestCase):
    def test_project_name_outside_allowlist_is_rejected_and_retained(self):
        with tempfile.TemporaryDirectory() as temp:
            env = UpgradeEnvironment(Path(temp))
            _create_upgrade_zip(
                env.zip_path,
                {ARCHITECTURE: _valid_document("Architecture", "Updated.")},
                manifest_updates={"project_name": "../other-project"},
            )
            with self.assertRaisesRegex(
                ContextValidationError,
                "project_name must be one of",
            ):
                env.run()
            self.assertTrue(env.zip_path.exists())

    def test_valid_zip_creates_backup_replaces_and_cleans_input(self):
        with tempfile.TemporaryDirectory() as temp:
            env = UpgradeEnvironment(Path(temp))
            target = env.targets[ARCHITECTURE]
            old_mode = stat.S_IMODE(target.stat().st_mode)
            updated = _valid_document("Architecture", "Updated architecture.")

            _create_upgrade_zip(env.zip_path, {ARCHITECTURE: updated})
            response = env.run()

            self.assertEqual(response.project_name, "dp-api")
            self.assertEqual(response.workflow, "documentation-upgrade")
            self.assertEqual(
                response.updated_files,
                [EXECUTIVE_README, COMMIT_MESSAGE, ARCHITECTURE],
            )
            self.assertTrue(response.input_cleaned)
            self.assertFalse(env.zip_path.exists())
            self.assertEqual(target.read_text(encoding="utf-8"), updated)
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), old_mode)

            backup = Path(response.backup_directory)
            self.assertTrue((backup / "previous" / ARCHITECTURE).is_file())
            self.assertTrue((backup / "applied" / ARCHITECTURE).is_file())
            self.assertTrue((backup / EXECUTIVE_README).is_file())
            self.assertTrue((backup / COMMIT_MESSAGE).is_file())
            self.assertTrue((backup / "manifest.json").is_file())
            backup_manifest = json.loads(
                (backup / "BACKUP_MANIFEST.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                backup_manifest["workflow"],
                "documentation-upgrade",
            )
            self.assertEqual(
                [item["archive_path"] for item in backup_manifest["backed_up_files"]],
                [ARCHITECTURE],
            )
            self.assertFalse((env.documentation_root / "backup").exists())

    def test_multiple_documentation_files_can_be_replaced(self):
        with tempfile.TemporaryDirectory() as temp:
            env = UpgradeEnvironment(Path(temp))
            files = {
                ARCHITECTURE: _valid_document(
                    "Architecture", "Updated architecture."
                ),
                BUSINESS: _valid_document("Business", "Updated business."),
                ROADMAP: _valid_document("Roadmap", "Updated roadmap."),
            }

            _create_upgrade_zip(env.zip_path, files)
            response = env.run()

            self.assertEqual(
                set(response.updated_files),
                {
                    EXECUTIVE_README,
                    COMMIT_MESSAGE,
                    ARCHITECTURE,
                    BUSINESS,
                    ROADMAP,
                },
            )
            for archive_path, content in files.items():
                self.assertEqual(
                    env.targets[archive_path].read_text(encoding="utf-8"),
                    content,
                )

    def test_partial_update_replaces_only_selected_file(self):
        with tempfile.TemporaryDirectory() as temp:
            env = UpgradeEnvironment(Path(temp))
            original_business = env.targets[BUSINESS].read_text(
                encoding="utf-8"
            )
            updated_architecture = _valid_document(
                "Architecture", "Updated architecture."
            )

            _create_upgrade_zip(
                env.zip_path,
                {ARCHITECTURE: updated_architecture},
            )
            response = env.run()

            self.assertEqual(
                env.targets[ARCHITECTURE].read_text(encoding="utf-8"),
                updated_architecture,
            )
            self.assertEqual(
                env.targets[BUSINESS].read_text(encoding="utf-8"),
                original_business,
            )
            backup = Path(response.backup_directory)
            self.assertFalse(
                (backup / "previous" / BUSINESS).exists()
            )

    def test_user_guided_zip_accepts_prompt(self):
        with tempfile.TemporaryDirectory() as temp:
            env = UpgradeEnvironment(Path(temp))
            _create_upgrade_zip(
                env.zip_path,
                {
                    ROADMAP: _valid_document(
                        "Roadmap", "Updated roadmap."
                    )
                },
                execution_mode="user-guided",
                user_prompt="Update only the validated roadmap.",
            )

            response = env.run()
            backup = Path(response.backup_directory)

            self.assertEqual(
                (backup / USER_PROMPT).read_text(encoding="utf-8"),
                "Update only the validated roadmap.",
            )

    def test_user_prompt_is_rejected_in_evidence_mode(self):
        with tempfile.TemporaryDirectory() as temp:
            env = UpgradeEnvironment(Path(temp))
            _create_upgrade_zip(
                env.zip_path,
                {
                    ARCHITECTURE: _valid_document(
                        "Architecture", "Updated."
                    )
                },
                user_prompt="Prompt",
                manifest_updates={
                    "execution_mode": "evidence",
                    "user_prompt_file": None,
                },
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "USER_PROMPT.md is not allowed",
            ):
                env.run()

    def test_user_guided_mode_requires_prompt_file(self):
        with tempfile.TemporaryDirectory() as temp:
            env = UpgradeEnvironment(Path(temp))
            _create_upgrade_zip(
                env.zip_path,
                {
                    ARCHITECTURE: _valid_document(
                        "Architecture", "Updated."
                    )
                },
                manifest_updates={
                    "execution_mode": "user-guided",
                    "user_prompt_file": USER_PROMPT,
                },
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "USER_PROMPT.md is required",
            ):
                env.run()

    def test_information_only_zip_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            env = UpgradeEnvironment(Path(temp))
            _create_upgrade_zip(env.zip_path, {})

            with self.assertRaisesRegex(
                ContextValidationError,
                "at least one documentation file",
            ):
                env.run()

    def test_missing_required_root_files_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            env = UpgradeEnvironment(Path(temp))
            content = _valid_document("Architecture", "Updated.")
            manifest = {
                "project_name": "dp-api",
                "workflow": "documentation-upgrade",
                "execution_mode": "evidence",
                "user_prompt_file": None,
                "output_filename": "documentation-upgrade.zip",
                "documentation_root": "documentation",
                "allowed_files": [ARCHITECTURE, "manifest.json"],
                "updated_files": [ARCHITECTURE],
                "content_hashes": {
                    ARCHITECTURE: hashlib.sha256(
                        content.encode("utf-8")
                    ).hexdigest()
                },
                "commit": {
                    "type": "docs",
                    "scope": "documentation",
                    "subject": "update project documentation",
                    "message_file": COMMIT_MESSAGE,
                },
                "rag": {},
                "evidence": {},
            }
            with ZipFile(env.zip_path, "w") as archive:
                archive.writestr(ARCHITECTURE, content)
                archive.writestr("manifest.json", json.dumps(manifest))

            with self.assertRaisesRegex(
                ContextValidationError,
                "ZIP is missing required files",
            ):
                env.run()

    def test_non_markdown_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            env = UpgradeEnvironment(Path(temp))
            _create_upgrade_zip(
                env.zip_path,
                {"documentation/architecture.txt": "invalid"},
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "must use .md",
            ):
                env.run()

    def test_protected_format_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            env = UpgradeEnvironment(Path(temp))
            _create_upgrade_zip(
                env.zip_path,
                {
                    "documentation/FORMAT_CONTEXT.md":
                        _valid_document("FORMAT_CONTEXT.md", "Forbidden.")
                },
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "Protected documentation file",
            ):
                env.run()

    def test_hash_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            env = UpgradeEnvironment(Path(temp))
            content = _valid_document("Architecture", "Updated.")
            files = {
                EXECUTIVE_README: "Documentation upgrade summary\n",
                COMMIT_MESSAGE: (
                    "docs(documentation): update project documentation\n"
                ),
                ARCHITECTURE: content,
            }
            _create_upgrade_zip(
                env.zip_path,
                {ARCHITECTURE: content},
                manifest_updates={
                    "content_hashes": {
                        name: (
                            "0" * 64
                            if name == ARCHITECTURE
                            else hashlib.sha256(
                                value.encode("utf-8")
                            ).hexdigest()
                        )
                        for name, value in files.items()
                    }
                },
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "SHA-256 mismatch",
            ):
                env.run()

    def test_commit_metadata_must_match_commit_message(self):
        with tempfile.TemporaryDirectory() as temp:
            env = UpgradeEnvironment(Path(temp))
            _create_upgrade_zip(
                env.zip_path,
                {
                    ARCHITECTURE: _valid_document(
                        "Architecture", "Updated."
                    )
                },
                manifest_updates={
                    "commit": {
                        "type": "feat",
                        "scope": "documentation",
                        "subject": "different subject",
                        "message_file": COMMIT_MESSAGE,
                    }
                },
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "does not match COMMIT_MESSAGE",
            ):
                env.run()

    def test_missing_metadata_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            env = UpgradeEnvironment(Path(temp))
            invalid = "\n\n".join(
                [
                    "# Architecture",
                    *sum(
                        ([heading, "Content."] for heading in MAIN_PAGE_HEADINGS),
                        [],
                    ),
                ]
            ) + "\n"
            _create_upgrade_zip(
                env.zip_path,
                {ARCHITECTURE: invalid},
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "metadata",
            ):
                env.run()

    def test_multiple_level_one_headings_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            env = UpgradeEnvironment(Path(temp))
            invalid = (
                _valid_document("Architecture", "Updated.")
                + "\n# Duplicate title\n"
            )
            _create_upgrade_zip(
                env.zip_path,
                {ARCHITECTURE: invalid},
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "exactly one level-one heading",
            ):
                env.run()

    def test_heading_contract_is_enforced(self):
        with tempfile.TemporaryDirectory() as temp:
            env = UpgradeEnvironment(Path(temp))
            invalid = _valid_document(
                "Architecture", "Updated."
            ).replace(
                "## 15. Document boundary",
                "## 15. Scope boundary",
            )
            _create_upgrade_zip(
                env.zip_path,
                {ARCHITECTURE: invalid},
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "level-two headings do not match",
            ):
                env.run()

    def test_corrupt_zip_is_rejected_and_retained(self):
        with tempfile.TemporaryDirectory() as temp:
            env = UpgradeEnvironment(Path(temp))
            env.zip_path.write_bytes(b"not-a-zip")

            with self.assertRaises(ContextValidationError):
                env.run()

            self.assertTrue(env.zip_path.exists())

    def test_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            env = UpgradeEnvironment(Path(temp))
            with ZipFile(env.zip_path, "w") as archive:
                archive.writestr("../escape.md", "unsafe")
                archive.writestr("manifest.json", "{}")

            with self.assertRaises(ContextValidationError):
                env.run()

    def test_zip_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            env = UpgradeEnvironment(Path(temp))
            symlink = ZipInfo(ARCHITECTURE)
            symlink.create_system = 3
            symlink.external_attr = (stat.S_IFLNK | 0o777) << 16

            with ZipFile(env.zip_path, "w") as archive:
                archive.writestr(symlink, "architecture.md")
                archive.writestr("manifest.json", "{}")

            with self.assertRaises(ContextValidationError):
                env.run()

    def test_replacement_failure_rolls_back_and_retains_input(self):
        with tempfile.TemporaryDirectory() as temp:
            env = UpgradeEnvironment(Path(temp))
            original_architecture = env.targets[ARCHITECTURE].read_text(
                encoding="utf-8"
            )
            original_business = env.targets[BUSINESS].read_text(
                encoding="utf-8"
            )

            _create_upgrade_zip(
                env.zip_path,
                {
                    ARCHITECTURE: _valid_document(
                        "Architecture", "Updated architecture."
                    ),
                    BUSINESS: _valid_document(
                        "Business", "Updated business."
                    ),
                },
            )

            from app.services.documentation import (
                documentation_upgrade_service,
            )

            original_replace = (
                documentation_upgrade_service._atomic_replace_file
            )
            call_count = 0

            def fail_second(source: Path, target: Path):
                nonlocal call_count
                call_count += 1
                if call_count == 2:
                    raise OSError("simulated failure")
                return original_replace(source, target)

            with patch(
                "app.services.documentation."
                "documentation_upgrade_service._atomic_replace_file",
                side_effect=fail_second,
            ):
                with self.assertRaises(
                    DocumentationUpgradeOperationalError
                ):
                    env.run()

            self.assertEqual(
                env.targets[ARCHITECTURE].read_text(encoding="utf-8"),
                original_architecture,
            )
            self.assertEqual(
                env.targets[BUSINESS].read_text(encoding="utf-8"),
                original_business,
            )
            self.assertTrue(env.zip_path.exists())


if __name__ == "__main__":
    unittest.main()
