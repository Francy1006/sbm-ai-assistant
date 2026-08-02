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
from app.services.contexts.file_discovery_service import ContextValidationError


GLOBAL_PROJECT_PATCH = "patches/global-project-context.json"
SUITE_CONTEXT_PATCH = "patches/suite-context.json"
PROJECT_CONTEXT_PATCH = "patches/project-context.json"
PROJECT_README_PATCH = "patches/project-readme.json"

GLOBAL_PROJECT = "SBM-SUITE/context/PROJECT_CONTEXT.md"
SUITE_CONTEXT = "SBM-SUITE/context/SUITE_CONTEXT.md"
PROJECT_CONTEXT = "SBM-SUITE/dp/DP-API/context/PROJECT_CONTEXT.md"
PROJECT_README = "SBM-SUITE/dp/DP-API/README.md"

EXECUTIVE_README = "EXECUTIVE_README.md"
COMMIT_MESSAGE = "COMMIT_MESSAGE.md"
USER_PROMPT = "USER_PROMPT.md"


FORMAT_CONTRACT = """# FORMAT_CONTEXT.md

## 2. Global `PROJECT_CONTEXT.md`

```text
# PROJECT_CONTEXT.md
## 1. Executive summary
## 2. Current suite objective
## 3. Document boundary
```

---

## 3. Global `SUITE_CONTEXT.md`

```text
# SUITE_CONTEXT.md
## 1. Suite identity
## 2. Product scope
## 3. Document boundary
```

---

## 10. Project `context/PROJECT_CONTEXT.md`

```text
# PROJECT_CONTEXT.md
## 1. Executive summary
## 2. Project purpose
## 3. Document boundary
```

---

## 13. Project and suite `README.md`

```text
# README.md
## Overview
## Reusable components
## 3. Document boundary
```

---
"""


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _document(title: str, heading_1: str, heading_2: str) -> str:
    return (
        f"# {title}\n\n"
        f"{heading_1}\n\nOld first section.\n\n"
        f"{heading_2}\n\nOld second section.\n\n"
        "## 3. Document boundary\n\nBoundary.\n"
    )


def _replace_patch(target_file: str, heading: str, content: str) -> str:
    return json.dumps(
        {
            "target_file": target_file,
            "operations": [
                {
                    "operation": "replace_section",
                    "heading": heading,
                    "content": content,
                }
            ],
        }
    )


def _append_patch(target_file: str, heading: str, content: str) -> str:
    return json.dumps(
        {
            "target_file": target_file,
            "operations": [
                {
                    "operation": "append_to_section",
                    "heading": heading,
                    "content": content,
                }
            ],
        }
    )


class UpgradeEnvironment:
    def __init__(
        self,
        root: Path,
        project_name: str = "dp-api",
        brand: str = "dp",
        directory_name: str = "DP-API",
    ):
        self.project_name = project_name
        self.suite_root = root / "SBM-SUITE" / "context"
        self.project_root = root / "SBM-SUITE" / brand / directory_name
        self.input_directory = self.suite_root / "input"
        self.backup_root = self.suite_root / "backup"

        self.input_directory.mkdir(parents=True)
        self.backup_root.mkdir(parents=True)

        _write(self.suite_root / "FORMAT_CONTEXT.md", FORMAT_CONTRACT)
        _write(
            self.suite_root / "PROJECT_CONTEXT.md",
            _document(
                "PROJECT_CONTEXT.md",
                "## 1. Executive summary",
                "## 2. Current suite objective",
            ),
        )
        _write(
            self.suite_root / "SUITE_CONTEXT.md",
            _document(
                "SUITE_CONTEXT.md",
                "## 1. Suite identity",
                "## 2. Product scope",
            ),
        )
        _write(
            self.project_root / "context/PROJECT_CONTEXT.md",
            _document(
                "PROJECT_CONTEXT.md",
                "## 1. Executive summary",
                "## 2. Project purpose",
            ),
        )
        _write(
            self.project_root / "README.md",
            _document(
                "README.md",
                "## Overview",
                "## Reusable components",
            ),
        )

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
    patches: dict[str, str],
    *,
    execution_mode: str = "evidence",
    user_prompt: str | None = None,
    manifest_updates: dict | None = None,
    project_name: str = "dp-api",
) -> None:
    files = {
        EXECUTIVE_README: "Context upgrade summary\n",
        COMMIT_MESSAGE: "docs(contexts): update project context\n",
        **patches,
    }
    if user_prompt is not None:
        files[USER_PROMPT] = user_prompt

    manifest = {
        "project_name": project_name,
        "workflow": "context-upgrade",
        "execution_mode": execution_mode,
        "user_prompt_file": USER_PROMPT if user_prompt is not None else None,
        "output_filename": "context-upgrade.zip",
        "allowed_files": [*files, "manifest.json"],
        "updated_files": list(files),
        "content_hashes": {
            name: hashlib.sha256(content.encode("utf-8")).hexdigest()
            for name, content in files.items()
        },
        "commit": {
            "type": "docs",
            "scope": "contexts",
            "subject": "update project context",
            "message_file": COMMIT_MESSAGE,
        },
        "rag": {"retrieved_chunk_count": 3},
    }
    if manifest_updates:
        manifest.update(manifest_updates)

    with ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
        archive.writestr("manifest.json", json.dumps(manifest))


