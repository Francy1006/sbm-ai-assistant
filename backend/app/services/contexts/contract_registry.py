from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath

from app.services.project_registry import (
    PROJECT_ALLOWLIST,
    ProjectRegistryError,
    canonical_runtime_project_path,
    get_project_location,
    is_suite_scoped_project,
    runtime_to_repository_path,
)


LIFECYCLE_PHASES = (
    "planning-activation",
    "objective-activation",
    "implementation-progress",
    "implementation-closure",
)


@dataclass(frozen=True)
class PatchDefinition:
    patch_path: str
    scope: str
    relative_target: str
    target_template: str
    contract_section: str
    allowed_operations: tuple[str, ...]
    lifecycle_phases: tuple[str, ...]


_ALL_PHASES = LIFECYCLE_PHASES
_REPLACE_ONLY = ("replace_section",)


def _patch(
    patch_path: str,
    scope: str,
    relative_target: str,
    target_template: str,
    contract_section: str,
    allowed_operations: tuple[str, ...] = _REPLACE_ONLY,
    lifecycle_phases: tuple[str, ...] = _ALL_PHASES,
) -> PatchDefinition:
    return PatchDefinition(
        patch_path=patch_path,
        scope=scope,
        relative_target=relative_target,
        target_template=target_template,
        contract_section=contract_section,
        allowed_operations=allowed_operations,
        lifecycle_phases=lifecycle_phases,
    )


PATCH_DEFINITIONS = {
    definition.patch_path: definition
    for definition in (
        _patch(
            "patches/global-project-context.json",
            "suite",
            "PROJECT_CONTEXT.md",
            "SBM-SUITE/context/PROJECT_CONTEXT.md",
            "## 2. Global `PROJECT_CONTEXT.md`",
        ),
        _patch(
            "patches/completed-objectives.json",
            "suite",
            "COMPLETED_OBJECTIVES.md",
            "SBM-SUITE/context/COMPLETED_OBJECTIVES.md",
            "## 3. Global `COMPLETED_OBJECTIVES.md`",
            allowed_operations=("append_to_section",),
            lifecycle_phases=("implementation-closure",),
        ),
        _patch(
            "patches/suite-context.json",
            "suite",
            "SUITE_CONTEXT.md",
            "SBM-SUITE/context/SUITE_CONTEXT.md",
            "## 4. Global `SUITE_CONTEXT.md`",
        ),
        _patch(
            "patches/business-context.json",
            "suite",
            "BUSINESS_CONTEXT.md",
            "SBM-SUITE/context/BUSINESS_CONTEXT.md",
            "## 5. Global `BUSINESS_CONTEXT.md`",
        ),
        _patch(
            "patches/global-qa-context.json",
            "suite",
            "QA_CONTEXT.md",
            "SBM-SUITE/context/QA_CONTEXT.md",
            "## 6. Global `QA_CONTEXT.md`",
        ),
        _patch(
            "patches/security-context.json",
            "suite",
            "SECURITY_CONTEXT.md",
            "SBM-SUITE/context/SECURITY_CONTEXT.md",
            "## 7. Global `SECURITY_CONTEXT.md`",
        ),
        _patch(
            "patches/data-context.json",
            "suite",
            "DATA_CONTEXT.md",
            "SBM-SUITE/context/DATA_CONTEXT.md",
            "## 8. Global `DATA_CONTEXT.md`",
        ),
        _patch(
            "patches/decisions-context.json",
            "suite",
            "DECISIONS_CONTEXT.md",
            "SBM-SUITE/context/DECISIONS_CONTEXT.md",
            "## 9. Global `DECISIONS_CONTEXT.md`",
        ),
        _patch(
            "patches/project-context.json",
            "project",
            "context/PROJECT_CONTEXT.md",
            "SBM-SUITE/{brand}/{project}/context/PROJECT_CONTEXT.md",
            "## 11. Project `context/PROJECT_CONTEXT.md`",
        ),
        _patch(
            "patches/project-qa-context.json",
            "project",
            "context/QA_CONTEXT.md",
            "SBM-SUITE/{brand}/{project}/context/QA_CONTEXT.md",
            "## 12. Project `context/QA_CONTEXT.md`",
        ),
        _patch(
            "patches/project-deploy-context.json",
            "project",
            "context/DEPLOY_CONTEXT.md",
            "SBM-SUITE/{brand}/{project}/context/DEPLOY_CONTEXT.md",
            "## 13. Project `context/DEPLOY_CONTEXT.md`",
        ),
        _patch(
            "patches/global-readme.json",
            "suite",
            "README.md",
            "SBM-SUITE/context/README.md",
            "## 14. Project and suite `README.md`",
        ),
        _patch(
            "patches/project-readme.json",
            "project",
            "README.md",
            "SBM-SUITE/{brand}/{project}/README.md",
            "## 14. Project and suite `README.md`",
        ),
    )
}


def supported_patch_paths() -> list[str]:
    return sorted(PATCH_DEFINITIONS)


def patch_is_supported_for_project(
    patch_path: str,
    project_name: str,
) -> bool:
    definition = PATCH_DEFINITIONS[patch_path]
    return not (
        definition.scope == "project"
        and is_suite_scoped_project(project_name)
    )


