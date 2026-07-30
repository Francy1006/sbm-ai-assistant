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


GLOBAL_PROJECT = "SBM-SUITE/PROJECT_CONTEXT.md"
GLOBAL_README = "SBM-SUITE/README.md"
SUITE_CONTEXT = "SBM-SUITE/context/SUITE_CONTEXT.md"
PROJECT_CONTEXT = (
    "SBM-SUITE/dp-api/context/PROJECT_CONTEXT.md"
)
PROJECT_README = "SBM-SUITE/dp-api/README.md"
EXECUTIVE_README = "EXECUTIVE_README.md"
COMMIT_MESSAGE = "COMMIT_MESSAGE.md"
USER_PROMPT = "USER_PROMPT.md"
FORMAT_CONTEXT = "FORMAT_CONTEXT.md"


def _write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


FORMAT_CONTRACT = '# FORMAT_CONTEXT.md\n\n> **Purpose**\n>\n> Canonical structure contract for every SBM Suite context file.\n> Context generation and upgrade processes must preserve these formats exactly.\n\n## 1. Global rules\n\n1. Preserve the exact heading names and order defined here.\n2. Do not rename, merge, split, reorder or remove required sections.\n3. Add content only inside the matching section.\n4. Preserve the metadata block at the beginning of each file.\n5. Preserve Markdown lists, tables, code blocks and path formatting.\n6. Do not duplicate information across sections.\n7. Do not create unsupported facts, tests, migrations, deployments or decisions.\n8. When evidence is insufficient, keep the existing content unchanged.\n9. A structural change requires an explicit update to this file.\n10. If a complete source file is unavailable, do not generate a replacement.\n11. Protected context files remain read-only unless their workflow explicitly allows modification.\n12. All dates use `YYYY-MM-DD`.\n\n---\n\n## 2. Global `PROJECT_CONTEXT.md`\n\nRequired structure:\n\n```text\n# PROJECT_CONTEXT.md\n\n> Last updated\n> Purpose\n> Accuracy note\n\n## 1. Executive summary\n## 2. Current suite objective\n## 3. Projects and ownership\n## 4. Global architecture\n## 5. Shared infrastructure\n## 6. Cross-project integrations\n## 7. Context deployment and upgrade workflow\n## 8. Current implementation status\n## 9. Validated decisions\n## 10. Accepted risks and constraints\n## 11. Completed work\n## 12. Pending work\n## 13. Required behavior\n## 14. Historical decisions\n## 15. Document boundary\n```\n\nSection rules:\n\n- `Executive summary`: concise suite state.\n- `Current suite objective`: active global objective only.\n- `Projects and ownership`: project responsibilities and boundaries.\n- `Global architecture`: suite-level architecture only.\n- `Shared infrastructure`: shared databases, networks, containers and services.\n- `Cross-project integrations`: contracts and data flows between projects.\n- `Context deployment and upgrade workflow`: context lifecycle.\n- `Current implementation status`: current verified state.\n- `Validated decisions`: accepted architectural and product decisions.\n- `Accepted risks and constraints`: known limitations.\n- `Completed work`: completed suite-level milestones.\n- `Pending work`: transversal pending work.\n- `Required behavior`: mandatory operating rules.\n- `Historical decisions`: relevant superseded or historical decisions.\n- `Document boundary`: information intentionally excluded.\n\n---\n\n## 3. Global `SUITE_CONTEXT.md`\n\nRequired structure:\n\n```text\n# SUITE_CONTEXT.md\n\n> Last updated\n> Purpose\n> Accuracy note\n\n## 1. Suite identity\n## 2. Product scope\n## 3. Project map\n## 4. Ownership boundaries\n## 5. Runtime architecture\n## 6. Data architecture\n## 7. API boundaries\n## 8. Authentication and authorization\n## 9. Integrations\n## 10. Infrastructure and containers\n## 11. Shared configuration\n## 12. Context and knowledge architecture\n## 13. Deployment model\n## 14. Security rules\n## 15. Operational constraints\n## 16. Current suite state\n## 17. Context deployment lifecycle\n## 18. Document boundary\n```\n\nSection rules:\n\n- Describe only suite-wide behavior.\n- Do not include project implementation transcripts.\n- Do not duplicate complete project contexts.\n- Record ownership, boundaries and shared flows.\n\n---\n\n## 4. Global `BUSINESS_CONTEXT.md`\n\nRequired structure:\n\n```text\n# BUSINESS_CONTEXT.md\n\n> Last updated\n> Purpose\n> Accuracy note\n\n## 1. Business overview\n## 2. Product vision\n## 3. Business actors\n## 4. Organizations and brands\n## 5. Core business domains\n## 6. Business entities\n## 7. Business rules\n## 8. Commercial flows\n## 9. Pricing and fiscal concepts\n## 10. Inventory and catalog concepts\n## 11. Sales and order concepts\n## 12. Provider and branch concepts\n## 13. Terminology\n## 14. Validated business decisions\n## 15. Business constraints\n## 16. Pending business definitions\n## 17. Document boundary\n```\n\nSection rules:\n\n- Store business meaning, not implementation detail.\n- Technical references are allowed only when required to explain ownership.\n- Do not infer business rules from code alone.\n\n---\n\n## 5. Global `QA_CONTEXT.md`\n\nRequired structure:\n\n```text\n# QA_CONTEXT.md\n\n> Last updated\n> Purpose\n> Accuracy note\n\n## 1. QA strategy\n## 2. Quality gates\n## 3. Test levels\n## 4. Test environments\n## 5. Required evidence\n## 6. Coverage rules\n## 7. Static analysis\n## 8. Security validation\n## 9. API validation\n## 10. Database validation\n## 11. Deployment validation\n## 12. Defect classification\n## 13. Release criteria\n## 14. Accepted exceptions\n## 15. Current QA status\n## 16. Pending QA work\n## 17. Document boundary\n```\n\nSection rules:\n\n- Record only executed and evidenced validation.\n- Never invent coverage, SonarQube, tests or deployments.\n- Separate required QA policy from current QA results.\n\n---\n\n## 6. Global `SYS_PROMPT.md`\n\nRequired structure:\n\n```text\n# SYS_PROMPT.md\n\n## Parameters\n## Objective\n## Required inputs\n## Input meaning\n## Change determination\n## Allowed outputs\n## Protected files\n## Context format contract\n## Context reconstruction rules\n## Project context\n## Suite project context\n## README files\n## QA evidence\n## Commit nomenclature\n## Executive summary\n## Database rules\n## Output rules\n## Manifest\n```\n\nSection rules:\n\n- `Context format contract` must require compliance with this file.\n- The prompt must not redefine formats independently.\n- Output filenames and manifest contracts must be explicit.\n- Protected files must be listed explicitly.\n\n---\n\n## 7. Project `context/PROJECT_CONTEXT.md`\n\nRequired structure:\n\n```text\n# PROJECT_CONTEXT.md\n\n> Last updated\n> Purpose\n> Accuracy note\n\n## 1. Executive summary\n## 2. Project purpose\n## 3. Current objective\n## 4. Scope and ownership\n## 5. Architecture\n## 6. Runtime and containers\n## 7. Configuration\n## 8. Modules\n## 9. Data model ownership\n## 10. API surface\n## 11. Authentication and authorization\n## 12. Integrations\n## 13. Implemented behavior\n## 14. Validation evidence\n## 15. Database and migration impact\n## 16. Security considerations\n## 17. Accepted risks and constraints\n## 18. Completed work\n## 19. Pending work\n## 20. Required behavior\n## 21. Historical decisions\n## 22. Document boundary\n```\n\nSection rules:\n\n- Keep implementation state separate from planned work.\n- Endpoint behavior belongs in `API surface`.\n- Completed implementation belongs in `Implemented behavior`.\n- Test results belong only in `Validation evidence`.\n- Database impact must state explicitly when none exists.\n- Project-specific headings may be added only through an approved update to this format file.\n\n---\n\n## 8. Project `context/QA_CONTEXT.md`\n\nRequired structure:\n\n```text\n# QA_CONTEXT.md\n\n> Last updated\n> Purpose\n> Accuracy note\n\n## 1. Project QA scope\n## 2. Required quality gates\n## 3. Test structure\n## 4. Unit tests\n## 5. Integration tests\n## 6. API tests\n## 7. Database tests\n## 8. Security tests\n## 9. Static analysis\n## 10. Coverage\n## 11. Test data and fixtures\n## 12. Environment requirements\n## 13. Current validated evidence\n## 14. Known defects\n## 15. Accepted exceptions\n## 16. Pending QA work\n## 17. Document boundary\n```\n\nSection rules:\n\n- Distinguish policy from current results.\n- Every result must include its evidence source.\n- Do not overwrite historical evidence without preserving relevant records.\n\n---\n\n## 9. Project `context/DEPLOY_CONTEXT.md`\n\nRequired structure:\n\n```text\n# DEPLOY_CONTEXT.md\n\n> Last updated\n> Purpose\n> Accuracy note\n\n## 1. Deployment overview\n## 2. Environments\n## 3. Runtime topology\n## 4. Containers and services\n## 5. Networks and ports\n## 6. Configuration and secrets\n## 7. Build process\n## 8. Deployment process\n## 9. Database deployment\n## 10. Health checks\n## 11. Observability\n## 12. Rollback\n## 13. Security requirements\n## 14. Operational procedures\n## 15. Current deployment status\n## 16. Known deployment risks\n## 17. Pending deployment work\n## 18. Document boundary\n```\n\nSection rules:\n\n- Never expose secret values.\n- Separate local, development, staging and production behavior.\n- Do not claim a deployment occurred without explicit evidence.\n\n---\n\n## 10. Project and suite `README.md`\n\nRequired structure:\n\n```text\n# Project or suite name\n\n## Overview\n## Purpose\n## Architecture\n## Requirements\n## Configuration\n## Installation\n## Runtime\n## Usage\n## API or interfaces\n## Development\n## Validation\n## Security\n## Known limitations\n## Related documentation\n```\n\nSection rules:\n\n- README files describe stable user-facing behavior.\n- Do not include temporary implementation notes.\n- Do not include historical chat decisions.\n- Omit sections that are genuinely not applicable only when the source README already omits them.\n\n---\n\n## 11. `FORMAT_CONTEXT.md`\n\nRequired structure:\n\n```text\n# FORMAT_CONTEXT.md\n\n## 1. Global rules\n## 2. Global PROJECT_CONTEXT.md\n## 3. Global SUITE_CONTEXT.md\n## 4. Global BUSINESS_CONTEXT.md\n## 5. Global QA_CONTEXT.md\n## 6. Global SYS_PROMPT.md\n## 7. Project context/PROJECT_CONTEXT.md\n## 8. Project context/QA_CONTEXT.md\n## 9. Project context/DEPLOY_CONTEXT.md\n## 10. Project and suite README.md\n## 11. FORMAT_CONTEXT.md\n## 12. Enforcement rules\n## 13. Document boundary\n```\n\n---\n\n## 12. Enforcement rules\n\nEvery context export and upgrade workflow must:\n\n1. Include this file as a protected format contract.\n2. Make it available to RAG retrieval.\n3. Include its complete contents in the export package.\n4. Never allow ChatGPT to modify it through `context-upgrade`.\n5. Validate every generated context against its required heading structure.\n6. Reject files with missing, renamed, duplicated or reordered required headings.\n7. Allow content changes only inside existing sections.\n8. Reject unexpected top-level sections unless this contract explicitly allows them.\n9. Report structural validation errors before replacement.\n10. Keep the input ZIP untouched when validation fails.\n11. Apply replacements only after all files pass structural validation.\n12. Preserve backup, rollback and atomic replacement behavior.\n\n---\n\n## 13. Document boundary\n\nThis file defines structure only.\n\nIt does not define:\n\n- business behavior;\n- architecture decisions;\n- QA results;\n- deployment status;\n- implementation completion;\n- project priorities.\n'