class ContextUpgradeTests(unittest.TestCase):
    def test_valid_global_patch_creates_backup_applies_and_cleans_input(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            target = env.suite_root / "PROJECT_CONTEXT.md"
            old_mode = stat.S_IMODE(target.stat().st_mode)

            patch_content = "## 2. Current suite objective\n\n" "New suite objective.\n"
            _create_upgrade_zip(
                env.zip_path,
                {
                    GLOBAL_PROJECT_PATCH: _replace_patch(
                        GLOBAL_PROJECT,
                        "## 2. Current suite objective",
                        patch_content,
                    )
                },
            )

            response = env.run()

            self.assertEqual(response.project_name, "dp-api")
            self.assertEqual(response.workflow, "context-upgrade")
            self.assertEqual(response.updated_files, [GLOBAL_PROJECT])
            self.assertTrue(response.input_cleaned)
            self.assertFalse(env.zip_path.exists())
            self.assertIn("New suite objective.", target.read_text(encoding="utf-8"))
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), old_mode)

            backup = Path(response.backup_directory)
            self.assertTrue((backup / "previous" / GLOBAL_PROJECT).is_file())
            self.assertTrue((backup / "applied" / GLOBAL_PROJECT).is_file())
            self.assertTrue((backup / GLOBAL_PROJECT_PATCH).is_file())
            self.assertTrue((backup / EXECUTIVE_README).is_file())
            self.assertTrue((backup / COMMIT_MESSAGE).is_file())
            backup_manifest = json.loads(
                (backup / "BACKUP_MANIFEST.json").read_text(encoding="utf-8")
            )
            self.assertEqual(backup_manifest["project_name"], "dp-api")
            self.assertEqual(backup_manifest["workflow"], "context-upgrade")
            self.assertEqual(
                [item["archive_path"] for item in backup_manifest["backed_up_files"]],
                [GLOBAL_PROJECT],
            )
            self.assertFalse((env.suite_root / "backups").exists())

    def test_all_allowlisted_projects_can_apply_their_own_patch(self):
        projects = (
            ("dp-api", "dp", "DP-API"),
            ("sbm-api", "sbm", "SBM-API"),
            ("sbm-ai-assistant", "sbm", "sbm-ai-assistant"),
        )
        for project_name, brand, directory_name in projects:
            with self.subTest(project_name=project_name):
                with tempfile.TemporaryDirectory() as temporary_directory:
                    env = UpgradeEnvironment(
                        Path(temporary_directory),
                        project_name,
                        brand,
                        directory_name,
                    )
                    target = (
                        f"SBM-SUITE/{brand}/{directory_name}/context/"
                        "PROJECT_CONTEXT.md"
                    )
                    _create_upgrade_zip(
                        env.zip_path,
                        {
                            PROJECT_CONTEXT_PATCH: _replace_patch(
                                target,
                                "## 2. Project purpose",
                                "## 2. Project purpose\n\nAllowlisted update.\n",
                            )
                        },
                        project_name=project_name,
                    )
                    response = env.run()
                    self.assertEqual(response.project_name, project_name)
                    self.assertEqual(response.updated_files, [target])

    def test_project_readme_section_patch_is_supported(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(
                env.zip_path,
                {
                    PROJECT_README_PATCH: _replace_patch(
                        PROJECT_README,
                        "## Reusable components",
                        "## Reusable components\n\n| File name | Path | Description |\n"
                        "|---|---|---|\n| registry | services/ | allowlist |\n",
                    )
                },
            )
            response = env.run()
            self.assertEqual(response.updated_files, [PROJECT_README])
            self.assertIn(
                "| File name | Path | Description |",
                (env.project_root / "README.md").read_text(encoding="utf-8"),
            )

    def test_reusable_changes_require_context_and_readme_patches(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(
                env.zip_path,
                {
                    PROJECT_CONTEXT_PATCH: _replace_patch(
                        PROJECT_CONTEXT,
                        "## 2. Project purpose",
                        "## 2. Project purpose\n\nUpdated service inventory.\n",
                    )
                },
                manifest_updates={
                    "changed_files": ["backend/app/services/new_service.py"]
                },
            )
            with self.assertRaisesRegex(
                ContextValidationError,
                "require project-context.json and project-readme.json",
            ):
                env.run()
            self.assertTrue(env.zip_path.exists())

    def test_project_patch_uses_brand_and_real_project_directory(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(
                env.zip_path,
                {
                    PROJECT_CONTEXT_PATCH: _replace_patch(
                        PROJECT_CONTEXT,
                        "## 2. Project purpose",
                        "## 2. Project purpose\n\nUpdated DP-API purpose.\n",
                    )
                },
            )

            response = env.run()

            self.assertEqual(response.updated_files, [PROJECT_CONTEXT])
            self.assertIn(
                "Updated DP-API purpose.",
                (env.project_root / "context/PROJECT_CONTEXT.md").read_text(
                    encoding="utf-8"
                ),
            )

    def test_multiple_authorized_patches_are_applied(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(
                env.zip_path,
                {
                    GLOBAL_PROJECT_PATCH: _replace_patch(
                        GLOBAL_PROJECT,
                        "## 1. Executive summary",
                        "## 1. Executive summary\n\nUpdated global summary.\n",
                    ),
                    SUITE_CONTEXT_PATCH: _replace_patch(
                        SUITE_CONTEXT,
                        "## 2. Product scope",
                        "## 2. Product scope\n\nUpdated product scope.\n",
                    ),
                },
            )

            response = env.run()

            self.assertEqual(
                response.updated_files,
                sorted([GLOBAL_PROJECT, SUITE_CONTEXT]),
            )

    def test_append_to_section_is_supported(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(
                env.zip_path,
                {
                    GLOBAL_PROJECT_PATCH: _append_patch(
                        GLOBAL_PROJECT,
                        "## 2. Current suite objective",
                        "Additional validated detail.",
                    )
                },
            )

            env.run()

            self.assertIn(
                "Additional validated detail.",
                (env.suite_root / "PROJECT_CONTEXT.md").read_text(encoding="utf-8"),
            )

    def test_user_guided_zip_accepts_and_backs_up_prompt(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(
                env.zip_path,
                {
                    PROJECT_CONTEXT_PATCH: _replace_patch(
                        PROJECT_CONTEXT,
                        "## 2. Project purpose",
                        "## 2. Project purpose\n\nGuided update.\n",
                    )
                },
                execution_mode="user-guided",
                user_prompt="Actualizar el propósito del proyecto.",
            )

            response = env.run()
            backup = Path(response.backup_directory)

            self.assertEqual(
                (backup / USER_PROMPT).read_text(encoding="utf-8"),
                "Actualizar el propósito del proyecto.",
            )

    def test_information_only_zip_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(env.zip_path, {})

            with self.assertRaisesRegex(
                ContextValidationError,
                "at least one authorized patch file",
            ):
                env.run()

    def test_missing_required_root_files_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            patch = _replace_patch(
                GLOBAL_PROJECT,
                "## 2. Current suite objective",
                "## 2. Current suite objective\n\nUpdated.\n",
            )
            manifest = {
                "project_name": "dp-api",
                "workflow": "context-upgrade",
            }
            with ZipFile(env.zip_path, "w") as archive:
                archive.writestr(GLOBAL_PROJECT_PATCH, patch)
                archive.writestr("manifest.json", json.dumps(manifest))

            with self.assertRaisesRegex(
                ContextValidationError,
                "manifest.allowed_files must be a unique string list",
            ):
                env.run()

    def test_wrong_project_target_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(
                env.zip_path,
                {
                    PROJECT_CONTEXT_PATCH: _replace_patch(
                        "SBM-SUITE/sbm/SBM-API/context/PROJECT_CONTEXT.md",
                        "## 2. Project purpose",
                        "## 2. Project purpose\n\nWrong target.\n",
                    )
                },
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "target_file must be",
            ):
                env.run()

    def test_unauthorized_heading_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(
                env.zip_path,
                {
                    GLOBAL_PROJECT_PATCH: _replace_patch(
                        GLOBAL_PROJECT,
                        "## 99. Unknown",
                        "## 99. Unknown\n\nInvalid.\n",
                    )
                },
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "Unauthorized heading",
            ):
                env.run()

    def test_replace_section_must_begin_with_exact_heading(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(
                env.zip_path,
                {
                    GLOBAL_PROJECT_PATCH: _replace_patch(
                        GLOBAL_PROJECT,
                        "## 2. Current suite objective",
                        "Content without heading.",
                    )
                },
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "must begin with exact heading",
            ):
                env.run()

    def test_append_must_not_contain_h1_or_h2(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(
                env.zip_path,
                {
                    GLOBAL_PROJECT_PATCH: _append_patch(
                        GLOBAL_PROJECT,
                        "## 2. Current suite objective",
                        "## Invalid nested heading\n\nContent.",
                    )
                },
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "must not contain H1/H2",
            ):
                env.run()

    def test_hash_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            patch = _replace_patch(
                GLOBAL_PROJECT,
                "## 2. Current suite objective",
                "## 2. Current suite objective\n\nUpdated.\n",
            )
            _create_upgrade_zip(
                env.zip_path,
                {GLOBAL_PROJECT_PATCH: patch},
                manifest_updates={
                    "content_hashes": {
                        EXECUTIVE_README: hashlib.sha256(
                            b"Context upgrade summary\n"
                        ).hexdigest(),
                        COMMIT_MESSAGE: hashlib.sha256(
                            b"docs(contexts): update project context\n"
                        ).hexdigest(),
                        GLOBAL_PROJECT_PATCH: "0" * 64,
                    }
                },
            )

            with self.assertRaisesRegex(ContextValidationError, "SHA-256 mismatch"):
                env.run()

    def test_commit_metadata_must_match_message(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            patch = _replace_patch(
                GLOBAL_PROJECT,
                "## 2. Current suite objective",
                "## 2. Current suite objective\n\nUpdated.\n",
            )
            _create_upgrade_zip(
                env.zip_path,
                {GLOBAL_PROJECT_PATCH: patch},
                manifest_updates={
                    "commit": {
                        "type": "feat",
                        "scope": "contexts",
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

    def test_missing_format_contract_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            (env.suite_root / "FORMAT_CONTEXT.md").unlink()
            _create_upgrade_zip(
                env.zip_path,
                {
                    GLOBAL_PROJECT_PATCH: _replace_patch(
                        GLOBAL_PROJECT,
                        "## 2. Current suite objective",
                        "## 2. Current suite objective\n\nUpdated.\n",
                    )
                },
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "Missing required format contract",
            ):
                env.run()

    def test_corrupt_zip_is_rejected_and_retained(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            env.zip_path.write_bytes(b"not-a-zip")

            with self.assertRaises(ContextValidationError):
                env.run()

            self.assertTrue(env.zip_path.exists())

    def test_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            with ZipFile(env.zip_path, "w") as archive:
                archive.writestr("../escape.md", "unsafe")
                archive.writestr("manifest.json", "{}")

            with self.assertRaises(ContextValidationError):
                env.run()

    def test_zip_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            symlink = ZipInfo(GLOBAL_PROJECT_PATCH)
            symlink.create_system = 3
            symlink.external_attr = (stat.S_IFLNK | 0o777) << 16

            with ZipFile(env.zip_path, "w") as archive:
                archive.writestr(symlink, "target")
                archive.writestr("manifest.json", "{}")

            with self.assertRaises(ContextValidationError):
                env.run()

    def test_replacement_failure_rolls_back_and_retains_input(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            global_original = (env.suite_root / "PROJECT_CONTEXT.md").read_text(
                encoding="utf-8"
            )
            suite_original = (env.suite_root / "SUITE_CONTEXT.md").read_text(
                encoding="utf-8"
            )

            _create_upgrade_zip(
                env.zip_path,
                {
                    GLOBAL_PROJECT_PATCH: _replace_patch(
                        GLOBAL_PROJECT,
                        "## 2. Current suite objective",
                        "## 2. Current suite objective\n\nUpdated global.\n",
                    ),
                    SUITE_CONTEXT_PATCH: _replace_patch(
                        SUITE_CONTEXT,
                        "## 2. Product scope",
                        "## 2. Product scope\n\nUpdated suite.\n",
                    ),
                },
            )

            from app.services.contexts import context_upgrade_service

            original_atomic_write = context_upgrade_service._atomic_write_text
            call_count = 0

            def fail_second_write(content, target):
                nonlocal call_count
                call_count += 1
                if call_count == 2:
                    raise OSError("simulated replacement failure")
                return original_atomic_write(content, target)

            with patch(
                "app.services.contexts.context_upgrade_service._atomic_write_text",
                side_effect=fail_second_write,
            ):
                with self.assertRaises(ContextUpgradeOperationalError):
                    env.run()

            self.assertEqual(
                (env.suite_root / "PROJECT_CONTEXT.md").read_text(encoding="utf-8"),
                global_original,
            )
            self.assertEqual(
                (env.suite_root / "SUITE_CONTEXT.md").read_text(encoding="utf-8"),
                suite_original,
            )
            self.assertTrue(env.zip_path.exists())


if __name__ == "__main__":
    unittest.main()
