from __future__ import annotations

import hashlib
import json
import re
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


GLOBAL_PROJECT = "SBM-SUITE/context/PROJECT_CONTEXT.md"
SUITE_CONTEXT = "SBM-SUITE/context/SUITE_CONTEXT.md"
BUSINESS_CONTEXT = "SBM-SUITE/context/BUSINESS_CONTEXT.md"
GLOBAL_QA_CONTEXT = "SBM-SUITE/context/QA_CONTEXT.md"
SECURITY_CONTEXT = "SBM-SUITE/context/SECURITY_CONTEXT.md"
DATA_CONTEXT = "SBM-SUITE/context/DATA_CONTEXT.md"
DECISIONS_CONTEXT = "SBM-SUITE/context/DECISIONS_CONTEXT.md"
PROJECT_CONTEXT = (
    "SBM-SUITE/dp-api/context/PROJECT_CONTEXT.md"
)
PROJECT_QA_CONTEXT = (
    "SBM-SUITE/dp-api/context/QA_CONTEXT.md"
)
EXECUTIVE_README = "EXECUTIVE_README.md"
COMMIT_MESSAGE = "COMMIT_MESSAGE.md"
USER_PROMPT = "USER_PROMPT.md"
FORMAT_CONTEXT = "FORMAT_CONTEXT.md"


def _write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


FORMAT_CONTRACT = """# FORMAT_CONTEXT.md

## 1. Global rules

Preserve exact headings and order.

## 2. Global `PROJECT_CONTEXT.md`

```text
# PROJECT_CONTEXT.md

## 1. Executive summary
## 2. Current suite objective
## 3. Projects and ownership
## 4. Global architecture
## 5. Shared infrastructure
## 6. Cross-project integrations
## 7. Context deployment and upgrade workflow
## 8. Current implementation status
## 9. Validated decisions
## 10. Accepted risks and constraints
## 11. Completed work
## 12. Pending work
## 13. Required behavior
## 14. Historical decisions
## 15. Document boundary
```

## 3. Global `SUITE_CONTEXT.md`

```text
# SUITE_CONTEXT.md

## 1. Suite identity
## 2. Product scope
## 3. Project map
## 4. Ownership boundaries
## 5. Runtime architecture
## 6. Data architecture
## 7. API boundaries
## 8. Authentication and authorization
## 9. Integrations
## 10. Infrastructure and containers
## 11. Shared configuration
## 12. Context and knowledge architecture
## 13. Deployment model
## 14. Security rules
## 15. Operational constraints
## 16. Current suite state
## 17. Context deployment lifecycle
## 18. Document boundary
```

## 4. Global `BUSINESS_CONTEXT.md`

```text
# BUSINESS_CONTEXT.md

## 1. Business overview
## 2. Product vision
## 3. Business actors
## 4. Organizations and brands
## 5. Core business domains
## 6. Business entities
## 7. Business rules
## 8. Commercial flows
## 9. Pricing and fiscal concepts
## 10. Inventory and catalog concepts
## 11. Sales and order concepts
## 12. Provider and branch concepts
## 13. Terminology
## 14. Validated business decisions
## 15. Business constraints
## 16. Pending business definitions
## 17. Document boundary
```

## 5. Global `QA_CONTEXT.md`

```text
# QA_CONTEXT.md

## 1. QA strategy
## 2. Quality gates
## 3. Test levels
## 4. Test environments
## 5. Required evidence
## 6. Coverage rules
## 7. Static analysis
## 8. Security validation
## 9. API validation
## 10. Database validation
## 11. Deployment validation
## 12. Defect classification
## 13. Release criteria
## 14. Accepted exceptions
## 15. Current QA status
## 16. Pending QA work
## 17. Document boundary
```

## 6. Global `SECURITY_CONTEXT.md`

```text
# SECURITY_CONTEXT.md

## 1. Security objectives
## 2. Security scope
## 3. Identity and authentication
## 4. Authorization
## 5. Secrets and configuration
## 6. Network security
## 7. Data protection
## 8. API security
## 9. Dependency and supply-chain security
## 10. Logging and audit
## 11. Security validation
## 12. Incident handling
## 13. Current security status
## 14. Accepted security risks
## 15. Pending security work
## 16. Document boundary
```

## 7. Global `DATA_CONTEXT.md`

```text
# DATA_CONTEXT.md

## 1. Data architecture overview
## 2. Data ownership
## 3. Datastores
## 4. Schemas
## 5. Core entities
## 6. Relationships
## 7. Migration ownership
## 8. Data lifecycle
## 9. Data integrity
## 10. Data access
## 11. Data synchronization
## 12. Backup and recovery
## 13. Current data status
## 14. Accepted data risks
## 15. Pending data work
## 16. Document boundary
```

## 8. Global `DECISIONS_CONTEXT.md`

```text
# DECISIONS_CONTEXT.md

## 1. Decision governance
## 2. Active decisions
## 3. Architecture decisions
## 4. Product decisions
## 5. Data decisions
## 6. Security decisions
## 7. QA decisions
## 8. Deployment decisions
## 9. Superseded decisions
## 10. Pending decisions
## 11. Document boundary
```

## 9. Project `context/PROJECT_CONTEXT.md`

```text
# PROJECT_CONTEXT.md

## 1. Executive summary
## 2. Project purpose
## 3. Current objective
## 4. Scope and ownership
## 5. Architecture
## 6. Runtime and containers
## 7. Configuration
## 8. Modules
## 9. Data model ownership
## 10. API surface
## 11. Authentication and authorization
## 12. Integrations
## 13. Implemented behavior
## 14. Validation evidence
## 15. Database and migration impact
## 16. Security considerations
## 17. Accepted risks and constraints
## 18. Completed work
## 19. Pending work
## 20. Required behavior
## 21. Historical decisions
## 22. Document boundary
```

## 10. Project `context/QA_CONTEXT.md`

```text
# QA_CONTEXT.md

## 1. Project QA scope
## 2. Required quality gates
## 3. Test structure
## 4. Unit tests
## 5. Integration tests
## 6. API tests
## 7. Database tests
## 8. Security tests
## 9. Static analysis
## 10. Coverage
## 11. Test data and fixtures
## 12. Environment requirements
## 13. Current validated evidence
## 14. Known defects
## 15. Accepted exceptions
## 16. Pending QA work
## 17. Document boundary
```
"""


