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

from app.services.contexts.context_upgrade_service import (
    ContextUpgradeOperationalError,
    upgrade_contexts,
)
from app.services.contexts.file_discovery_service import (
    ContextValidationError,
)


GLOBAL_PROJECT = "SBM-SUITE/PROJECT_CONTEXT.md"
GLOBAL_README = "SBM-SUITE/README.md"
SUITE_CONTEXT = "SBM-SUITE/context/SUITE_CONTEXT.md"
PROJECT_CONTEXT = (
    "SBM-SUITE/dp-api/context/PROJECT_CONTEXT.md"
)
PROJECT_README = "SBM-SUITE/dp-api/README.md"
EXECUTIVE_README = "EXECUTIVE_README.md"
COMMIT_MESSAGE = "COMMIT_MESSAGE.md"


def _write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class UpgradeEnvironment:
    def __init__(self, root: Path):
        self.suite_root = root / "context"
        self.project_root = root / "DP-API"
        self.input_directory = self.suite_root / "input"
        self.backup_root = self.suite_root / "temp" / "backup"
        self.input_directory.mkdir(parents=True)
        self.backup_root.mkdir(parents=True)
        self.targets = {
            GLOBAL_PROJECT: self.suite_root / "PROJECT_CONTEXT.md",
            GLOBAL_README: self.suite_root / "README.md",
            SUITE_CONTEXT: self.suite_root / "SUITE_CONTEXT.md",
            PROJECT_CONTEXT: (
                self.project_root / "context/PROJECT_CONTEXT.md"
            ),
            PROJECT_README: self.project_root / "README.md",
        }

        for archive_path, target in self.targets.items():
            _write(target, f"old:{archive_path}")

    @property
    def zip_path(self) -> Path:
        return self.input_directory / "context-upgrade.zip"

    def run(self):
        return upgrade_contexts(
            input_directory=str(self.input_directory),
            suite_context_root=str(self.suite_root),
            project_root=str(self.project_root),
            backup_root=str(self.backup_root),
            now=lambda: datetime(2026, 7, 30, 10, 11, 12),
        )


def _create_upgrade_zip(
    path: Path,
    files: dict[str, str],
    updated_files: list[str],
    manifest_updates: dict | None = None,
):
    manifest = {
        "project_name": "dp-api",
        "workflow": "context-upgrade",
        "output_filename": "context-upgrade.zip",
        "allowed_files": [*files, "manifest.json"],
        "updated_files": updated_files,
        "content_hashes": {
            name: hashlib.sha256(
                content.encode("utf-8")
            ).hexdigest()
            for name, content in files.items()
        },
        "commit": {
            "type": "docs",
            "scope": "contexts",
            "subject": "update project context",
        },
        "rag": {"retrieved_chunk_count": 3},
    }

    if manifest_updates:
        manifest.update(manifest_updates)

    with ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)

        archive.writestr(
            "manifest.json",
            json.dumps(manifest),
        )


