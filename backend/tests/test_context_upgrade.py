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
from app.services.contexts.contract_registry import (
    PATCH_DEFINITIONS,
    build_contract_version,
    canonical_project_path,
    patch_target_file,
    supported_patch_paths_for_project,
)
from app.services.contexts.file_discovery_service import ContextValidationError


GLOBAL_PROJECT_PATCH = "patches/global-project-context.json"
SUITE_CONTEXT_PATCH = "patches/suite-context.json"
PROJECT_CONTEXT_PATCH = "patches/project-context.json"
PROJECT_README_PATCH = "patches/project-readme.json"
COMPLETED_OBJECTIVES_PATCH = "patches/completed-objectives.json"
GLOBAL_QA_PATCH = "patches/global-qa-context.json"
PROJECT_QA_PATCH = "patches/project-qa-context.json"

GLOBAL_PROJECT = "SBM-SUITE/context/PROJECT_CONTEXT.md"
SUITE_CONTEXT = "SBM-SUITE/context/SUITE_CONTEXT.md"
PROJECT_CONTEXT = "SBM-SUITE/dp/DP-API/context/PROJECT_CONTEXT.md"
PROJECT_README = "SBM-SUITE/dp/DP-API/README.md"
COMPLETED_OBJECTIVES = "SBM-SUITE/context/COMPLETED_OBJECTIVES.md"
GLOBAL_QA = "SBM-SUITE/context/QA_CONTEXT.md"
PROJECT_QA = "SBM-SUITE/dp/DP-API/context/QA_CONTEXT.md"

EXECUTIVE_README = "EXECUTIVE_README.md"
COMMIT_MESSAGE = "COMMIT_MESSAGE.md"
USER_PROMPT = "USER_PROMPT.md"

COMPLETED_TABLE_HEADER = (
    "| Objective ID | Project | Objective | Final status | Priority | Branch | "
    "Started | Completed | Summary | Validation | Documentation | Proposed commit |"
)
COMPLETED_TABLE_SEPARATOR = (
    "|---|---|---|---|---:|---|---|---|---|---|---|---|"
)


FORMAT_CONTRACT = """# FORMAT_CONTEXT.md

## 1. Global rules

Canonical backend contract.

---

## 2. Global `PROJECT_CONTEXT.md`

```text
# PROJECT_CONTEXT.md
## 1. Executive summary
## 2. Suite purpose
## 3. Active objectives
## 4. Pending objectives
## 5. Document boundary
```

---

## 3. Global `COMPLETED_OBJECTIVES.md`

```text
# COMPLETED_OBJECTIVES.md
## 1. Completed objectives by project
## 2. Document boundary
```

---

## 4. Global `SUITE_CONTEXT.md`

```text
# SUITE_CONTEXT.md
## 1. Suite identity
## 2. Product scope
## 3. Document boundary
```

---

## 5. Global `BUSINESS_CONTEXT.md`

```text
# BUSINESS_CONTEXT.md
## 1. Business overview
## 2. Document boundary
```

---

## 6. Global `QA_CONTEXT.md`

```text
# QA_CONTEXT.md
## 1. QA strategy
## 2. Project QA summaries
## 3. Document boundary
```

---

## 7. Global `SECURITY_CONTEXT.md`

```text
# SECURITY_CONTEXT.md
## 1. Security objectives
## 2. Document boundary
```

---

## 8. Global `DATA_CONTEXT.md`

```text
# DATA_CONTEXT.md
## 1. Data architecture overview
## 2. Document boundary
```

---

## 9. Global `DECISIONS_CONTEXT.md`

```text
# DECISIONS_CONTEXT.md
## 1. Decision governance
## 2. Document boundary
```

---

## 10. Global `SYS_PROMPT.md`

Protected.

---

## 11. Project `context/PROJECT_CONTEXT.md`

```text
# PROJECT_CONTEXT.md
## 1. Executive summary
## 2. Project purpose
## 3. Active objectives
## 4. Pending objectives
## 5. Document boundary
```

---

## 12. Project `context/QA_CONTEXT.md`

```text
# QA_CONTEXT.md
## 1. QA strategy
## 2. Current validated evidence
## 3. Document boundary
```

---

## 13. Project `context/DEPLOY_CONTEXT.md`

```text
# DEPLOY_CONTEXT.md
## 1. Deployment overview
## 2. Document boundary
```

---

## 14. Project and suite `README.md`

README headings are repository-owned.

```text
# README.md
## Overview
## Reusable components
## 3. Document boundary
```

### Output patch mappings

""" + "\n\n".join(
    f"{path}\n→ "
    + patch_target_file(path, "dp-api")
    for path, definition in PATCH_DEFINITIONS.items()
) + "\n"


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