def supported_patch_paths_for_project(project_name: str) -> list[str]:
    get_project_location(project_name)
    return [
        patch_path
        for patch_path in supported_patch_paths()
        if patch_is_supported_for_project(patch_path, project_name)
    ]


def canonical_projects() -> dict[str, str]:
    return {
        project_name: PROJECT_ALLOWLIST[project_name].repository_root
        for project_name in sorted(PROJECT_ALLOWLIST)
    }


def canonical_project_path(project_name: str) -> str:
    """Return the canonical repository-relative project root."""

    return get_project_location(project_name).repository_root


def patch_target_file(patch_path: str, project_name: str) -> str:
    """Resolve a patch target without mixing runtime and repository paths."""

    definition = PATCH_DEFINITIONS[patch_path]
    if definition.scope == "project":
        if is_suite_scoped_project(project_name):
            raise ProjectRegistryError(
                f"{patch_path} is not supported for suite-scoped project "
                f"{project_name}"
            )
        runtime_target = PurePosixPath(
            canonical_runtime_project_path(project_name),
            definition.relative_target,
        ).as_posix()
    else:
        runtime_target = PurePosixPath(
            "/suite/context",
            definition.relative_target,
        ).as_posix()
    return runtime_to_repository_path(runtime_target)


def _registry_payload() -> dict:
    return {
        "patch_definitions": [
            asdict(PATCH_DEFINITIONS[path])
            for path in supported_patch_paths()
        ],
        "lifecycle_phases": list(LIFECYCLE_PHASES),
        "canonical_projects": canonical_projects(),
        "project_supported_patch_paths": {
            project_name: supported_patch_paths_for_project(project_name)
            for project_name in sorted(PROJECT_ALLOWLIST)
        },
    }


def build_contract_version(format_markdown: str) -> str:
    payload = {
        **_registry_payload(),
        "format_context_sha256": hashlib.sha256(
            format_markdown.encode("utf-8")
        ).hexdigest(),
    }
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def contract_descriptor(format_markdown: str) -> dict:
    return {
        "contract_version": build_contract_version(format_markdown),
        "supported_patch_paths": supported_patch_paths(),
        "lifecycle_phases": list(LIFECYCLE_PHASES),
        "canonical_projects": canonical_projects(),
    }


def _outside_fenced_blocks(markdown: str) -> str:
    return re.sub(r"```.*?```", "", markdown, flags=re.DOTALL)


def validate_format_context(format_markdown: str) -> None:
    visible = _outside_fenced_blocks(format_markdown)
    numbered_sections = [
        (int(number), title.strip())
        for number, title in re.findall(
            r"^##\s+(\d+)\.\s+(.+?)\s*$",
            visible,
            flags=re.MULTILINE,
        )
    ]
    if not numbered_sections:
        raise ValueError("FORMAT_CONTEXT.md has no numbered contract sections")
    numbers = [number for number, _ in numbered_sections]
    if len(numbers) != len(set(numbers)) or numbers != list(
        range(numbers[0], numbers[0] + len(numbers))
    ):
        raise ValueError(
            "FORMAT_CONTEXT.md main sections must be unique and sequential"
        )

    mapped_project_name = None
    for definition in PATCH_DEFINITIONS.values():
        if visible.count(definition.contract_section) != 1:
            raise ValueError(
                "FORMAT_CONTEXT.md must contain exactly one contract section: "
                f"{definition.contract_section}"
            )
        if definition.scope == "project":
            target_mappings = {
                project_name: patch_target_file(
                    definition.patch_path,
                    project_name,
                )
                for project_name in PROJECT_ALLOWLIST
                if patch_is_supported_for_project(
                    definition.patch_path,
                    project_name,
                )
            }
        else:
            target_mappings = {
                "suite": patch_target_file(
                    definition.patch_path,
                    next(iter(PROJECT_ALLOWLIST)),
                )
            }
        matching_projects = [
            project_name
            for project_name, target in target_mappings.items()
            if format_markdown.count(
                f"{definition.patch_path}\n→ {target}"
            ) == 1
        ]
        if len(matching_projects) != 1:
            raise ValueError(
                "FORMAT_CONTEXT.md patch mapping diverges from backend: "
                f"{definition.patch_path}"
            )
        if definition.scope == "project":
            project_name = matching_projects[0]
            if mapped_project_name not in {None, project_name}:
                raise ValueError(
                    "FORMAT_CONTEXT.md project patch mappings must use one "
                    "canonical project"
                )
            mapped_project_name = project_name

    if "README headings are repository-owned." not in format_markdown:
        raise ValueError("FORMAT_CONTEXT.md must declare README repository ownership")
    if re.search(r"\bCurrent objectives\b", format_markdown, flags=re.IGNORECASE):
        raise ValueError("FORMAT_CONTEXT.md contains forbidden Current objectives")
    for obsolete_path in ("/suite/DP-API", "SBM-SUITE/dp-api"):
        if obsolete_path in format_markdown:
            raise ValueError(
                f"FORMAT_CONTEXT.md contains obsolete path: {obsolete_path}"
            )