class ContextUpgradeTests(unittest.TestCase):
    def test_valid_zip_creates_backup_replaces_atomically_and_cleans_input(
        self,
    ):
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = UpgradeEnvironment(Path(temporary_directory))
            old_mode = stat.S_IMODE(
                environment.targets[GLOBAL_PROJECT].stat().st_mode
            )
            files = {
                GLOBAL_PROJECT: "new global project",
                EXECUTIVE_README: "Executive summary",
                COMMIT_MESSAGE: "feat: update context",
            }
            _create_upgrade_zip(
                environment.zip_path,
                files,
                [GLOBAL_PROJECT, EXECUTIVE_README, COMMIT_MESSAGE],
            )

            response = environment.run()

            self.assertEqual(response.project_name, "dp-api")
            self.assertEqual(response.workflow, "context-upgrade")
            self.assertTrue(response.input_cleaned)
            self.assertFalse(environment.zip_path.exists())
            self.assertEqual(
                environment.targets[GLOBAL_PROJECT].read_text(
                    encoding="utf-8"
                ),
                "new global project",
            )
            self.assertEqual(
                stat.S_IMODE(
                    environment.targets[GLOBAL_PROJECT].stat().st_mode
                ),
                old_mode,
            )
            backup = Path(response.backup_directory)
            self.assertEqual(
                backup.name,
                "20260730_101112_dp-api",
            )
            self.assertEqual(
                (
                    backup / "previous" / GLOBAL_PROJECT
                ).read_text(encoding="utf-8"),
                f"old:{GLOBAL_PROJECT}",
            )
            self.assertEqual(
                (
                    backup / "applied" / GLOBAL_PROJECT
                ).read_text(encoding="utf-8"),
                "new global project",
            )
            self.assertTrue(
                (backup / "EXECUTIVE_README.md").is_file()
            )
            self.assertTrue(
                (backup / "COMMIT_MESSAGE.md").is_file()
            )
            self.assertTrue((backup / "manifest.json").is_file())
            self.assertEqual(
                list(
                    environment.targets[
                        GLOBAL_PROJECT
                    ].parent.glob(
                        ".PROJECT_CONTEXT.md.*.upgrade"
                    )
                ),
                [],
            )

    def test_absent_zip_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = UpgradeEnvironment(Path(temporary_directory))

            with self.assertRaises(ContextValidationError):
                environment.run()

    def test_multiple_zips_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = UpgradeEnvironment(Path(temporary_directory))
            environment.zip_path.write_bytes(b"one")
            (
                environment.input_directory / "second.zip"
            ).write_bytes(b"two")

            with self.assertRaises(ContextValidationError):
                environment.run()

    def test_wrong_zip_name_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = UpgradeEnvironment(Path(temporary_directory))
            (
                environment.input_directory / "other.zip"
            ).write_bytes(b"zip")

            with self.assertRaises(ContextValidationError):
                environment.run()

    def test_corrupt_zip_is_rejected_and_retained(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = UpgradeEnvironment(Path(temporary_directory))
            environment.zip_path.write_bytes(b"not-a-zip")

            with self.assertRaises(ContextValidationError):
                environment.run()

            self.assertTrue(environment.zip_path.exists())

    def test_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = UpgradeEnvironment(Path(temporary_directory))

            with ZipFile(environment.zip_path, "w") as archive:
                archive.writestr("../escape.md", "unsafe")
                archive.writestr("manifest.json", "{}")

            with self.assertRaises(ContextValidationError):
                environment.run()

            self.assertFalse(
                (Path(temporary_directory) / "escape.md").exists()
            )

    def test_absolute_zip_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = UpgradeEnvironment(Path(temporary_directory))

            with ZipFile(environment.zip_path, "w") as archive:
                archive.writestr("/absolute.md", "unsafe")
                archive.writestr("manifest.json", "{}")

            with self.assertRaises(ContextValidationError):
                environment.run()

    def test_zip_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = UpgradeEnvironment(Path(temporary_directory))
            symlink = ZipInfo(GLOBAL_PROJECT)
            symlink.create_system = 3
            symlink.external_attr = (
                stat.S_IFLNK | 0o777
            ) << 16

            with ZipFile(environment.zip_path, "w") as archive:
                archive.writestr(symlink, "README.md")
                archive.writestr("manifest.json", "{}")

            with self.assertRaises(ContextValidationError):
                environment.run()

    def test_missing_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = UpgradeEnvironment(Path(temporary_directory))

            with ZipFile(environment.zip_path, "w") as archive:
                archive.writestr(GLOBAL_README, "new readme")

            with self.assertRaises(ContextValidationError):
                environment.run()

    def test_protected_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = UpgradeEnvironment(Path(temporary_directory))
            protected = "SBM-SUITE/context/QA_CONTEXT.md"
            _create_upgrade_zip(
                environment.zip_path,
                {protected: "forbidden"},
                [protected],
            )

            with self.assertRaises(ContextValidationError):
                environment.run()

    def test_hash_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(
                environment.zip_path,
                {GLOBAL_README: "new readme"},
                [GLOBAL_README],
                manifest_updates={
                    "content_hashes": {
                        GLOBAL_README: "0" * 64,
                    }
                },
            )

            with self.assertRaises(ContextValidationError):
                environment.run()

    def test_inconsistent_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(
                environment.zip_path,
                {GLOBAL_README: "new readme"},
                [GLOBAL_PROJECT],
            )

            with self.assertRaises(ContextValidationError):
                environment.run()

    def test_partial_update_replaces_only_updated_files(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(
                environment.zip_path,
                {
                    GLOBAL_PROJECT: "new project",
                },
                [GLOBAL_PROJECT],
                manifest_updates={
                    "allowed_files": [
                        GLOBAL_PROJECT,
                        GLOBAL_README,
                        SUITE_CONTEXT,
                        PROJECT_CONTEXT,
                        PROJECT_README,
                        EXECUTIVE_README,
                        COMMIT_MESSAGE,
                        "manifest.json",
                    ],
                },
            )

            response = environment.run()

            self.assertEqual(
                environment.targets[GLOBAL_PROJECT].read_text(
                    encoding="utf-8"
                ),
                "new project",
            )
            self.assertEqual(
                environment.targets[GLOBAL_README].read_text(
                    encoding="utf-8"
                ),
                f"old:{GLOBAL_README}",
            )
            backup = Path(response.backup_directory)
            self.assertFalse(
                (backup / "previous" / GLOBAL_README).exists()
            )
            self.assertFalse(
                (backup / "applied" / GLOBAL_README).exists()
            )

    def test_output_filename_may_be_absent_for_compatibility(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(
                environment.zip_path,
                {GLOBAL_README: "new readme"},
                [GLOBAL_README],
                manifest_updates={"output_filename": None},
            )

            manifest_path = environment.zip_path

            with ZipFile(manifest_path, "r") as source:
                members = {
                    info.filename: source.read(info.filename)
                    for info in source.infolist()
                }

            manifest = json.loads(
                members["manifest.json"].decode("utf-8")
            )
            manifest.pop("output_filename")
            members["manifest.json"] = json.dumps(manifest).encode(
                "utf-8"
            )

            with ZipFile(manifest_path, "w") as target:
                for name, content in members.items():
                    target.writestr(name, content)

            response = environment.run()

            self.assertTrue(response.input_cleaned)

    def test_incorrect_output_filename_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(
                environment.zip_path,
                {GLOBAL_README: "new readme"},
                [GLOBAL_README],
                manifest_updates={
                    "output_filename": "other.zip",
                },
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "manifest.output_filename",
            ):
                environment.run()

            self.assertTrue(environment.zip_path.exists())

    def test_chatgpt_manifest_with_partial_files_is_accepted(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = UpgradeEnvironment(Path(temporary_directory))
            files = {
                EXECUTIVE_README: "Executive",
                COMMIT_MESSAGE: "docs(contexts): update",
                GLOBAL_PROJECT: "new project",
                SUITE_CONTEXT: "new suite",
                PROJECT_CONTEXT: "new project context",
                PROJECT_README: "new project readme",
            }
            _create_upgrade_zip(
                environment.zip_path,
                files,
                list(files),
                manifest_updates={
                    "allowed_files": [
                        GLOBAL_PROJECT,
                        GLOBAL_README,
                        SUITE_CONTEXT,
                        PROJECT_CONTEXT,
                        PROJECT_README,
                        "manifest.json",
                        EXECUTIVE_README,
                        COMMIT_MESSAGE,
                    ],
                    "commit": {
                        "type": "feat",
                        "scope": "contexts",
                        "subject": "add RAG context lifecycle",
                        "message_file": COMMIT_MESSAGE,
                    },
                    "rag": {
                        "retrieved_chunk_count": 16,
                        "retrieved_sources": [],
                    },
                },
            )

            response = environment.run()

            self.assertEqual(response.updated_files, list(files))
            self.assertTrue(response.input_cleaned)

    def test_information_only_zip_creates_backup_without_replacements(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = UpgradeEnvironment(Path(temporary_directory))
            original_contents = {
                archive_path: target.read_text(encoding="utf-8")
                for archive_path, target in environment.targets.items()
            }
            _create_upgrade_zip(
                environment.zip_path,
                {
                    EXECUTIVE_README: "Executive",
                    COMMIT_MESSAGE: "docs: context report",
                },
                [EXECUTIVE_README, COMMIT_MESSAGE],
            )

            response = environment.run()

            self.assertTrue(response.input_cleaned)
            self.assertEqual(
                {
                    archive_path: target.read_text(encoding="utf-8")
                    for archive_path, target in environment.targets.items()
                },
                original_contents,
            )
            backup = Path(response.backup_directory)
            self.assertEqual(
                list((backup / "previous").rglob("*")),
                [],
            )
            self.assertEqual(
                list((backup / "applied").rglob("*")),
                [],
            )

    def test_replacement_failure_rolls_back_and_retains_input(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(
                environment.zip_path,
                {
                    GLOBAL_PROJECT: "new project",
                    GLOBAL_README: "new readme",
                },
                [GLOBAL_PROJECT, GLOBAL_README],
            )
            from app.services.contexts import (
                context_upgrade_service,
            )

            original_atomic_replace = (
                context_upgrade_service._atomic_replace_file
            )

            def fail_second_replacement(source, target):
                if (
                    target
                    == environment.targets[GLOBAL_README].resolve()
                    and "previous" not in source.parts
                ):
                    raise OSError("simulated replacement failure")

                return original_atomic_replace(source, target)

            with patch(
                "app.services.contexts.context_upgrade_service."
                "_atomic_replace_file",
                side_effect=fail_second_replacement,
            ):
                with self.assertRaises(
                    ContextUpgradeOperationalError
                ):
                    environment.run()

            self.assertEqual(
                environment.targets[GLOBAL_PROJECT].read_text(
                    encoding="utf-8"
                ),
                f"old:{GLOBAL_PROJECT}",
            )
            self.assertEqual(
                environment.targets[GLOBAL_README].read_text(
                    encoding="utf-8"
                ),
                f"old:{GLOBAL_README}",
            )
            self.assertTrue(environment.zip_path.exists())


if __name__ == "__main__":
    unittest.main()