def _contract_section_heading(archive_path: str) -> str:
    mapping = {
        GLOBAL_PROJECT: "## 2. Global `PROJECT_CONTEXT.md`",
        SUITE_CONTEXT: "## 3. Global `SUITE_CONTEXT.md`",
        BUSINESS_CONTEXT: "## 4. Global `BUSINESS_CONTEXT.md`",
        GLOBAL_QA_CONTEXT: "## 5. Global `QA_CONTEXT.md`",
        SECURITY_CONTEXT: "## 6. Global `SECURITY_CONTEXT.md`",
        DATA_CONTEXT: "## 7. Global `DATA_CONTEXT.md`",
        DECISIONS_CONTEXT: "## 8. Global `DECISIONS_CONTEXT.md`",
        PROJECT_CONTEXT: "## 9. Project `context/PROJECT_CONTEXT.md`",
        PROJECT_QA_CONTEXT: "## 10. Project `context/QA_CONTEXT.md`",
    }

    try:
        return mapping[archive_path]
    except KeyError as exc:
        raise ValueError(
            f"No format contract for {archive_path}"
        ) from exc


def _required_headings(archive_path: str) -> list[str]:
    section_heading = _contract_section_heading(archive_path)
    section_start = FORMAT_CONTRACT.index(section_heading)
    body_start = section_start + len(section_heading)
    section_body = FORMAT_CONTRACT[body_start:]

    match = re.search(
        r"```text\s*\n(?P<body>.*?)\n```",
        section_body,
        flags=re.DOTALL,
    )

    if match is None:
        raise AssertionError(
            f"Missing format block for {archive_path}"
        )

    return [
        line.strip()
        for line in match.group("body").splitlines()
        if re.fullmatch(r"#{1,2}\s+.+", line.strip())
    ]