def _contract_section_heading(archive_path: str) -> str:
    if archive_path == GLOBAL_PROJECT:
        return "## 2. Global `PROJECT_CONTEXT.md`"

    if archive_path == SUITE_CONTEXT:
        return "## 3. Global `SUITE_CONTEXT.md`"

    if archive_path == PROJECT_CONTEXT:
        return "## 7. Project `context/PROJECT_CONTEXT.md`"

    if archive_path in {GLOBAL_README, PROJECT_README}:
        return "## 10. Project and suite `README.md`"

    raise ValueError(f"No format contract for {archive_path}")


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
                {GLOBAL_README: _valid_document(GLOBAL_README, "new readme")},
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
                {GLOBAL_README: _valid_document(GLOBAL_README, "new readme")},
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
                _valid_document(GLOBAL_PROJECT, "new project"),
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
                {GLOBAL_README: _valid_document(GLOBAL_README, "new readme")},
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
                {GLOBAL_README: _valid_document(GLOBAL_README, "new readme")},
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
                GLOBAL_PROJECT: _valid_document(GLOBAL_PROJECT, "new project"),
                SUITE_CONTEXT: _valid_document(SUITE_CONTEXT, "new suite"),
                PROJECT_CONTEXT: _valid_document(PROJECT_CONTEXT, "new project context"),
                PROJECT_README: _valid_document(PROJECT_README, "new project readme"),
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
                    GLOBAL_README: _valid_document(GLOBAL_README, "new readme"),
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