def _replace_sections_patch(
    target_file: str,
    sections: list[tuple[str, str]],
) -> str:
    return json.dumps(
        {
            "target_file": target_file,
            "operations": [
                {
                    "operation": "replace_section",
                    "heading": heading,
                    "content": content,
                }
                for heading, content in sections
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
        self.repository_root = root / "SBM-SUITE"
        self.suite_root = self.repository_root / "context"
        self.project_root = root / "SBM-SUITE" / brand / directory_name
        self.input_directory = self.suite_root / "input"
        self.backup_root = self.suite_root / "backup"

        self.input_directory.mkdir(parents=True)
        self.backup_root.mkdir(parents=True)

        _write(self.suite_root / "FORMAT_CONTEXT.md", FORMAT_CONTRACT)
        _write(
            self.suite_root / "PROJECT_CONTEXT.md",
            "# PROJECT_CONTEXT.md\n\n"
            "## 1. Executive summary\n\nOld summary.\n\n"
            "## 2. Suite purpose\n\nOld purpose.\n\n"
            "## 3. Active objectives\n\n"
            "| ID | Project | Objective | Status | Priority | Target date | Branch | Documentation |\n"
            "|---|---|---|---|---:|---|---|---|\n\n"
            "## 4. Pending objectives\n\n"
            "| ID | Project | Objective | Status | Priority | Target date | Branch | Documentation |\n"
            "|---|---|---|---|---:|---|---|---|\n\n"
            "## 5. Document boundary\n\nBoundary.\n",
        )
        _write(
            self.suite_root / "COMPLETED_OBJECTIVES.md",
            "# COMPLETED_OBJECTIVES.md\n\n"
            "## 1. Completed objectives by project\n\n"
            "No completed objectives have been migrated into this register yet.\n\n"
            "The following fenced example is documentation, not a real group:\n\n"
            "```text\n"
            "### <project>\n\n"
            f"{COMPLETED_TABLE_HEADER}\n"
            f"{COMPLETED_TABLE_SEPARATOR}\n"
            "```\n\n"
            "## 2. Document boundary\n\nBoundary.\n",
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
            self.suite_root / "QA_CONTEXT.md",
            "# QA_CONTEXT.md\n\n"
            "## 1. QA strategy\n\nValidated QA.\n\n"
            "## 2. Project QA summaries\n\n"
            "| Project | Status | Evidence |\n"
            "|---|---|---|\n"
            "| SBM-API | passing | existing |\n\n"
            "## 3. Document boundary\n\nBoundary.\n",
        )
        _write(
            self.project_root / "context/PROJECT_CONTEXT.md",
            "# PROJECT_CONTEXT.md\n\n"
            "## 1. Executive summary\n\nOld summary.\n\n"
            "## 2. Project purpose\n\nOld purpose.\n\n"
            "## 3. Active objectives\n\n"
            "| ID | Objective | Status | Priority | Target date | Branch | Documentation |\n"
            "|---|---|---|---:|---|---|---|\n\n"
            "## 4. Pending objectives\n\n"
            "| ID | Objective | Status | Priority | Target date | Branch | Documentation |\n"
            "|---|---|---|---:|---|---|---|\n\n"
            "## 5. Document boundary\n\nBoundary.\n",
        )
        _write(
            self.project_root / "README.md",
            "# README.md\n\n"
            "## Overview\n\nOld first section.\n\n"
            "## Reusable components\n\n"
            "| File name | Path | Description |\n"
            "|---|---|---|\n"
            "| existing-service.py | backend/app/services/ | Existing service |\n"
            "| existing-model.py | backend/app/models/ | Existing model |\n\n"
            "## 3. Document boundary\n\nBoundary.\n",
        )
        _write(
            self.project_root / "context/QA_CONTEXT.md",
            "# QA_CONTEXT.md\n\n"
            "## 1. QA strategy\n\nValidated QA.\n\n"
            "## 2. Current validated evidence\n\n"
            "| Test | Result | Evidence |\n"
            "|---|---|---|\n"
            "| Existing | passed | baseline |\n\n"
            "## 3. Document boundary\n\nBoundary.\n",
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
    lifecycle_phase: str = "implementation-progress",
    objective_id: str | None = "OBJ-001",
    objectives: list[dict] | None = None,
) -> None:
    files = {
        EXECUTIVE_README: "Context upgrade summary\n",
        COMMIT_MESSAGE: "docs(contexts): update project context\n",
        **patches,
    }
    if user_prompt is not None:
        files[USER_PROMPT] = user_prompt

    if objectives is None:
        if objective_id is None:
            objectives = []
        elif lifecycle_phase == "planning-activation":
            objectives = [
                {
                    "objective_id": objective_id,
                    "objective": "Enable Material",
                    "status": "active",
                    "priority": 5,
                    "target_date": "N/A",
                    "branch": "FEATURE-enable-material",
                }
            ]
        else:
            objectives = [{"objective_id": objective_id}]

    manifest = {
        "project_name": project_name,
        "workflow": "context-upgrade",
        "contract_version": build_contract_version(
            (path.parent.parent / "FORMAT_CONTEXT.md").read_text(encoding="utf-8")
        ),
        "supported_patch_paths": supported_patch_paths_for_project(project_name),
        "canonical_project_path": canonical_project_path(project_name),
        "lifecycle_phase": lifecycle_phase,
        "objectives": objectives,
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
        "qa": {"status": "passed"},
    }
    if manifest_updates:
        manifest.update(manifest_updates)

    with ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
        archive.writestr("manifest.json", json.dumps(manifest))


def _seed_active_objectives(
    env: UpgradeEnvironment,
    objective_ids: tuple[str, ...] = ("OBJ-001",),
) -> None:
    global_rows = "".join(
        f"| {objective_id} | DP-API | Objective {objective_id} | active | 5 |  | FEATURE-{objective_id.casefold()} | N/A |\n"
        for objective_id in objective_ids
    )
    project_rows = "".join(
        f"| {objective_id} | Objective {objective_id} | active | 5 |  | FEATURE-{objective_id.casefold()} | N/A |\n"
        for objective_id in objective_ids
    )
    global_path = env.suite_root / "PROJECT_CONTEXT.md"
    project_path = env.project_root / "context/PROJECT_CONTEXT.md"
    global_path.write_text(
        global_path.read_text(encoding="utf-8").replace(
            "|---|---|---|---|---:|---|---|---|\n\n",
            "|---|---|---|---|---:|---|---|---|\n" + global_rows + "\n",
            1,
        ),
        encoding="utf-8",
    )
    project_path.write_text(
        project_path.read_text(encoding="utf-8").replace(
            "|---|---|---|---:|---|---|---|\n\n",
            "|---|---|---|---:|---|---|---|\n" + project_rows + "\n",
            1,
        ),
        encoding="utf-8",
    )


def _seed_suite_pending_objective(env: UpgradeEnvironment) -> None:
    global_path = env.suite_root / "PROJECT_CONTEXT.md"
    markdown = global_path.read_text(encoding="utf-8")
    pending_table = (
        "## 4. Pending objectives\n\n"
        "| ID | Project | Objective | Status | Priority | Target date | Branch | Documentation |\n"
        "|---|---|---|---|---:|---|---|---|\n"
    )
    existing_row = (
        "| OBJ-CTX-010 | SBM-SUITE | Existing suite objective | pending | 3 | "
        "N/A | FEATURE-existing-suite-objective | N/A |\n"
    )
    if markdown.count(pending_table) != 1:
        raise AssertionError("Missing unique suite pending objectives table")
    global_path.write_text(
        markdown.replace(pending_table, pending_table + existing_row, 1),
        encoding="utf-8",
    )


def _activation_objective(
    objective_id: str = "OBJ-CTX-013",
    *,
    status: str = "active",
) -> dict:
    return {
        "objective_id": objective_id,
        "objective": "Fix context documentation lifecycle",
        "status": status,
        "priority": 5,
        "target_date": "N/A",
        "branch": "BUGFIX-fixes-context-workflow",
    }


def _seed_pending_objectives(
    env: UpgradeEnvironment,
    objectives: list[dict],
    *,
    suite_only: bool = False,
) -> None:
    global_rows = "".join(
        "| {objective_id} | {project} | {objective} | pending | {priority} | "
        "{target_date} | {branch} | N/A |\n".format(
            project="SBM-SUITE" if suite_only else "DP-API",
            **objective,
        )
        for objective in objectives
    )
    global_path = env.suite_root / "PROJECT_CONTEXT.md"
    global_table = (
        "## 4. Pending objectives\n\n"
        "| ID | Project | Objective | Status | Priority | Target date | Branch | Documentation |\n"
        "|---|---|---|---|---:|---|---|---|\n"
    )
    global_markdown = global_path.read_text(encoding="utf-8")
    global_path.write_text(
        global_markdown.replace(global_table, global_table + global_rows, 1),
        encoding="utf-8",
    )

    if suite_only:
        return

    project_rows = "".join(
        "| {objective_id} | {objective} | pending | {priority} | {target_date} | "
        "{branch} | N/A |\n".format(**objective)
        for objective in objectives
    )
    project_path = env.project_root / "context/PROJECT_CONTEXT.md"
    project_table = (
        "## 4. Pending objectives\n\n"
        "| ID | Objective | Status | Priority | Target date | Branch | Documentation |\n"
        "|---|---|---|---:|---|---|---|\n"
    )
    project_markdown = project_path.read_text(encoding="utf-8")
    project_path.write_text(
        project_markdown.replace(project_table, project_table + project_rows, 1),
        encoding="utf-8",
    )


def _activation_patches(
    objective: dict,
    *,
    remaining_pending: list[dict] | None = None,
    suite_only: bool = False,
) -> dict[str, str]:
    remaining_pending = remaining_pending or []
    project_label = "SBM-SUITE" if suite_only else "DP-API"
    global_active = (
        "## 3. Active objectives\n\n"
        "| ID | Project | Objective | Status | Priority | Target date | Branch | Documentation |\n"
        "|---|---|---|---|---:|---|---|---|\n"
        "| {objective_id} | {project} | {objective} | active | {priority} | "
        "{target_date} | {branch} | N/A |\n"
    ).format(project=project_label, **objective)
    global_pending_rows = "".join(
        "| {objective_id} | {project} | {objective} | pending | {priority} | "
        "{target_date} | {branch} | N/A |\n".format(
            project=project_label,
            **pending,
        )
        for pending in remaining_pending
    )
    global_pending = (
        "## 4. Pending objectives\n\n"
        "| ID | Project | Objective | Status | Priority | Target date | Branch | Documentation |\n"
        "|---|---|---|---|---:|---|---|---|\n"
        + global_pending_rows
    )
    patches = {
        GLOBAL_PROJECT_PATCH: _replace_sections_patch(
            GLOBAL_PROJECT,
            [
                ("## 3. Active objectives", global_active),
                ("## 4. Pending objectives", global_pending),
            ],
        )
    }
    if suite_only:
        return patches

    project_active = (
        "## 3. Active objectives\n\n"
        "| ID | Objective | Status | Priority | Target date | Branch | Documentation |\n"
        "|---|---|---|---:|---|---|---|\n"
        "| {objective_id} | {objective} | active | {priority} | {target_date} | "
        "{branch} | N/A |\n"
    ).format(**objective)
    project_pending_rows = "".join(
        "| {objective_id} | {objective} | pending | {priority} | {target_date} | "
        "{branch} | N/A |\n".format(**pending)
        for pending in remaining_pending
    )
    project_pending = (
        "## 4. Pending objectives\n\n"
        "| ID | Objective | Status | Priority | Target date | Branch | Documentation |\n"
        "|---|---|---|---:|---|---|---|\n"
        + project_pending_rows
    )
    patches[PROJECT_CONTEXT_PATCH] = _replace_sections_patch(
        PROJECT_CONTEXT,
        [
            ("## 3. Active objectives", project_active),
            ("## 4. Pending objectives", project_pending),
        ],
    )
    return patches


def _suite_planning_objectives() -> list[dict]:
    return [
        {
            "objective_id": "OBJ-CTX-011",
            "objective": "Strengthen context preflight",
            "status": "pending",
            "priority": 5,
            "target_date": "N/A",
            "branch": "FEATURE-strengthen-context-preflight",
        },
        {
            "objective_id": "OBJ-CTX-012",
            "objective": "Document context validation",
            "status": "pending",
            "priority": 4,
            "target_date": "2026-08-20",
            "branch": "FEATURE-document-context-validation",
        },
    ]


def _suite_pending_section(*, blank_before_objective: str | None = None) -> str:
    rows = [
        (
            "OBJ-CTX-010",
            "Existing suite objective",
            "3",
            "N/A",
            "FEATURE-existing-suite-objective",
        ),
        (
            "OBJ-CTX-011",
            "Strengthen context preflight",
            "5",
            "N/A",
            "FEATURE-strengthen-context-preflight",
        ),
        (
            "OBJ-CTX-012",
            "Document context validation",
            "4",
            "2026-08-20",
            "FEATURE-document-context-validation",
        ),
    ]
    rendered_rows = ""
    for objective_id, objective, priority, target_date, branch in rows:
        if objective_id == blank_before_objective:
            rendered_rows += "\n"
        rendered_rows += (
            f"| {objective_id} | SBM-SUITE | {objective} | pending | {priority} | "
            f"{target_date} | {branch} | N/A |\n"
        )
    return (
        "## 4. Pending objectives\n\n"
        "| ID | Project | Objective | Status | Priority | Target date | Branch | Documentation |\n"
        "|---|---|---|---|---:|---|---|---|\n"
        f"{rendered_rows}"
    )


def _run_suite_context_upgrade(env: UpgradeEnvironment):
    return upgrade_contexts(
        input_directory=str(env.input_directory),
        suite_context_root=str(env.suite_root),
        project_root=str(env.repository_root),
        backup_root=str(env.backup_root),
        now=lambda: datetime(2026, 7, 30, 10, 11, 12),
    )


def _completed_row(
    objective_id: str = "OBJ-001",
    objective: str | None = None,
) -> str:
    objective_text = objective or f"Objective {objective_id}"
    return (
        f"| {objective_id} | DP-API | {objective_text} | completed | 5 | "
        f"FEATURE-{objective_id.casefold()} | 2026-08-02 | 2026-08-02 | "
        "Completed | QA passed | N/A | feat: close |"
    )


def _completed_project_group(row: str) -> str:
    return (
        "### DP-API\n\n"
        f"{COMPLETED_TABLE_HEADER}\n"
        f"{COMPLETED_TABLE_SEPARATOR}\n"
        f"{row}"
    )


def _seed_completed_project_group(
    env: UpgradeEnvironment,
    rows: tuple[str, ...] = (),
) -> None:
    completed = env.suite_root / "COMPLETED_OBJECTIVES.md"
    markdown = completed.read_text(encoding="utf-8")
    markdown = markdown.replace(
        "No completed objectives have been migrated into this register yet.\n\n",
        "",
        1,
    )
    group_rows = "".join(f"{row}\n" for row in rows)
    group = (
        "### DP-API\n\n"
        f"{COMPLETED_TABLE_HEADER}\n"
        f"{COMPLETED_TABLE_SEPARATOR}\n"
        f"{group_rows}\n"
    )
    markdown = markdown.replace(
        "## 2. Document boundary",
        group + "## 2. Document boundary",
        1,
    )
    completed.write_text(markdown, encoding="utf-8")


def _completed_replace_patch(env: UpgradeEnvironment, row: str) -> str:
    markdown = (env.suite_root / "COMPLETED_OBJECTIVES.md").read_text(
        encoding="utf-8"
    )
    start = markdown.index("## 1. Completed objectives by project")
    end = markdown.index("## 2. Document boundary")
    section = markdown[start:end].rstrip()
    prefix, group = section.split("### DP-API", 1)
    separator = COMPLETED_TABLE_SEPARATOR + "\n"
    if separator not in group:
        raise AssertionError("Missing completed objectives table separator")
    group = group.replace(separator, separator + row + "\n", 1)
    replacement = prefix + "### DP-API" + group
    return _replace_patch(
        COMPLETED_OBJECTIVES,
        "## 1. Completed objectives by project",
        replacement,
    )


def _closure_patches() -> dict[str, str]:
    completed_row = _completed_row()
    return {
        GLOBAL_PROJECT_PATCH: _replace_patch(
            GLOBAL_PROJECT,
            "## 3. Active objectives",
            "## 3. Active objectives\n\n"
            "| ID | Project | Objective | Status | Priority | Target date | Branch | Documentation |\n"
            "|---|---|---|---|---:|---|---|---|\n",
        ),
        PROJECT_CONTEXT_PATCH: _replace_patch(
            PROJECT_CONTEXT,
            "## 3. Active objectives",
            "## 3. Active objectives\n\n"
            "| ID | Objective | Status | Priority | Target date | Branch | Documentation |\n"
            "|---|---|---|---:|---|---|---|\n",
        ),
        COMPLETED_OBJECTIVES_PATCH: _append_patch(
            COMPLETED_OBJECTIVES,
            "## 1. Completed objectives by project",
            _completed_project_group(completed_row),
        ),
        GLOBAL_QA_PATCH: _replace_patch(
            GLOBAL_QA,
            "## 1. QA strategy",
            "## 1. QA strategy\n\nValidated closure QA.\n",
        ),
        PROJECT_QA_PATCH: _replace_patch(
            PROJECT_QA,
            "## 1. QA strategy",
            "## 1. QA strategy\n\nValidated closure QA.\n",
        ),
    }


class ContextUpgradeTests(unittest.TestCase):
    def test_contract_version_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(
                env.zip_path,
                {
                    GLOBAL_PROJECT_PATCH: _replace_patch(
                        GLOBAL_PROJECT,
                        "## 2. Suite purpose",
                        "## 2. Suite purpose\n\nUpdated.\n",
                    )
                },
                manifest_updates={"contract_version": "0" * 64},
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "contract_version does not match",
            ):
                env.run()

    def test_format_context_backend_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(
                env.zip_path,
                {
                    GLOBAL_PROJECT_PATCH: _replace_patch(
                        GLOBAL_PROJECT,
                        "## 2. Suite purpose",
                        "## 2. Suite purpose\n\nUpdated.\n",
                    )
                },
            )
            format_path = env.suite_root / "FORMAT_CONTEXT.md"
            format_path.write_text(
                format_path.read_text(encoding="utf-8").replace(
                    "## 14. Project and suite `README.md`",
                    "## 13. Project and suite `README.md`",
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "unique and sequential",
            ):
                env.run()

    def test_missing_lifecycle_phase_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            patch_content = _replace_patch(
                GLOBAL_PROJECT,
                "## 2. Suite purpose",
                "## 2. Suite purpose\n\nUpdated.\n",
            )
            _create_upgrade_zip(
                env.zip_path,
                {GLOBAL_PROJECT_PATCH: patch_content},
                manifest_updates={"lifecycle_phase": None},
            )
            with self.assertRaisesRegex(ContextValidationError, "is required"):
                env.run()

    def test_invalid_lifecycle_phase_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            patch_content = _replace_patch(
                GLOBAL_PROJECT,
                "## 2. Suite purpose",
                "## 2. Suite purpose\n\nUpdated.\n",
            )
            _create_upgrade_zip(
                env.zip_path,
                {GLOBAL_PROJECT_PATCH: patch_content},
                manifest_updates={"lifecycle_phase": "finished"},
            )
            with self.assertRaisesRegex(ContextValidationError, "not supported"):
                env.run()

    def test_closure_without_objective_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(
                env.zip_path,
                _closure_patches(),
                lifecycle_phase="implementation-closure",
                objective_id=None,
            )
            with self.assertRaisesRegex(ContextValidationError, "objectives"):
                env.run()

    def test_closure_without_completed_patch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            patches = _closure_patches()
            patches.pop(COMPLETED_OBJECTIVES_PATCH)
            _create_upgrade_zip(
                env.zip_path,
                patches,
                lifecycle_phase="implementation-closure",
            )
            with self.assertRaisesRegex(
                ContextValidationError,
                "missing required patches",
            ):
                env.run()

    def test_closure_without_qa_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(
                env.zip_path,
                _closure_patches(),
                lifecycle_phase="implementation-closure",
                manifest_updates={"qa": None},
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "implementation-closure requires successful QA",
            ):
                env.run()

    def test_closure_with_failed_qa_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(
                env.zip_path,
                _closure_patches(),
                lifecycle_phase="implementation-closure",
                manifest_updates={"qa": {"status": "failed"}},
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "implementation-closure requires successful QA",
            ):
                env.run()

    def test_closure_with_successful_qa_manifest_is_accepted(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            _seed_active_objectives(env)
            _create_upgrade_zip(
                env.zip_path,
                _closure_patches(),
                lifecycle_phase="implementation-closure",
                manifest_updates={"qa": {"status": "passed"}},
            )

            response = env.run()

            self.assertEqual(response.project_name, "dp-api")
            self.assertTrue(response.input_cleaned)

    def test_planning_with_completed_patch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(
                env.zip_path,
                {COMPLETED_OBJECTIVES_PATCH: _closure_patches()[COMPLETED_OBJECTIVES_PATCH]},
                execution_mode="user-guided",
                user_prompt="Plan objective.",
                lifecycle_phase="planning-activation",
            )
            with self.assertRaises(ContextValidationError):
                env.run()

    def test_progress_with_completed_patch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(
                env.zip_path,
                {COMPLETED_OBJECTIVES_PATCH: _closure_patches()[COMPLETED_OBJECTIVES_PATCH]},
            )
            with self.assertRaises(ContextValidationError):
                env.run()
    def test_manifest_contract_accepts_manifest_only_in_allowed_files(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            patch_content = _replace_patch(
                GLOBAL_PROJECT,
                "## 2. Suite purpose",
                "## 2. Suite purpose\n\nContract-compliant update.\n",
            )
            _create_upgrade_zip(
                env.zip_path,
                {GLOBAL_PROJECT_PATCH: patch_content},
            )

            response = env.run()

            self.assertEqual(response.updated_files, [GLOBAL_PROJECT])

    def test_manifest_contract_rejects_manifest_missing_from_allowed_files(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            patch_content = _replace_patch(
                GLOBAL_PROJECT,
                "## 2. Suite purpose",
                "## 2. Suite purpose\n\nUpdated.\n",
            )
            _create_upgrade_zip(
                env.zip_path,
                {GLOBAL_PROJECT_PATCH: patch_content},
                manifest_updates={
                    "allowed_files": [
                        EXECUTIVE_README,
                        COMMIT_MESSAGE,
                        GLOBAL_PROJECT_PATCH,
                    ]
                },
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "allowed_files must include manifest.json",
            ):
                env.run()

    def test_manifest_contract_rejects_manifest_in_updated_files(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            patch_content = _replace_patch(
                GLOBAL_PROJECT,
                "## 2. Suite purpose",
                "## 2. Suite purpose\n\nUpdated.\n",
            )
            _create_upgrade_zip(
                env.zip_path,
                {GLOBAL_PROJECT_PATCH: patch_content},
                manifest_updates={
                    "updated_files": [
                        EXECUTIVE_README,
                        COMMIT_MESSAGE,
                        GLOBAL_PROJECT_PATCH,
                        "manifest.json",
                    ]
                },
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "updated_files must not include manifest.json",
            ):
                env.run()

    def test_manifest_contract_rejects_manifest_in_content_hashes(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            patch_content = _replace_patch(
                GLOBAL_PROJECT,
                "## 2. Suite purpose",
                "## 2. Suite purpose\n\nUpdated.\n",
            )
            content_hashes = {
                EXECUTIVE_README: hashlib.sha256(
                    b"Context upgrade summary\n"
                ).hexdigest(),
                COMMIT_MESSAGE: hashlib.sha256(
                    b"docs(contexts): update project context\n"
                ).hexdigest(),
                GLOBAL_PROJECT_PATCH: hashlib.sha256(
                    patch_content.encode("utf-8")
                ).hexdigest(),
                "manifest.json": "0" * 64,
            }
            _create_upgrade_zip(
                env.zip_path,
                {GLOBAL_PROJECT_PATCH: patch_content},
                manifest_updates={"content_hashes": content_hashes},
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "content_hashes must not include manifest.json",
            ):
                env.run()

    def test_manifest_contract_rejects_updated_files_not_matching_zip(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            patch_content = _replace_patch(
                GLOBAL_PROJECT,
                "## 2. Suite purpose",
                "## 2. Suite purpose\n\nUpdated.\n",
            )
            _create_upgrade_zip(
                env.zip_path,
                {GLOBAL_PROJECT_PATCH: patch_content},
                manifest_updates={
                    "updated_files": [EXECUTIVE_README, COMMIT_MESSAGE]
                },
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "updated_files must match non-manifest ZIP files",
            ):
                env.run()

    def test_manifest_contract_rejects_hash_keys_not_matching_updated_files(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            patch_content = _replace_patch(
                GLOBAL_PROJECT,
                "## 2. Suite purpose",
                "## 2. Suite purpose\n\nUpdated.\n",
            )
            content_hashes = {
                EXECUTIVE_README: hashlib.sha256(
                    b"Context upgrade summary\n"
                ).hexdigest(),
                GLOBAL_PROJECT_PATCH: hashlib.sha256(
                    patch_content.encode("utf-8")
                ).hexdigest(),
            }
            _create_upgrade_zip(
                env.zip_path,
                {GLOBAL_PROJECT_PATCH: patch_content},
                manifest_updates={"content_hashes": content_hashes},
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "content_hashes keys must match manifest.updated_files",
            ):
                env.run()

    def test_valid_global_patch_creates_backup_applies_and_cleans_input(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            target = env.suite_root / "PROJECT_CONTEXT.md"
            old_mode = stat.S_IMODE(target.stat().st_mode)

            patch_content = "## 2. Suite purpose\n\n" "New suite purpose.\n"
            _create_upgrade_zip(
                env.zip_path,
                {
                    GLOBAL_PROJECT_PATCH: _replace_patch(
                        GLOBAL_PROJECT,
                        "## 2. Suite purpose",
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
            self.assertIn("New suite purpose.", target.read_text(encoding="utf-8"))
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), old_mode)

            backup = env.repository_root / response.backup_directory
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
                [item["original_path"] for item in backup_manifest["backed_up_files"]],
                [GLOBAL_PROJECT],
            )

    def test_all_allowlisted_projects_can_apply_their_own_patch(self):
        projects = (
            ("dp-api", "dp", "DP-API"),
            ("sbm-api", "sbm", "SBM-API"),
            ("sbm-db", "sbm", "SBM-DB"),
            ("sbm-manager", "sbm", "SBM-MANAGER"),
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
                        "|---|---|---|\n"
                        "| existing-service.py | backend/app/services/ | Existing service |\n"
                        "| existing-model.py | backend/app/models/ | Existing model |\n"
                        "| registry | services/ | allowlist |\n",
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

    def test_append_to_current_section_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(
                env.zip_path,
                {
                    GLOBAL_PROJECT_PATCH: _append_patch(
                        GLOBAL_PROJECT,
                        "## 2. Suite purpose",
                        "Additional validated suite detail.",
                    )
                },
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "operation forbidden by PATCH_DEFINITIONS",
            ):
                env.run()

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
            backup = env.repository_root / response.backup_directory

            self.assertEqual(
                (backup / USER_PROMPT).read_text(encoding="utf-8"),
                "Actualizar el propósito del proyecto.",
            )

    def test_planning_activation_requires_global_and_project_objective_patches(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(
                env.zip_path,
                {
                    PROJECT_CONTEXT_PATCH: _replace_patch(
                        PROJECT_CONTEXT,
                        "## 3. Active objectives",
                        "## 3. Active objectives\n\n"
                        "| ID | Objective | Status | Priority | Target date | Branch | Documentation |\n"
                        "|---|---|---|---:|---|---|---|\n"
                        "| OBJ-001 | Enable Material | active | 5 | N/A | FEATURE-enable-material | N/A |\n",
                    )
                },
                execution_mode="user-guided",
                user_prompt="Agregar el módulo Material en DP-API.",
                lifecycle_phase="planning-activation",
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "require both global-project-context.json and project-context.json",
            ):
                env.run()

    def test_planning_activation_updates_global_and_project_contexts(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(
                env.zip_path,
                {
                    GLOBAL_PROJECT_PATCH: _replace_patch(
                        GLOBAL_PROJECT,
                        "## 3. Active objectives",
                        "## 3. Active objectives\n\n"
                        "| ID | Project | Objective | Status | Priority | Target date | Branch | Documentation |\n"
                        "|---|---|---|---|---:|---|---|---|\n"
                        "| OBJ-001 | DP-API | Enable Material | active | 5 | N/A | FEATURE-enable-material | N/A |\n",
                    ),
                    PROJECT_CONTEXT_PATCH: _replace_patch(
                        PROJECT_CONTEXT,
                        "## 3. Active objectives",
                        "## 3. Active objectives\n\n"
                        "| ID | Objective | Status | Priority | Target date | Branch | Documentation |\n"
                        "|---|---|---|---:|---|---|---|\n"
                        "| OBJ-001 | Enable Material | active | 5 | N/A | FEATURE-enable-material | N/A |\n",
                    ),
                },
                execution_mode="user-guided",
                user_prompt="Agregar el módulo Material en DP-API.",
                lifecycle_phase="planning-activation",
            )

            response = env.run()

            self.assertEqual(
                response.updated_files,
                sorted([GLOBAL_PROJECT, PROJECT_CONTEXT]),
            )
            self.assertIn(
                "FEATURE-enable-material",
                (env.suite_root / "PROJECT_CONTEXT.md").read_text(encoding="utf-8"),
            )
            self.assertIn(
                "FEATURE-enable-material",
                (env.project_root / "context/PROJECT_CONTEXT.md").read_text(
                    encoding="utf-8"
                ),
            )

    def test_objective_activation_moves_pending_to_active_project_scoped(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            objective = _activation_objective()
            unrelated = {
                **_activation_objective("OBJ-DP-099"),
                "objective": "Preserve unrelated pending objective",
                "branch": "FEATURE-preserves-pending-objective",
            }
            _seed_pending_objectives(env, [objective, unrelated])
            _create_upgrade_zip(
                env.zip_path,
                _activation_patches(
                    objective,
                    remaining_pending=[unrelated],
                ),
                lifecycle_phase="objective-activation",
                objectives=[objective],
            )

            response = env.run()

            self.assertEqual(
                response.updated_files,
                sorted([GLOBAL_PROJECT, PROJECT_CONTEXT]),
            )
            for context_path in (
                env.suite_root / "PROJECT_CONTEXT.md",
                env.project_root / "context/PROJECT_CONTEXT.md",
            ):
                markdown = context_path.read_text(encoding="utf-8")
                active_section, pending_section = markdown.split(
                    "## 4. Pending objectives",
                    1,
                )
                self.assertEqual(markdown.count(objective["objective_id"]), 1)
                self.assertIn(objective["objective_id"], active_section)
                self.assertNotIn(objective["objective_id"], pending_section)
                self.assertIn(unrelated["objective_id"], pending_section)
                for field in (
                    "objective",
                    "priority",
                    "target_date",
                    "branch",
                ):
                    self.assertIn(str(objective[field]), active_section)

    def test_suite_context_objective_activation_supports_obj_ctx_013(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            objective = _activation_objective("OBJ-CTX-013")
            _seed_pending_objectives(env, [objective], suite_only=True)
            _create_upgrade_zip(
                env.zip_path,
                _activation_patches(objective, suite_only=True),
                project_name="sbm-suite-context",
                lifecycle_phase="objective-activation",
                objectives=[objective],
            )

            response = _run_suite_context_upgrade(env)

            self.assertEqual(response.project_name, "sbm-suite-context")
            self.assertEqual(response.updated_files, [GLOBAL_PROJECT])
            markdown = (env.suite_root / "PROJECT_CONTEXT.md").read_text(
                encoding="utf-8"
            )
            active_section, pending_section = markdown.split(
                "## 4. Pending objectives",
                1,
            )
            self.assertEqual(markdown.count("OBJ-CTX-013"), 1)
            self.assertIn("OBJ-CTX-013", active_section)
            self.assertNotIn("OBJ-CTX-013", pending_section)

    def test_objective_activation_rejects_missing_pending_objective(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            objective = _activation_objective()
            _create_upgrade_zip(
                env.zip_path,
                _activation_patches(objective),
                lifecycle_phase="objective-activation",
                objectives=[objective],
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "pending objective must exist exactly once: OBJ-CTX-013",
            ):
                env.run()

    def test_objective_activation_requires_all_project_scoped_context_patches(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            objective = _activation_objective()
            _seed_pending_objectives(env, [objective])
            patches = _activation_patches(objective)
            _create_upgrade_zip(
                env.zip_path,
                {GLOBAL_PROJECT_PATCH: patches[GLOBAL_PROJECT_PATCH]},
                lifecycle_phase="objective-activation",
                objectives=[objective],
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "requires objective context patches: patches/project-context.json",
            ):
                env.run()

    def test_objective_activation_rejects_already_active_objective(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            objective = _activation_objective("OBJ-001")
            _seed_active_objectives(env)
            _create_upgrade_zip(
                env.zip_path,
                _activation_patches(objective),
                lifecycle_phase="objective-activation",
                objectives=[objective],
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "already active: OBJ-001",
            ):
                env.run()

    def test_objective_activation_rejects_completed_objective(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            objective = _activation_objective("OBJ-001")
            _seed_completed_project_group(env, (_completed_row(),))
            _create_upgrade_zip(
                env.zip_path,
                _activation_patches(objective),
                lifecycle_phase="objective-activation",
                objectives=[objective],
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "cannot activate completed objective: OBJ-001",
            ):
                env.run()

    def test_objective_activation_rejects_requested_pending_status(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            current = _activation_objective()
            requested = _activation_objective(status="pending")
            _seed_pending_objectives(env, [current])
            _create_upgrade_zip(
                env.zip_path,
                _activation_patches(current),
                lifecycle_phase="objective-activation",
                objectives=[requested],
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "requested status must be active",
            ):
                env.run()

    def test_objective_activation_rejects_changes_beyond_status(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            objective = _activation_objective()
            _seed_pending_objectives(env, [objective])
            patches = {
                patch_path: payload.replace(
                    "BUGFIX-fixes-context-workflow | N/A |\\n",
                    "BUGFIX-fixes-context-workflow | changed-docs |\\n",
                    1,
                )
                for patch_path, payload in _activation_patches(objective).items()
            }
            _create_upgrade_zip(
                env.zip_path,
                patches,
                lifecycle_phase="objective-activation",
                objectives=[objective],
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "may change only the status cell: OBJ-CTX-013",
            ):
                env.run()

    def test_planning_activation_rejects_existing_operational_id(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            objective = _activation_objective()
            _seed_pending_objectives(env, [objective])
            _create_upgrade_zip(
                env.zip_path,
                _activation_patches(objective),
                lifecycle_phase="planning-activation",
                objectives=[objective],
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "cannot reuse existing objective IDs: OBJ-CTX-013",
            ):
                env.run()

    def test_planning_activation_rejects_completed_id(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            objective = _activation_objective("OBJ-001")
            _seed_completed_project_group(env, (_completed_row(),))
            _create_upgrade_zip(
                env.zip_path,
                _activation_patches(objective),
                lifecycle_phase="planning-activation",
                objectives=[objective],
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "cannot reuse completed objective IDs: OBJ-001",
            ):
                env.run()

    def test_planning_activation_applies_multiple_pending_objectives_atomically(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            objectives = [
                {
                    "objective_id": "OBJ-001",
                    "objective": "Enable Material",
                    "status": "pending",
                    "priority": 5,
                    "target_date": "N/A",
                    "branch": "FEATURE-enable-material",
                },
                {
                    "objective_id": "OBJ-002",
                    "objective": "Enable Orders",
                    "status": "pending",
                    "priority": 4,
                    "target_date": "2026-08-20",
                    "branch": "FEATURE-enable-orders",
                },
            ]
            _create_upgrade_zip(
                env.zip_path,
                {
                    GLOBAL_PROJECT_PATCH: _replace_patch(
                        GLOBAL_PROJECT,
                        "## 4. Pending objectives",
                        "## 4. Pending objectives\n\n"
                        "| ID | Project | Objective | Status | Priority | Target date | Branch | Documentation |\n"
                        "|---|---|---|---|---:|---|---|---|\n"
                        "| OBJ-001 | DP-API | Enable Material | pending | 5 | N/A | FEATURE-enable-material | N/A |\n"
                        "| OBJ-002 | DP-API | Enable Orders | pending | 4 | 2026-08-20 | FEATURE-enable-orders | N/A |\n",
                    ),
                    PROJECT_CONTEXT_PATCH: _replace_patch(
                        PROJECT_CONTEXT,
                        "## 4. Pending objectives",
                        "## 4. Pending objectives\n\n"
                        "| ID | Objective | Status | Priority | Target date | Branch | Documentation |\n"
                        "|---|---|---|---:|---|---|---|\n"
                        "| OBJ-001 | Enable Material | pending | 5 | N/A | FEATURE-enable-material | N/A |\n"
                        "| OBJ-002 | Enable Orders | pending | 4 | 2026-08-20 | FEATURE-enable-orders | N/A |\n",
                    ),
                },
                lifecycle_phase="planning-activation",
                objectives=objectives,
            )

            response = env.run()
            self.assertEqual(
                response.updated_files,
                sorted([GLOBAL_PROJECT, PROJECT_CONTEXT]),
            )
            global_context = (env.suite_root / "PROJECT_CONTEXT.md").read_text(
                encoding="utf-8"
            )
            local_context = (
                env.project_root / "context/PROJECT_CONTEXT.md"
            ).read_text(encoding="utf-8")
            for objective in objectives:
                self.assertEqual(
                    global_context.count(objective["objective_id"]),
                    1,
                )
                self.assertEqual(
                    local_context.count(objective["objective_id"]),
                    1,
                )

    def test_planning_activation_rejects_field_divergence_in_batch(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            objectives = [
                {
                    "objective_id": "OBJ-001",
                    "objective": "Enable Material",
                    "status": "pending",
                    "priority": 5,
                    "target_date": "N/A",
                    "branch": "FEATURE-enable-material",
                },
                {
                    "objective_id": "OBJ-002",
                    "objective": "Enable Orders",
                    "status": "pending",
                    "priority": 4,
                    "target_date": "N/A",
                    "branch": "FEATURE-enable-orders",
                },
            ]
            _create_upgrade_zip(
                env.zip_path,
                {
                    GLOBAL_PROJECT_PATCH: _replace_patch(
                        GLOBAL_PROJECT,
                        "## 4. Pending objectives",
                        "## 4. Pending objectives\n\n"
                        "| ID | Project | Objective | Status | Priority | Target date | Branch | Documentation |\n"
                        "|---|---|---|---|---:|---|---|---|\n"
                        "| OBJ-001 | DP-API | Enable Material | pending | 5 | N/A | FEATURE-enable-material | N/A |\n"
                        "| OBJ-002 | DP-API | WRONG DESCRIPTION | pending | 4 | N/A | FEATURE-enable-orders | N/A |\n",
                    ),
                    PROJECT_CONTEXT_PATCH: _replace_patch(
                        PROJECT_CONTEXT,
                        "## 4. Pending objectives",
                        "## 4. Pending objectives\n\n"
                        "| ID | Objective | Status | Priority | Target date | Branch | Documentation |\n"
                        "|---|---|---|---:|---|---|---|\n"
                        "| OBJ-001 | Enable Material | pending | 5 | N/A | FEATURE-enable-material | N/A |\n"
                        "| OBJ-002 | Enable Orders | pending | 4 | N/A | FEATURE-enable-orders | N/A |\n",
                    ),
                },
                lifecycle_phase="planning-activation",
                objectives=objectives,
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "diverges from manifest.objectives",
            ):
                env.run()

    def test_planning_activation_rejects_markdown_wrapped_branch(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            objectives = [
                {
                    "objective_id": "OBJ-001",
                    "objective": "Enable Material",
                    "status": "pending",
                    "priority": 5,
                    "target_date": "N/A",
                    "branch": "FEATURE-enable-material",
                }
            ]
            _create_upgrade_zip(
                env.zip_path,
                {
                    GLOBAL_PROJECT_PATCH: _replace_patch(
                        GLOBAL_PROJECT,
                        "## 4. Pending objectives",
                        "## 4. Pending objectives\n\n"
                        "| ID | Project | Objective | Status | Priority | Target date | Branch | Documentation |\n"
                        "|---|---|---|---|---:|---|---|---|\n"
                        "| OBJ-001 | DP-API | Enable Material | pending | 5 | N/A | FEATURE-enable-material | N/A |\n",
                    ),
                    PROJECT_CONTEXT_PATCH: _replace_patch(
                        PROJECT_CONTEXT,
                        "## 4. Pending objectives",
                        "## 4. Pending objectives\n\n"
                        "| ID | Objective | Status | Priority | Target date | Branch | Documentation |\n"
                        "|---|---|---|---:|---|---|---|\n"
                        "| OBJ-001 | Enable Material | pending | 5 | N/A | `FEATURE-enable-material` | N/A |\n",
                    ),
                },
                lifecycle_phase="planning-activation",
                objectives=objectives,
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "diverges from manifest.objectives for OBJ-001: branch",
            ):
                env.run()

    def test_suite_context_planning_activation_uses_global_context_only(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            objectives = [
                {
                    "objective_id": "OBJ-CTX-002",
                    "objective": "Enable cross-project flows",
                    "status": "pending",
                    "priority": 5,
                    "target_date": "N/A",
                    "branch": "FEATURE-enables-cross-project-flows",
                }
            ]
            _create_upgrade_zip(
                env.zip_path,
                {
                    GLOBAL_PROJECT_PATCH: _replace_patch(
                        GLOBAL_PROJECT,
                        "## 4. Pending objectives",
                        "## 4. Pending objectives\n\n"
                        "| ID | Project | Objective | Status | Priority | Target date | Branch | Documentation |\n"
                        "|---|---|---|---|---:|---|---|---|\n"
                        "| OBJ-CTX-002 | SBM-SUITE | Enable cross-project flows | pending | 5 | N/A | FEATURE-enables-cross-project-flows | N/A |\n",
                    )
                },
                project_name="sbm-suite-context",
                lifecycle_phase="planning-activation",
                objectives=objectives,
            )

            response = upgrade_contexts(
                input_directory=str(env.input_directory),
                suite_context_root=str(env.suite_root),
                project_root=str(env.repository_root),
                backup_root=str(env.backup_root),
                now=lambda: datetime(2026, 7, 30, 10, 11, 12),
            )

            self.assertEqual(response.project_name, "sbm-suite-context")
            self.assertEqual(response.updated_files, [GLOBAL_PROJECT])
            updated = (env.suite_root / "PROJECT_CONTEXT.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("OBJ-CTX-002", updated)
            self.assertIn("| SBM-SUITE |", updated)

    def test_planning_activation_rejects_pending_rows_after_blank_line(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            _seed_suite_pending_objective(env)
            objectives = _suite_planning_objectives()
            _create_upgrade_zip(
                env.zip_path,
                {
                    GLOBAL_PROJECT_PATCH: _replace_patch(
                        GLOBAL_PROJECT,
                        "## 4. Pending objectives",
                        _suite_pending_section(
                            blank_before_objective="OBJ-CTX-011"
                        ),
                    )
                },
                project_name="sbm-suite-context",
                lifecycle_phase="planning-activation",
                objectives=objectives,
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "exactly once in its pending table: OBJ-CTX-011",
            ):
                _run_suite_context_upgrade(env)

    def test_planning_activation_validates_each_pending_objective_in_batch(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            _seed_suite_pending_objective(env)
            objectives = _suite_planning_objectives()
            _create_upgrade_zip(
                env.zip_path,
                {
                    GLOBAL_PROJECT_PATCH: _replace_patch(
                        GLOBAL_PROJECT,
                        "## 4. Pending objectives",
                        _suite_pending_section(
                            blank_before_objective="OBJ-CTX-012"
                        ),
                    )
                },
                project_name="sbm-suite-context",
                lifecycle_phase="planning-activation",
                objectives=objectives,
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "exactly once in its pending table: OBJ-CTX-012",
            ):
                _run_suite_context_upgrade(env)

    def test_planning_activation_accepts_contiguous_pending_rows(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            _seed_suite_pending_objective(env)
            objectives = _suite_planning_objectives()
            _create_upgrade_zip(
                env.zip_path,
                {
                    GLOBAL_PROJECT_PATCH: _replace_patch(
                        GLOBAL_PROJECT,
                        "## 4. Pending objectives",
                        _suite_pending_section(),
                    )
                },
                project_name="sbm-suite-context",
                lifecycle_phase="planning-activation",
                objectives=objectives,
            )

            response = _run_suite_context_upgrade(env)

            self.assertEqual(response.updated_files, [GLOBAL_PROJECT])
            updated = (env.suite_root / "PROJECT_CONTEXT.md").read_text(
                encoding="utf-8"
            )
            for objective in objectives:
                self.assertEqual(updated.count(objective["objective_id"]), 1)

    def test_suite_context_rejects_project_scoped_patch(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(
                env.zip_path,
                {
                    PROJECT_CONTEXT_PATCH: _replace_patch(
                        "SBM-SUITE/context/context/PROJECT_CONTEXT.md",
                        "## 2. Project purpose",
                        "## 2. Project purpose\n\nInvalid suite-local patch.\n",
                    )
                },
                project_name="sbm-suite-context",
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "unauthorized|supported",
            ):
                upgrade_contexts(
                    input_directory=str(env.input_directory),
                    suite_context_root=str(env.suite_root),
                    project_root=str(env.repository_root),
                    backup_root=str(env.backup_root),
                    now=lambda: datetime(2026, 7, 30, 10, 11, 12),
                )

    def test_completed_objective_requires_global_and_project_context_patches(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(
                env.zip_path,
                {
                    COMPLETED_OBJECTIVES_PATCH: _append_patch(
                        COMPLETED_OBJECTIVES,
                        "## 1. Completed objectives by project",
                        "### DP-API\n\nCompleted objective record.",
                    )
                },
                lifecycle_phase="implementation-closure",
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "implementation-closure is missing required patches",
            ):
                env.run()

    def test_missing_completed_project_group_rejects_replace_section(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            _seed_active_objectives(env)
            patches = _closure_patches()
            patches[COMPLETED_OBJECTIVES_PATCH] = _replace_patch(
                COMPLETED_OBJECTIVES,
                "## 1. Completed objectives by project",
                "## 1. Completed objectives by project\n\nInvalid replacement.\n",
            )
            _create_upgrade_zip(
                env.zip_path,
                patches,
                lifecycle_phase="implementation-closure",
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "missing completed-objectives project group requires append_to_section",
            ):
                env.run()

    def test_completed_objective_closure_updates_history_and_operational_contexts(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            _seed_active_objectives(env)
            _create_upgrade_zip(
                env.zip_path,
                _closure_patches(),
                lifecycle_phase="implementation-closure",
            )

            response = env.run()

            self.assertEqual(
                response.updated_files,
                sorted(
                    [
                        GLOBAL_PROJECT,
                        PROJECT_CONTEXT,
                        COMPLETED_OBJECTIVES,
                        GLOBAL_QA,
                        PROJECT_QA,
                    ]
                ),
            )
            history = (env.suite_root / "COMPLETED_OBJECTIVES.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("### DP-API", history)
            self.assertIn("OBJ-001", history)
            self.assertNotIn(
                "No completed objectives have been migrated into this register yet.",
                history,
            )

    def test_existing_completed_project_group_rejects_append(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            _seed_active_objectives(env)
            _seed_completed_project_group(
                env,
                (_completed_row("OLD-001", "Existing objective"),),
            )
            _create_upgrade_zip(
                env.zip_path,
                _closure_patches(),
                lifecycle_phase="implementation-closure",
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "existing completed-objectives project group requires replace_section",
            ):
                env.run()

    def test_existing_completed_project_group_accepts_complete_replace(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            _seed_active_objectives(env)
            existing_row = _completed_row("OLD-001", "Existing objective")
            _seed_completed_project_group(env, (existing_row,))
            patches = _closure_patches()
            patches[COMPLETED_OBJECTIVES_PATCH] = _completed_replace_patch(
                env,
                _completed_row(),
            )
            _create_upgrade_zip(
                env.zip_path,
                patches,
                lifecycle_phase="implementation-closure",
            )

            env.run()

            history = (env.suite_root / "COMPLETED_OBJECTIVES.md").read_text(
                encoding="utf-8"
            )
            self.assertEqual(history.count("### DP-API"), 1)
            self.assertIn("OLD-001", history)
            self.assertIn("OBJ-001", history)

    def test_closure_cannot_remove_another_objective(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            _seed_active_objectives(env, ("OBJ-001", "OBJ-002"))
            _create_upgrade_zip(
                env.zip_path,
                _closure_patches(),
                lifecycle_phase="implementation-closure",
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "objective other than OBJ-001|unrelated table row",
            ):
                env.run()

    def test_global_qa_cannot_remove_another_project(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(
                env.zip_path,
                {
                    GLOBAL_QA_PATCH: _replace_patch(
                        GLOBAL_QA,
                        "## 2. Project QA summaries",
                        "## 2. Project QA summaries\n\n"
                        "| Project | Status | Evidence |\n"
                        "|---|---|---|\n"
                        "| DP-API | passing | current |\n",
                    )
                },
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "unrelated table row",
            ):
                env.run()

    def test_partial_global_qa_table_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(
                env.zip_path,
                {
                    GLOBAL_QA_PATCH: _replace_patch(
                        GLOBAL_QA,
                        "## 2. Project QA summaries",
                        "## 2. Project QA summaries\n\n"
                        "| Project | Status | Evidence |\n"
                        "|---|---|---|\n",
                    )
                },
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "unrelated table row",
            ):
                env.run()

    def test_partial_reusable_components_table_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(
                env.zip_path,
                {
                    PROJECT_README_PATCH: _replace_patch(
                        PROJECT_README,
                        "## Reusable components",
                        "## Reusable components\n\n"
                        "| File name | Path | Description |\n"
                        "|---|---|---|\n"
                        "| existing-service.py | backend/app/services/ | Existing service |\n",
                    )
                },
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "unrelated table row",
            ):
                env.run()

    def test_changed_table_header_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(
                env.zip_path,
                {
                    GLOBAL_QA_PATCH: _replace_patch(
                        GLOBAL_QA,
                        "## 2. Project QA summaries",
                        "## 2. Project QA summaries\n\n"
                        "| Project | Result | Evidence |\n"
                        "|---|---|---|\n"
                        "| SBM-API | passing | existing |\n",
                    )
                },
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "table header differs",
            ):
                env.run()

    def test_duplicate_completed_objective_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            _seed_active_objectives(env)
            _seed_completed_project_group(env, (_completed_row(),))
            patches = _closure_patches()
            patches[COMPLETED_OBJECTIVES_PATCH] = _completed_replace_patch(
                env,
                _completed_row(),
            )
            _create_upgrade_zip(
                env.zip_path,
                patches,
                lifecycle_phase="implementation-closure",
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "duplicated|unique",
            ):
                env.run()

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
                "## 2. Suite purpose",
                "## 2. Suite purpose\n\nUpdated.\n",
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

    def test_absolute_runtime_path_in_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(
                env.zip_path,
                {
                    PROJECT_CONTEXT_PATCH: _replace_patch(
                        PROJECT_CONTEXT,
                        "## 2. Project purpose",
                        "## 2. Project purpose\n\nUpdated.\n",
                    )
                },
                manifest_updates={
                    "canonical_project_path": "/suite/dp/DP-API"
                },
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "canonical_project_path does not match",
            ):
                env.run()

    def test_runtime_path_in_patch_target_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = UpgradeEnvironment(Path(temporary_directory))
            _create_upgrade_zip(
                env.zip_path,
                {
                    PROJECT_CONTEXT_PATCH: _replace_patch(
                        "/suite/dp/DP-API/context/PROJECT_CONTEXT.md",
                        "## 2. Project purpose",
                        "## 2. Project purpose\n\nUpdated.\n",
                    )
                },
            )

            with self.assertRaisesRegex(
                ContextValidationError,
                "target_file must be SBM-SUITE/dp/DP-API",
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
                        "## 2. Suite purpose",
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
                        "## 2. Suite purpose",
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
                "## 2. Suite purpose",
                "## 2. Suite purpose\n\nUpdated.\n",
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
                "## 2. Suite purpose",
                "## 2. Suite purpose\n\nUpdated.\n",
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
            _create_upgrade_zip(
                env.zip_path,
                {
                    GLOBAL_PROJECT_PATCH: _replace_patch(
                        GLOBAL_PROJECT,
                        "## 2. Suite purpose",
                        "## 2. Suite purpose\n\nUpdated.\n",
                    )
                },
            )
            (env.suite_root / "FORMAT_CONTEXT.md").unlink()

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
                        "## 2. Suite purpose",
                        "## 2. Suite purpose\n\nUpdated global.\n",
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