def _valid_document(archive_path: str, marker: str) -> str:
    headings = _required_headings(archive_path)
    blocks = []

    for index, heading in enumerate(headings):
        blocks.append(heading)

        if index == 0:
            blocks.append(
                "> **Last updated:** 2026-07-30\n"
                ">\n"
                "> **Purpose:** Test fixture\n"
                ">\n"
                "> **Accuracy note:** Test-only content"
            )
        elif index == 1:
            blocks.append(marker)
        else:
            blocks.append(f"Content for {heading}")

    return "\n\n".join(blocks) + "\n"



class UpgradeEnvironment:
    def __init__(self, root: Path):
        self.suite_root = root / "context"
        self.project_root = root / "DP-API"
        self.input_directory = self.suite_root / "input"
        self.backup_root = self.suite_root / "temp" / "backup"
        self.input_directory.mkdir(parents=True)
        self.backup_root.mkdir(parents=True)
        _write(
            self.suite_root / FORMAT_CONTEXT,
            FORMAT_CONTRACT,
        )
        self.targets = {
            GLOBAL_PROJECT: self.suite_root / "PROJECT_CONTEXT.md",
            SUITE_CONTEXT: self.suite_root / "SUITE_CONTEXT.md",
            BUSINESS_CONTEXT: self.suite_root / "BUSINESS_CONTEXT.md",
            GLOBAL_QA_CONTEXT: self.suite_root / "QA_CONTEXT.md",
            SECURITY_CONTEXT: self.suite_root / "SECURITY_CONTEXT.md",
            DATA_CONTEXT: self.suite_root / "DATA_CONTEXT.md",
            DECISIONS_CONTEXT: self.suite_root / "DECISIONS_CONTEXT.md",
            PROJECT_CONTEXT: (
                self.project_root / "context/PROJECT_CONTEXT.md"
            ),
            PROJECT_QA_CONTEXT: (
                self.project_root / "context/QA_CONTEXT.md"
            ),
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
        "execution_mode": "evidence",
        "user_prompt_file": None,
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
                GLOBAL_PROJECT: _valid_document(GLOBAL_PROJECT, "new global project"),
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
                _valid_document(GLOBAL_PROJECT, "new global project"),
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
                "20260730_101112_000000_dp-api",
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
                _valid_document(GLOBAL_PROJECT, "new global project"),
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

    def test_all_authorized_context_types_can_be_replaced(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = UpgradeEnvironment(Path(temporary_directory))
            context_paths = [
                GLOBAL_PROJECT,
                SUITE_CONTEXT,
                BUSINESS_CONTEXT,
                GLOBAL_QA_CONTEXT,
                SECURITY_CONTEXT,
                DATA_CONTEXT,
                DECISIONS_CONTEXT,
                PROJECT_CONTEXT,
                PROJECT_QA_CONTEXT,
            ]
            files = {
                archive_path: _valid_document(
                    archive_path,
                    f"updated:{archive_path}",
                )
                for archive_path in context_paths
            }
            _create_upgrade_zip(
                environment.zip_path,
                files,
                context_paths,
            )

            response = environment.run()

            self.assertEqual(response.updated_files, context_paths)
            for archive_path in context_paths:
                self.assertEqual(
                    environment.targets[archive_path].read_text(
                        encoding="utf-8"
                    ),
                    files[archive_path],
                )


    def test_user_guided_zip_accepts_and_backs_up_user_prompt(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = UpgradeEnvironment(Path(temporary_directory))
            files = {
                EXECUTIVE_README: "Executive",
                COMMIT_MESSAGE: "docs(contexts): update objective",
                USER_PROMPT: (
                    "Actualizar el objetivo actual del proyecto "
                    "para integrar sbm-api."
                ),
                PROJECT_CONTEXT: _valid_document(
                    PROJECT_CONTEXT,
                    "Updated current objective",
                ),
            }
            _create_upgrade_zip(
                environment.zip_path,
                files,
                list(files),
                manifest_updates={
                    "execution_mode": "user-guided",
                    "user_prompt_file": USER_PROMPT,
                },
            )

            response = environment.run()
            backup = Path(response.backup_directory)

            self.assertTrue(response.input_cleaned)
            self.assertEqual(response.updated_files, list(files))
            self.assertEqual(
                (backup / USER_PROMPT).read_text(encoding="utf-8"),
                files[USER_PROMPT],
            )

    def test_user_prompt_is_rejected_in_evidence_mode(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(
                environment.zip_path,
                {USER_PROMPT: "Prompt literal"},
                [USER_PROMPT],
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "USER_PROMPT.md is not allowed in evidence mode",
            ):
                environment.run()

    def test_user_guided_mode_requires_user_prompt_file(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(
                environment.zip_path,
                {EXECUTIVE_README: "Executive"},
                [EXECUTIVE_README],
                manifest_updates={
                    "execution_mode": "user-guided",
                    "user_prompt_file": USER_PROMPT,
                },
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "USER_PROMPT.md is required in user-guided mode",
            ):
                environment.run()

    def test_user_guided_mode_requires_manifest_prompt_reference(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(
                environment.zip_path,
                {USER_PROMPT: "Prompt literal"},
                [USER_PROMPT],
                manifest_updates={
                    "execution_mode": "user-guided",
                    "user_prompt_file": None,
                },
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "manifest.user_prompt_file",
            ):
                environment.run()

    def test_invalid_execution_mode_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(
                environment.zip_path,
                {EXECUTIVE_README: "Executive"},
                [EXECUTIVE_README],
                manifest_updates={"execution_mode": "invalid"},
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "manifest.execution_mode",
            ):
                environment.run()

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
                archive.writestr(SUITE_CONTEXT, "new readme")

            with self.assertRaises(ContextValidationError):
                environment.run()

    def test_protected_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = UpgradeEnvironment(Path(temporary_directory))
            protected = "SBM-SUITE/context/FORMAT_CONTEXT.md"
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
                {GLOBAL_PROJECT: _valid_document(GLOBAL_PROJECT, "new project")},
                [GLOBAL_PROJECT],
                manifest_updates={
                    "content_hashes": {GLOBAL_PROJECT: "0" * 64}
                },
            )

            with self.assertRaises(ContextValidationError):
                environment.run()

    def test_inconsistent_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(
                environment.zip_path,
                {SUITE_CONTEXT: _valid_document(SUITE_CONTEXT, "new suite")},
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
                    GLOBAL_PROJECT: _valid_document(GLOBAL_PROJECT, "new project"),
                },
                [GLOBAL_PROJECT],
                manifest_updates={
                    "allowed_files": [
                        GLOBAL_PROJECT,
                        SUITE_CONTEXT,
                        PROJECT_CONTEXT,
                        PROJECT_QA_CONTEXT,
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
                _valid_document(GLOBAL_PROJECT, "new project"),
            )
            self.assertEqual(
                environment.targets[SUITE_CONTEXT].read_text(
                    encoding="utf-8"
                ),
                f"old:{SUITE_CONTEXT}",
            )
            backup = Path(response.backup_directory)
            self.assertFalse(
                (backup / "previous" / SUITE_CONTEXT).exists()
            )
            self.assertFalse(
                (backup / "applied" / SUITE_CONTEXT).exists()
            )

    def test_chatgpt_manifest_with_partial_files_is_accepted(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = UpgradeEnvironment(Path(temporary_directory))
            files = {
                EXECUTIVE_README: "Executive",
                COMMIT_MESSAGE: "docs(contexts): update",
                GLOBAL_PROJECT: _valid_document(GLOBAL_PROJECT, "new project"),
                SUITE_CONTEXT: _valid_document(SUITE_CONTEXT, "new suite"),
                PROJECT_CONTEXT: _valid_document(PROJECT_CONTEXT, "new project context"),
                PROJECT_QA_CONTEXT: _valid_document(PROJECT_QA_CONTEXT, "new project readme"),
            }
            _create_upgrade_zip(
                environment.zip_path,
                files,
                list(files),
                manifest_updates={
                    "allowed_files": [
                        GLOBAL_PROJECT,
                        SUITE_CONTEXT,
                        PROJECT_CONTEXT,
                        PROJECT_QA_CONTEXT,
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

    def test_information_only_zip_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(
                environment.zip_path,
                {
                    EXECUTIVE_README: "Executive",
                    COMMIT_MESSAGE: "docs: context report",
                },
                [EXECUTIVE_README, COMMIT_MESSAGE],
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "at least one authorized context file",
            ):
                environment.run()

            self.assertTrue(environment.zip_path.exists())

    def test_missing_required_heading_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = UpgradeEnvironment(Path(temporary_directory))
            valid = _valid_document(GLOBAL_PROJECT, "new project")
            heading = _required_headings(GLOBAL_PROJECT)[-1]
            invalid = valid.replace(
                heading + "\n\nContent for " + heading + "\n",
                "",
                1,
            )
            _create_upgrade_zip(
                environment.zip_path,
                {GLOBAL_PROJECT: invalid},
                [GLOBAL_PROJECT],
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "missing",
            ):
                environment.run()

            self.assertTrue(environment.zip_path.exists())
    def test_renamed_heading_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = UpgradeEnvironment(Path(temporary_directory))
            valid = _valid_document(GLOBAL_PROJECT, "new project")
            original = _required_headings(GLOBAL_PROJECT)[1]
            invalid = valid.replace(
                original,
                "## 1. Renamed executive summary",
                1,
            )
            _create_upgrade_zip(
                environment.zip_path,
                {GLOBAL_PROJECT: invalid},
                [GLOBAL_PROJECT],
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "missing|unexpected",
            ):
                environment.run()
    def test_duplicated_heading_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = UpgradeEnvironment(Path(temporary_directory))
            valid = _valid_document(GLOBAL_PROJECT, "new project")
            duplicate = _required_headings(GLOBAL_PROJECT)[1]
            invalid = valid + "\n" + duplicate + "\n\nDuplicate\n"
            _create_upgrade_zip(
                environment.zip_path,
                {GLOBAL_PROJECT: invalid},
                [GLOBAL_PROJECT],
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "Duplicated headings",
            ):
                environment.run()
    def test_heading_order_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = UpgradeEnvironment(Path(temporary_directory))
            valid = _valid_document(GLOBAL_PROJECT, "new project")
            headings = _required_headings(GLOBAL_PROJECT)
            first = headings[1]
            second = headings[2]
            invalid = valid.replace(first, "__FIRST__", 1)
            invalid = invalid.replace(second, first, 1)
            invalid = invalid.replace("__FIRST__", second, 1)

            _create_upgrade_zip(
                environment.zip_path,
                {GLOBAL_PROJECT: invalid},
                [GLOBAL_PROJECT],
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "out of order",
            ):
                environment.run()
    def test_unexpected_top_level_heading_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = UpgradeEnvironment(Path(temporary_directory))
            invalid = (
                _valid_document(GLOBAL_PROJECT, "new project")
                + "\n## 99. Unexpected\n\nContent\n"
            )
            _create_upgrade_zip(
                environment.zip_path,
                {GLOBAL_PROJECT: invalid},
                [GLOBAL_PROJECT],
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "unexpected",
            ):
                environment.run()
    def test_missing_format_contract_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = UpgradeEnvironment(Path(temporary_directory))
            (environment.suite_root / FORMAT_CONTEXT).unlink()
            _create_upgrade_zip(
                environment.zip_path,
                {
                    GLOBAL_PROJECT: _valid_document(
                        GLOBAL_PROJECT,
                        "new project",
                    )
                },
                [GLOBAL_PROJECT],
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "Missing required format contract",
            ):
                environment.run()

            self.assertTrue(environment.zip_path.exists())

    def test_replacement_failure_rolls_back_and_retains_input(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(
                environment.zip_path,
                {
                    GLOBAL_PROJECT: _valid_document(GLOBAL_PROJECT, "new project"),
                    SUITE_CONTEXT: _valid_document(SUITE_CONTEXT, "new suite"),
                },
                [GLOBAL_PROJECT, SUITE_CONTEXT],
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
                    == environment.targets[SUITE_CONTEXT].resolve()
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
                environment.targets[SUITE_CONTEXT].read_text(
                    encoding="utf-8"
                ),
                f"old:{SUITE_CONTEXT}",
            )
            self.assertTrue(environment.zip_path.exists())


if __name__ == "__main__":
    unittest.main()
