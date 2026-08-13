from __future__ import annotations

import json
import os
import re
import shutil
import stat
import tempfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Callable
from zipfile import BadZipFile, ZipFile, ZipInfo

from app.config.settings import (
    CONTEXT_UPGRADE_BACKUP_ROOT,
    CONTEXT_UPGRADE_INPUT_ROOT,
    CONTEXT_UPGRADE_PROJECT_ROOT,
    CONTEXT_UPGRADE_SUITE_CONTEXT_ROOT,
)
from app.services.project_registry import (
    ProjectRegistryError,
    get_project_location,
    is_suite_scoped_project,
    lifecycle_objective_label,
    resolve_allowed_project_root,
)
from app.schemas.contexts import (
    ContextObjective,
    ContextQADecision,
    ContextUpgradeResponse,
)
from app.services.contexts.context_index_service import content_hash
from app.services.contexts.contract_registry import (
    LIFECYCLE_PHASES,
    PATCH_DEFINITIONS,
    build_contract_version,
    canonical_project_path,
    patch_target_file,
    supported_patch_paths_for_project,
    validate_format_context,
)
from app.services.contexts.file_discovery_service import (
    ContextValidationError,
    resolve_existing_directory,
    validate_project_name,
)


UPGRADE_ZIP_NAME = "context-upgrade.zip"
UPGRADE_WORKFLOW = "context-upgrade"
FORMAT_CONTEXT_FILENAME = "FORMAT_CONTEXT.md"
REQUIRED_ROOT_FILES = frozenset(
    {
        "EXECUTIVE_README.md",
        "COMMIT_MESSAGE.md",
        "manifest.json",
    }
)

INFORMATIONAL_FILES = frozenset(
    {
        "EXECUTIVE_README.md",
        "COMMIT_MESSAGE.md",
        "USER_PROMPT.md",
        "manifest.json",
    }
)

PROJECT_SYNC_PATCHES = frozenset(
    {
        "patches/project-context.json",
        "patches/project-readme.json",
    }
)

OBJECTIVE_CONTEXT_PATCHES = frozenset(
    {
        "patches/global-project-context.json",
        "patches/project-context.json",
    }
)
COMPLETED_OBJECTIVES_PATCH = "patches/completed-objectives.json"
ACTIVE_OBJECTIVE_HEADING = "## 3. Active objectives"
PENDING_OBJECTIVE_HEADING = "## 4. Pending objectives"
COMPLETED_OBJECTIVES_HEADING = "## 1. Completed objectives by project"
COMPLETED_OBJECTIVES_TABLE_HEADER = (
    "| Objective ID | Project | Objective | Final status | Priority | Branch | "
    "Started | Completed | Summary | Validation | Documentation | Proposed commit |"
)
COMPLETED_OBJECTIVES_TABLE_SEPARATOR = (
    "|---|---|---|---|---:|---|---|---|---|---|---|---|"
)
COMPLETED_OBJECTIVES_EMPTY_MARKERS = (
    "No completed objectives have been migrated into this register yet.",
)
REUSABLE_CHANGE_MARKERS = (
    "/services/",
    "/scripts/",
    "/models/",
    "/routers/",
    "/schemas/",
    "/utils/",
    "model.py",
    "models.py",
)


def _objective_context_patches(project_name: str) -> frozenset[str]:
    if is_suite_scoped_project(project_name):
        return frozenset({"patches/global-project-context.json"})
    return OBJECTIVE_CONTEXT_PATCHES


def _reusable_sync_patches(project_name: str) -> frozenset[str]:
    if is_suite_scoped_project(project_name):
        return frozenset(
            {
                "patches/global-project-context.json",
                "patches/global-readme.json",
            }
        )
    return PROJECT_SYNC_PATCHES


def _closure_required_patches(project_name: str) -> set[str]:
    required = {
        COMPLETED_OBJECTIVES_PATCH,
        "patches/global-project-context.json",
        "patches/global-qa-context.json",
    }
    if not is_suite_scoped_project(project_name):
        required.update(
            {
                "patches/project-context.json",
                "patches/project-qa-context.json",
            }
        )
    return required


class ContextUpgradeOperationalError(RuntimeError):
    pass


def locate_upgrade_zip(input_directory: Path) -> Path:
    zip_files = sorted(
        path
        for path in input_directory.iterdir()
        if path.is_file() and path.suffix.lower() == ".zip"
    )
    if not zip_files:
        raise ContextValidationError(f"No ZIP file found in {input_directory}")
    if len(zip_files) > 1:
        raise ContextValidationError(
            f"Expected exactly one ZIP file in {input_directory}"
        )
    zip_path = zip_files[0]
    if zip_path.name != UPGRADE_ZIP_NAME:
        raise ContextValidationError(f"ZIP file must be named {UPGRADE_ZIP_NAME}")
    if zip_path.is_symlink():
        raise ContextValidationError("Upgrade ZIP must not be a symlink")
    return zip_path


def _validate_member_name(name: str) -> PurePosixPath:
    if not name or "\\" in name:
        raise ContextValidationError(f"Invalid ZIP member path: {name!r}")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise ContextValidationError(f"Unsafe ZIP member path: {name}")
    return path


def _is_zip_symlink(info: ZipInfo) -> bool:
    file_type = (info.external_attr >> 16) & 0o170000
    return file_type == stat.S_IFLNK


def validate_and_stage_zip(
    zip_path: Path,
    staging_directory: Path,
) -> tuple[dict, set[str]]:
    try:
        with ZipFile(zip_path) as archive:
            members: list[tuple[ZipInfo, PurePosixPath]] = []
            seen_names: set[str] = set()
            for info in archive.infolist():
                member_path = _validate_member_name(info.filename)
                if _is_zip_symlink(info):
                    raise ContextValidationError(
                        f"ZIP symlinks are not allowed: {info.filename}"
                    )
                if info.is_dir():
                    continue
                member_name = member_path.as_posix()
                if member_name in seen_names:
                    raise ContextValidationError(f"Duplicate ZIP member: {member_name}")
                if info.flag_bits & 0x1:
                    raise ContextValidationError(
                        f"Encrypted ZIP members are not allowed: {member_name}"
                    )
                seen_names.add(member_name)
                members.append((info, member_path))

            corrupt_member = archive.testzip()
            if corrupt_member:
                raise ContextValidationError(f"Corrupt ZIP member: {corrupt_member}")
            if "manifest.json" not in seen_names:
                raise ContextValidationError("ZIP must contain manifest.json")

            for info, member_path in members:
                destination = staging_directory.joinpath(*member_path.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, destination.open("xb") as target:
                    shutil.copyfileobj(source, target)
                    target.flush()
                    os.fsync(target.fileno())
    except BadZipFile as exc:
        raise ContextValidationError("Upgrade ZIP is corrupt") from exc
    except RuntimeError as exc:
        raise ContextValidationError("Upgrade ZIP cannot be read safely") from exc
    except OSError as exc:
        raise ContextUpgradeOperationalError("Unable to stage upgrade ZIP") from exc

    try:
        manifest = json.loads(
            (staging_directory / "manifest.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContextValidationError("manifest.json must be valid UTF-8 JSON") from exc
    if not isinstance(manifest, dict):
        raise ContextValidationError("manifest.json must contain a JSON object")
    return manifest, seen_names


def _require_unique_string_list(manifest: dict, field_name: str) -> list[str]:
    value = manifest.get(field_name)
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) or not item for item in value)
        or len(value) != len(set(value))
    ):
        raise ContextValidationError(
            f"manifest.{field_name} must be a unique string list"
        )
    return value


def _read_utf8(path: Path, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ContextValidationError(f"{label} must be a readable UTF-8 file") from exc


def _validate_manifest_objectives(
    manifest: dict,
    lifecycle_phase: str,
) -> list[dict]:
    raw_objectives = manifest.get("objectives")
    if not isinstance(raw_objectives, list) or not raw_objectives:
        raise ContextValidationError(
            f"manifest.objectives must be a non-empty array for {lifecycle_phase}"
        )

    objectives: list[dict] = []
    for index, raw_objective in enumerate(raw_objectives):
        if not isinstance(raw_objective, dict):
            raise ContextValidationError(
                f"manifest.objectives[{index}] must be an object"
            )
        try:
            objective = ContextObjective.model_validate(raw_objective)
        except Exception as exc:
            raise ContextValidationError(
                f"manifest.objectives[{index}] is invalid: {exc}"
            ) from exc
        objectives.append(objective.model_dump())

    objective_ids = [objective["objective_id"] for objective in objectives]
    if len(objective_ids) != len(set(objective_ids)):
        raise ContextValidationError(
            "manifest.objectives contains duplicate objective_id values"
        )

    if lifecycle_phase in {
        "planning-activation",
        "objective-activation",
    }:
        required_fields = (
            "objective",
            "status",
            "priority",
            "target_date",
            "branch",
        )
        for index, objective in enumerate(objectives):
            missing = [
                field for field in required_fields if objective.get(field) is None
            ]
            if missing:
                lifecycle_label = (
                    "planning"
                    if lifecycle_phase == "planning-activation"
                    else "activation"
                )
                raise ContextValidationError(
                    f"manifest.objectives[{index}] is missing "
                    f"{lifecycle_label} fields: "
                    + ", ".join(missing)
                )
    if lifecycle_phase == "objective-activation":
        if len(objectives) != 1:
            raise ContextValidationError(
                "objective-activation requires exactly one objective"
            )
        if objectives[0]["status"] != "active":
            raise ContextValidationError(
                "objective-activation requested status must be active"
            )
    elif lifecycle_phase != "planning-activation" and len(objectives) != 1:
        raise ContextValidationError(
            f"{lifecycle_phase} currently supports exactly one objective"
        )

    return objectives


def validate_upgrade_manifest(
    manifest: dict,
    actual_files: set[str],
    staging_directory: Path,
    project_root: Path,
    format_markdown: str,
) -> tuple[str, list[str], str, list[dict]]:
    project_name_value = manifest.get("project_name")
    if not isinstance(project_name_value, str):
        raise ContextValidationError("manifest.project_name must be a string")
    project_name = validate_project_name(project_name_value)
    try:
        location = get_project_location(project_name)
        project_name = location.project_name
    except ProjectRegistryError as exc:
        raise ContextValidationError(str(exc)) from exc
    if location.directory_name.casefold() != project_root.name.casefold():
        raise ContextValidationError(
            "manifest.project_name does not match configured project"
        )
    if manifest.get("workflow") != UPGRADE_WORKFLOW:
        raise ContextValidationError(f"manifest.workflow must be {UPGRADE_WORKFLOW}")

    allowed_files = _require_unique_string_list(manifest, "allowed_files")
    updated_files = _require_unique_string_list(manifest, "updated_files")
    content_hashes = manifest.get("content_hashes")
    changed_files = manifest.get("changed_files", [])
    manifest_supported_patches = manifest.get("supported_patch_paths")
    lifecycle_phase = manifest.get("lifecycle_phase")
    execution_mode = manifest.get("execution_mode", "evidence")
    user_prompt_file = manifest.get("user_prompt_file")

    expected_contract_version = build_contract_version(format_markdown)
    if manifest.get("contract_version") != expected_contract_version:
        raise ContextValidationError(
            "manifest.contract_version does not match the runtime contract"
        )
    if (
        not isinstance(manifest_supported_patches, list)
        or any(
            not isinstance(path, str) or not path for path in manifest_supported_patches
        )
        or len(manifest_supported_patches) != len(set(manifest_supported_patches))
    ):
        raise ContextValidationError(
            "manifest.supported_patch_paths must be a unique string list"
        )
    applicable_patch_paths = set(
        supported_patch_paths_for_project(project_name)
    )
    unknown_supported = set(manifest_supported_patches) - applicable_patch_paths
    if unknown_supported:
        raise ContextValidationError(
            "manifest.supported_patch_paths contains unknown patches: "
            + ", ".join(sorted(unknown_supported))
        )
    if manifest.get("canonical_project_path") != canonical_project_path(project_name):
        raise ContextValidationError(
            "manifest.canonical_project_path does not match Project Registry"
        )
    if lifecycle_phase is None:
        raise ContextValidationError("manifest.lifecycle_phase is required")
    if lifecycle_phase not in LIFECYCLE_PHASES:
        raise ContextValidationError("manifest.lifecycle_phase is not supported")
    objectives = _validate_manifest_objectives(manifest, lifecycle_phase)

    if execution_mode not in {"evidence", "user-guided"}:
        raise ContextValidationError(
            "manifest.execution_mode must be evidence or user-guided"
        )
    if execution_mode == "evidence":
        if user_prompt_file is not None:
            raise ContextValidationError(
                "manifest.user_prompt_file must be null in evidence mode"
            )
        if "USER_PROMPT.md" in actual_files:
            raise ContextValidationError(
                "USER_PROMPT.md is not allowed in evidence mode"
            )
    else:
        if user_prompt_file != "USER_PROMPT.md":
            raise ContextValidationError(
                "manifest.user_prompt_file must be USER_PROMPT.md in user-guided mode"
            )
        if "USER_PROMPT.md" not in actual_files:
            raise ContextValidationError(
                "USER_PROMPT.md is required in user-guided mode"
            )

    if manifest.get("output_filename") != UPGRADE_ZIP_NAME:
        raise ContextValidationError(
            f"manifest.output_filename must be {UPGRADE_ZIP_NAME}"
        )
    if not isinstance(content_hashes, dict) or any(
        not isinstance(path, str) or not isinstance(digest, str)
        for path, digest in content_hashes.items()
    ):
        raise ContextValidationError("manifest.content_hashes must be a string map")
    if (
        not isinstance(changed_files, list)
        or any(not isinstance(path, str) or not path for path in changed_files)
        or len(changed_files) != len(set(changed_files))
    ):
        raise ContextValidationError(
            "manifest.changed_files must be a unique string list when provided"
        )
    for changed_file in changed_files:
        changed_path = PurePosixPath(changed_file)
        if (
            changed_path.is_absolute()
            or ".." in changed_path.parts
            or "\\" in changed_file
        ):
            raise ContextValidationError(
                "manifest.changed_files must contain safe project-relative paths"
            )

    system_allowlist = applicable_patch_paths | set(INFORMATIONAL_FILES)
    missing_required_files = REQUIRED_ROOT_FILES - actual_files
    if missing_required_files:
        raise ContextValidationError(
            "ZIP is missing required files: "
            + ", ".join(sorted(missing_required_files))
        )

    unauthorized_files = actual_files - system_allowlist
    if unauthorized_files:
        raise ContextValidationError(
            "ZIP contains unauthorized files: " + ", ".join(sorted(unauthorized_files))
        )

    declared_allowlist = set(allowed_files)
    if "manifest.json" not in declared_allowlist:
        raise ContextValidationError(
            "manifest.allowed_files must include manifest.json"
        )

    unauthorized_allowed_files = declared_allowlist - system_allowlist
    if unauthorized_allowed_files:
        raise ContextValidationError(
            "manifest.allowed_files contains unauthorized files: "
            + ", ".join(sorted(unauthorized_allowed_files))
        )

    if actual_files - declared_allowlist:
        raise ContextValidationError(
            "ZIP contains files absent from manifest.allowed_files: "
            + ", ".join(sorted(actual_files - declared_allowlist))
        )

    expected_updated_files = actual_files - {"manifest.json"}
    if "manifest.json" in updated_files:
        raise ContextValidationError(
            "manifest.updated_files must not include manifest.json"
        )
    if "manifest.json" in content_hashes:
        raise ContextValidationError(
            "manifest.content_hashes must not include manifest.json"
        )
    normalized_changed_files = [
        f"/{PurePosixPath(path).as_posix().casefold().strip('/')}"
        for path in changed_files
    ]
    reusable_change = any(
        path.endswith(".sh")
        or any(marker in path for marker in REUSABLE_CHANGE_MARKERS)
        for path in normalized_changed_files
    )
    reusable_sync_patches = _reusable_sync_patches(project_name)
    if reusable_change and not reusable_sync_patches.issubset(actual_files):
        if is_suite_scoped_project(project_name):
            raise ContextValidationError(
                "Reusable or structural suite-context changes require "
                "global-project-context.json and global-readme.json patches"
            )
        raise ContextValidationError(
            "Reusable or structural changes require project-context.json "
            "and project-readme.json patches"
        )
    physical_patch_paths = expected_updated_files & applicable_patch_paths
    undeclared_patches = physical_patch_paths - set(manifest_supported_patches)
    if undeclared_patches:
        raise ContextValidationError(
            "ZIP patch is absent from manifest.supported_patch_paths: "
            + ", ".join(sorted(undeclared_patches))
        )
    phase_forbidden = {
        patch_path
        for patch_path in physical_patch_paths
        if lifecycle_phase not in PATCH_DEFINITIONS[patch_path].lifecycle_phases
    }
    if phase_forbidden:
        raise ContextValidationError(
            f"Patches are not allowed for {lifecycle_phase}: "
            + ", ".join(sorted(phase_forbidden))
        )

    if lifecycle_phase == "planning-activation" and (
        COMPLETED_OBJECTIVES_PATCH in actual_files
    ):
        raise ContextValidationError(
            "planning-activation forbids completed-objectives.json"
        )

    if lifecycle_phase == "implementation-progress" and (
        COMPLETED_OBJECTIVES_PATCH in actual_files
    ):
        raise ContextValidationError(
            "implementation-progress forbids completed-objectives.json"
        )
    if lifecycle_phase == "implementation-closure":
        closure_patches = _closure_required_patches(project_name)
        missing_closure_patches = closure_patches - actual_files
        if missing_closure_patches:
            raise ContextValidationError(
                "implementation-closure is missing required patches: "
                + ", ".join(sorted(missing_closure_patches))
            )
        try:
            qa = ContextQADecision.model_validate(manifest.get("qa"))
        except ValueError as exc:
            raise ContextValidationError(
                "implementation-closure requires structured QA"
            ) from exc
        if qa.status == "failed":
            raise ContextValidationError(
                "implementation-closure is blocked by failed QA"
            )
    if not set(updated_files).issubset(declared_allowlist):
        raise ContextValidationError(
            "manifest.updated_files must be a subset of manifest.allowed_files"
        )
    if (
        lifecycle_phase != "implementation-progress"
        and not (expected_updated_files & applicable_patch_paths)
    ):
        raise ContextValidationError(
            "Upgrade ZIP must contain at least one authorized patch file"
        )
    if set(updated_files) != expected_updated_files:
        raise ContextValidationError(
            "manifest.updated_files must match non-manifest ZIP files"
        )
    if set(content_hashes) != set(updated_files):
        raise ContextValidationError(
            "manifest.content_hashes keys must match manifest.updated_files"
        )

    for archive_path, digest in content_hashes.items():
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ContextValidationError(
                f"manifest.content_hashes contains invalid SHA-256 for {archive_path}"
            )

    for archive_path in sorted(expected_updated_files):
        staged_file = staging_directory.joinpath(*PurePosixPath(archive_path).parts)
        content = _read_utf8(staged_file, archive_path)
        if content_hash(content) != content_hashes[archive_path]:
            raise ContextValidationError(f"SHA-256 mismatch for {archive_path}")

    commit = manifest.get("commit")
    if not isinstance(commit, dict):
        raise ContextValidationError("manifest.commit must be an object")

    commit_type = commit.get("type")
    commit_scope = commit.get("scope")
    commit_subject = commit.get("subject")
    commit_message_file = commit.get("message_file")

    if commit_message_file != "COMMIT_MESSAGE.md":
        raise ContextValidationError(
            "manifest.commit.message_file must be COMMIT_MESSAGE.md"
        )
    if not all(
        isinstance(value, str) and value.strip()
        for value in (commit_type, commit_scope, commit_subject)
    ):
        raise ContextValidationError(
            "manifest.commit type, scope and subject must be non-empty strings"
        )

    allowed_commit_types = {
        "feat",
        "fix",
        "refactor",
        "perf",
        "docs",
        "test",
        "build",
        "ci",
        "chore",
    }
    if commit_type not in allowed_commit_types:
        raise ContextValidationError(f"Unsupported manifest.commit.type: {commit_type}")

    commit_message = _read_utf8(
        staging_directory / "COMMIT_MESSAGE.md",
        "COMMIT_MESSAGE.md",
    )
    first_line = next(
        (line.strip() for line in commit_message.splitlines() if line.strip()),
        "",
    )
    expected_subject = f"{commit_type}({commit_scope}): {commit_subject}"
    if first_line != expected_subject:
        raise ContextValidationError(
            "manifest.commit metadata does not match COMMIT_MESSAGE.md"
        )

    validate_objective_lifecycle_patches(
        staging_directory,
        actual_files,
        lifecycle_phase,
        project_name,
    )

    return project_name, updated_files, lifecycle_phase, objectives


def _extract_contract_headings(
    format_markdown: str,
    contract_section: str,
) -> list[str]:
    section_start = format_markdown.find(contract_section)
    matched_section = contract_section
    if section_start < 0:
        normalized_title = re.sub(r"^##\s+\d+\.\s+", "", contract_section).strip()
        heading_pattern = re.compile(
            rf"^##\s+\d+\.\s+{re.escape(normalized_title)}\s*$",
            flags=re.MULTILINE,
        )
        heading_match = heading_pattern.search(format_markdown)
        if heading_match is None:
            raise ContextValidationError(
                f"FORMAT_CONTEXT.md is missing contract section: {contract_section}"
            )
        section_start = heading_match.start()
        matched_section = heading_match.group(0)

    section_body = format_markdown[section_start + len(matched_section) :]
    section_end = section_body.find("\n---\n")
    if section_end >= 0:
        section_body = section_body[:section_end]

    text_blocks = re.finditer(
        r"```text\s*\n(?P<body>.*?)\n```",
        section_body,
        flags=re.DOTALL,
    )

    for text_block in text_blocks:
        headings = [
            line.strip()
            for line in text_block.group("body").splitlines()
            if re.fullmatch(r"#{1,2}\s+.+", line.strip())
        ]

        if headings:
            if len(headings) != len(set(headings)):
                raise ContextValidationError(
                    "Duplicated required headings in FORMAT_CONTEXT.md: "
                    f"{contract_section}"
                )
            return headings

    raise ContextValidationError(
        f"Invalid required headings in FORMAT_CONTEXT.md: {contract_section}"
    )


def _document_headings(markdown: str) -> list[str]:
    return [
        line.strip()
        for line in markdown.splitlines()
        if re.fullmatch(r"#{1,2}\s+.+", line.strip())
    ]


def _resolve_target(
    scope: str,
    relative_path: str,
    suite_context_root: Path,
    project_root: Path,
) -> Path:
    if scope == "suite":
        root = suite_context_root
    elif scope == "suite_parent":
        root = suite_context_root.parent
    else:
        root = project_root
    target = root / relative_path
    if not target.is_relative_to(root):
        raise ContextValidationError("Patch target escapes configured root")
    current = root
    for part in target.relative_to(root).parts:
        current = current / part
        if current.is_symlink():
            raise ContextValidationError(f"Target symlinks are not allowed: {target}")
    if not target.is_file():
        completed_objectives_target = (
            scope == "suite" and relative_path == "COMPLETED_OBJECTIVES.md"
        )
        if not completed_objectives_target:
            raise ContextValidationError(
                f"Target must be an existing regular file: {target}"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "# COMPLETED_OBJECTIVES.md\n\n"
            "> Last updated\n"
            "> Purpose\n"
            "> Accuracy note\n\n"
            "## 1. Completed objectives by project\n\n"
            "## 2. Document boundary\n",
            encoding="utf-8",
        )
    return target


def _section_bounds(markdown: str, heading: str) -> tuple[int, int]:
    lines = markdown.splitlines(keepends=True)
    start = None
    for index, line in enumerate(lines):
        if line.rstrip("\r\n").strip() == heading:
            start = index
            break
    if start is None:
        raise ContextValidationError(f"Target heading does not exist: {heading}")
    level = len(heading) - len(heading.lstrip("#"))
    end = len(lines)
    for index in range(start + 1, len(lines)):
        candidate = lines[index].rstrip("\r\n").strip()
        match = re.match(r"^(#{1,6})\s+", candidate)
        if match and len(match.group(1)) <= level:
            end = index
            break
    return sum(len(line) for line in lines[:start]), sum(
        len(line) for line in lines[:end]
    )


def _validate_patch_payload(
    patch_path: str,
    payload: object,
    expected_target: str,
    allowed_headings: set[str],
) -> list[dict[str, str]]:
    if not isinstance(payload, dict):
        raise ContextValidationError(f"{patch_path} must contain a JSON object")
    unexpected_keys = set(payload) - {"target_file", "operations"}
    if unexpected_keys:
        raise ContextValidationError(
            f"{patch_path} contains unsupported keys: "
            + ", ".join(sorted(unexpected_keys))
        )
    if payload.get("target_file") != expected_target:
        raise ContextValidationError(
            f"{patch_path}.target_file must be {expected_target}"
        )
    operations = payload.get("operations")
    if not isinstance(operations, list) or not operations:
        raise ContextValidationError(
            f"{patch_path}.operations must be a non-empty array"
        )

    validated: list[dict[str, str]] = []
    seen_headings: set[str] = set()
    for index, operation in enumerate(operations):
        if not isinstance(operation, dict):
            raise ContextValidationError(
                f"{patch_path}.operations[{index}] must be an object"
            )
        unexpected_operation_keys = set(operation) - {
            "operation",
            "heading",
            "content",
        }
        if unexpected_operation_keys:
            raise ContextValidationError(
                f"{patch_path}.operations[{index}] contains unsupported keys: "
                + ", ".join(sorted(unexpected_operation_keys))
            )

        operation_name = operation.get("operation")
        heading = operation.get("heading")
        content = operation.get("content")
        if operation_name not in {"replace_section", "append_to_section"}:
            raise ContextValidationError(
                f"Unsupported operation in {patch_path}: {operation_name}"
            )
        if not isinstance(heading, str) or heading not in allowed_headings:
            raise ContextValidationError(
                f"Unauthorized heading in {patch_path}: {heading}"
            )
        if not isinstance(content, str) or not content.strip():
            raise ContextValidationError(
                f"Empty operation content in {patch_path}: {heading}"
            )
        if heading in seen_headings:
            raise ContextValidationError(
                f"Duplicate target heading in {patch_path}: {heading}"
            )
        seen_headings.add(heading)

        same_or_higher = [
            line.strip()
            for line in content.splitlines()
            if re.fullmatch(r"#{1,2}\s+.+", line.strip())
        ]
        if operation_name == "replace_section":
            first_content_line = next(
                (line.strip() for line in content.splitlines() if line.strip()),
                "",
            )
            if first_content_line != heading:
                raise ContextValidationError(
                    f"replace_section content must begin with exact heading {heading}"
                )
            if same_or_higher != [heading]:
                raise ContextValidationError(
                    f"replace_section contains unexpected headings: {heading}"
                )
        elif same_or_higher:
            raise ContextValidationError(
                f"append_to_section must not contain H1/H2 headings: {heading}"
            )

        validated.append(
            {
                "operation": operation_name,
                "heading": heading,
                "content": content.rstrip() + "\n",
            }
        )
    return validated


def _apply_operations(markdown: str, operations: list[dict[str, str]]) -> str:
    result = markdown
    for operation in operations:
        start, end = _section_bounds(result, operation["heading"])
        if operation["operation"] == "replace_section":
            replacement = operation["content"].rstrip() + "\n\n"
            result = result[:start] + replacement + result[end:]
        else:
            section = result[start:end].rstrip()
            appended = operation["content"].strip()
            replacement = section + "\n\n" + appended + "\n\n"
            result = result[:start] + replacement + result[end:]
    return result.rstrip() + "\n"


def _patch_operation_headings(
    staging_directory: Path,
    patch_path: str,
) -> set[str]:
    try:
        payload = json.loads(
            _read_utf8(
                staging_directory.joinpath(*PurePosixPath(patch_path).parts),
                patch_path,
            )
        )
    except json.JSONDecodeError as exc:
        raise ContextValidationError(f"{patch_path} must contain valid JSON") from exc

    operations = payload.get("operations") if isinstance(payload, dict) else None
    if not isinstance(operations, list):
        return set()
    return {
        operation.get("heading")
        for operation in operations
        if isinstance(operation, dict) and isinstance(operation.get("heading"), str)
    }


def validate_objective_lifecycle_patches(
    staging_directory: Path,
    actual_files: set[str],
    lifecycle_phase: str,
    project_name: str,
):
    objective_patches = _objective_context_patches(project_name)
    completed_present = COMPLETED_OBJECTIVES_PATCH in actual_files

    objective_headings = {ACTIVE_OBJECTIVE_HEADING, PENDING_OBJECTIVE_HEADING}
    objective_context_changed = False
    for patch_path in objective_patches & actual_files:
        headings = _patch_operation_headings(staging_directory, patch_path)
        if headings & objective_headings:
            objective_context_changed = True

    if lifecycle_phase == "objective-activation":
        missing_objective_patches = objective_patches - actual_files
        if missing_objective_patches:
            raise ContextValidationError(
                "objective-activation requires objective context patches: "
                + ", ".join(sorted(missing_objective_patches))
            )
        for patch_path in sorted(objective_patches):
            headings = _patch_operation_headings(staging_directory, patch_path)
            if not objective_headings.issubset(headings):
                raise ContextValidationError(
                    "objective-activation must replace both active and pending "
                    f"objective sections: {patch_path}"
                )

    if objective_context_changed and not objective_patches.issubset(actual_files):
        if is_suite_scoped_project(project_name):
            raise ContextValidationError(
                "Suite context objective changes require "
                "global-project-context.json"
            )
        raise ContextValidationError(
            "Objective context changes require both global-project-context.json "
            "and project-context.json"
        )

    if completed_present:
        if not objective_patches.issubset(actual_files):
            if is_suite_scoped_project(project_name):
                raise ContextValidationError(
                    "Completed suite objective closure requires the global "
                    "PROJECT_CONTEXT patch"
                )
            raise ContextValidationError(
                "Completed objective closure requires global and project "
                "PROJECT_CONTEXT patches"
            )
        completed_headings = _patch_operation_headings(
            staging_directory,
            COMPLETED_OBJECTIVES_PATCH,
        )
        if COMPLETED_OBJECTIVES_HEADING not in completed_headings:
            raise ContextValidationError(
                "completed-objectives.json must target the completed objectives "
                "history section"
            )
        if not objective_context_changed:
            raise ContextValidationError(
                "Completed objective closure must remove the objective from "
                "operational objective sections"
            )

    if lifecycle_phase != "implementation-closure" and completed_present:
        raise ContextValidationError(
            f"{lifecycle_phase} forbids completed-objectives.json"
        )


def _markdown_table_entries(
    markdown: str,
) -> list[tuple[str, str, list[str]]]:
    tables: list[tuple[str, str, list[str]]] = []
    heading = ""
    lines = markdown.splitlines()
    index = 0
    fence_character: str | None = None
    while index < len(lines):
        line = lines[index].strip()
        fence_match = re.match(r"^(`{3,}|~{3,})", line)
        if fence_match:
            marker_character = fence_match.group(1)[0]
            if fence_character is None:
                fence_character = marker_character
            elif marker_character == fence_character:
                fence_character = None
            index += 1
            continue
        if fence_character is not None:
            index += 1
            continue
        if re.fullmatch(r"#{1,3}\s+.+", line):
            heading = line
        if line.startswith("|") and line.endswith("|"):
            if index + 1 >= len(lines) or not re.fullmatch(
                r"\|[\s|:-]+\|",
                lines[index + 1].strip(),
            ):
                raise ContextValidationError(
                    f"Partial or malformed Markdown table in {heading or 'document'}"
                )
            header = line
            header_cells = _table_row_cells(header)
            separator_cells = _table_row_cells(lines[index + 1])
            if len(header_cells) != len(separator_cells) or not all(
                re.fullmatch(r":?-+:?", cell) for cell in separator_cells
            ):
                raise ContextValidationError(
                    f"Partial or malformed Markdown table in {heading or 'document'}"
                )
            rows: list[str] = []
            index += 2
            while (
                index < len(lines)
                and lines[index].strip().startswith("|")
                and lines[index].strip().endswith("|")
            ):
                row = lines[index].strip()
                if len(_table_row_cells(row)) != len(header_cells):
                    raise ContextValidationError(
                        f"Partial or malformed Markdown table in {heading or 'document'}"
                    )
                rows.append(row)
                index += 1
            tables.append((heading, header, rows))
            continue
        index += 1
    return tables


def _markdown_tables(markdown: str) -> dict[str, tuple[str, list[str]]]:
    tables: dict[str, tuple[str, list[str]]] = {}
    for heading, header, rows in _markdown_table_entries(markdown):
        if heading in tables:
            raise ContextValidationError(
                f"Multiple Markdown tables under one heading are ambiguous: {heading}"
            )
        tables[heading] = (header, rows)
    return tables


def _objective_ids(markdown: str) -> list[str]:
    return re.findall(r"(?m)^\|\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*\|", markdown)


def _table_row_cells(row: str) -> list[str]:
    return [cell.strip() for cell in row.strip().strip("|").split("|")]


def _operational_objective_status(markdown: str, objective_id: str) -> str:
    matches: list[str] = []
    tables = _markdown_tables(markdown)
    for heading, expected_status in (
        (ACTIVE_OBJECTIVE_HEADING, "active"),
        (PENDING_OBJECTIVE_HEADING, "pending"),
    ):
        table = tables.get(heading)
        if table is None:
            raise ContextValidationError(
                f"implementation-progress is missing objective table: {heading}"
            )
        header_cells = _table_row_cells(table[0])
        try:
            status_index = header_cells.index("Status")
        except ValueError as exc:
            raise ContextValidationError(
                f"implementation-progress objective table has no Status column: {heading}"
            ) from exc
        for row in table[1]:
            cells = _table_row_cells(row)
            if cells[0] != objective_id:
                continue
            if cells[status_index] != expected_status:
                raise ContextValidationError(
                    "implementation-progress must preserve the operational status "
                    f"{expected_status}: {objective_id}"
                )
            matches.append(expected_status)

    if len(matches) != 1:
        raise ContextValidationError(
            "implementation-progress objective must exist exactly once in "
            f"operational context: {objective_id}"
        )
    return matches[0]


def _planning_objective_row(
    markdown: str,
    objective: dict,
    lifecycle_phase: str = "planning-activation",
) -> list[str]:
    heading = (
        ACTIVE_OBJECTIVE_HEADING
        if objective["status"] == "active"
        else PENDING_OBJECTIVE_HEADING
    )
    table = _markdown_tables(markdown).get(heading)
    if table is None:
        raise ContextValidationError(f"Missing objective table for {heading}")
    matching = [
        _table_row_cells(row)
        for row in table[1]
        if _table_row_cells(row)
        and _table_row_cells(row)[0] == objective["objective_id"]
    ]
    if len(matching) != 1:
        raise ContextValidationError(
            f"{lifecycle_phase} must place each objective exactly once "
            f"in its {objective['status']} table: {objective['objective_id']}"
        )
    return matching[0]


def _validate_planning_objective_fields(
    markdown: str,
    objective: dict,
    *,
    global_context: bool,
    project_directory: str,
    lifecycle_phase: str = "planning-activation",
) -> None:
    cells = _planning_objective_row(
        markdown,
        objective,
        lifecycle_phase,
    )
    expected_length = 8 if global_context else 7
    if len(cells) != expected_length:
        raise ContextValidationError(
            f"{lifecycle_phase} objective row has an invalid column count: "
            f"{objective['objective_id']}"
        )

    if global_context:
        actual = {
            "objective_id": cells[0],
            "project": cells[1],
            "objective": cells[2],
            "status": cells[3],
            "priority": cells[4],
            "target_date": cells[5],
            "branch": cells[6],
        }
        if actual["project"].casefold() != project_directory.casefold():
            raise ContextValidationError(
                f"{lifecycle_phase} project column does not match the selected "
                f"project: {objective['objective_id']}"
            )
    else:
        actual = {
            "objective_id": cells[0],
            "objective": cells[1],
            "status": cells[2],
            "priority": cells[3],
            "target_date": cells[4],
            "branch": cells[5],
        }

    expected = {
        "objective_id": objective["objective_id"],
        "objective": objective["objective"],
        "status": objective["status"],
        "priority": str(objective["priority"]),
        "target_date": objective["target_date"],
        "branch": objective["branch"],
    }
    mismatches = [
        field for field, value in expected.items() if actual.get(field) != value
    ]
    if mismatches:
        raise ContextValidationError(
            f"{lifecycle_phase} objective row diverges from manifest.objectives "
            f"for {objective['objective_id']}: " + ", ".join(mismatches)
        )


def _section_markdown(markdown: str, heading: str) -> str:
    start, end = _section_bounds(markdown, heading)
    return markdown[start:end]


def _markdown_heading_entries(
    markdown: str,
    level: int,
) -> list[tuple[int, str]]:
    entries: list[tuple[int, str]] = []
    offset = 0
    fence_character: str | None = None
    for line in markdown.splitlines(keepends=True):
        stripped = line.strip()
        fence_match = re.match(r"^(`{3,}|~{3,})", stripped)
        if fence_match:
            marker_character = fence_match.group(1)[0]
            if fence_character is None:
                fence_character = marker_character
            elif marker_character == fence_character:
                fence_character = None
            offset += len(line)
            continue
        if fence_character is None and re.fullmatch(
            rf"#{{{level}}}\s+.+",
            stripped,
        ):
            entries.append((offset, stripped))
        offset += len(line)
    return entries


def _markdown_lines_outside_fences(markdown: str) -> list[str]:
    lines: list[str] = []
    fence_character: str | None = None
    for line in markdown.splitlines():
        stripped = line.strip()
        fence_match = re.match(r"^(`{3,}|~{3,})", stripped)
        if fence_match:
            marker_character = fence_match.group(1)[0]
            if fence_character is None:
                fence_character = marker_character
            elif marker_character == fence_character:
                fence_character = None
            continue
        if fence_character is None:
            lines.append(stripped)
    return lines


def _completed_project_headings(markdown: str) -> list[str]:
    section = _section_markdown(markdown, COMPLETED_OBJECTIVES_HEADING)
    return [heading for _, heading in _markdown_heading_entries(section, 3)]


def _completed_project_section(markdown: str, project_heading: str) -> str:
    section = _section_markdown(markdown, COMPLETED_OBJECTIVES_HEADING)
    entries = _markdown_heading_entries(section, 3)
    matching_indexes = [
        index
        for index, (_, heading) in enumerate(entries)
        if heading == project_heading
    ]
    if len(matching_indexes) != 1:
        raise ContextValidationError(
            f"Completed objectives must contain exactly one {project_heading} heading"
        )
    entry_index = matching_indexes[0]
    start = entries[entry_index][0]
    end = (
        entries[entry_index + 1][0] if entry_index + 1 < len(entries) else len(section)
    )
    return section[start:end]


def _contains_completed_objectives_table(markdown: str) -> bool:
    lines = _markdown_lines_outside_fences(markdown)
    for index, line in enumerate(lines[:-1]):
        if (
            line == COMPLETED_OBJECTIVES_TABLE_HEADER
            and lines[index + 1] == COMPLETED_OBJECTIVES_TABLE_SEPARATOR
        ):
            return True
    return False


def _strip_completed_empty_markers(markdown: str) -> str:
    result = markdown
    for marker in COMPLETED_OBJECTIVES_EMPTY_MARKERS:
        result = re.sub(
            rf"(?m)^[ \t]*{re.escape(marker)}[ \t]*\r?\n(?:[ \t]*\r?\n)?",
            "",
            result,
            count=1,
        )
    return result


def _prepare_completed_objectives_operation(
    current_markdown: str,
    operations: list[dict[str, str]],
    project_directory: str,
) -> str:
    if len(operations) != 1:
        raise ContextValidationError(
            "completed-objectives.json must contain exactly one operation"
        )

    operation = operations[0]
    if operation["heading"] != COMPLETED_OBJECTIVES_HEADING:
        raise ContextValidationError(
            "completed-objectives.json must target the completed objectives "
            "history section"
        )

    project_heading = f"### {project_directory}"
    current_headings = _completed_project_headings(current_markdown)
    if len(current_headings) != len(set(current_headings)):
        raise ContextValidationError(
            "COMPLETED_OBJECTIVES.md contains duplicate project headings"
        )

    project_heading_count = current_headings.count(project_heading)
    if project_heading_count > 1:
        raise ContextValidationError(
            f"COMPLETED_OBJECTIVES.md contains duplicate {project_heading} headings"
        )

    if project_heading_count == 0:
        if operation["operation"] != "append_to_section":
            raise ContextValidationError(
                "A missing completed-objectives project group requires "
                "append_to_section"
            )
        appended_headings = [
            heading for _, heading in _markdown_heading_entries(operation["content"], 3)
        ]
        if appended_headings != [project_heading]:
            raise ContextValidationError(
                "The first completed-objectives entry must append exactly one "
                f"{project_heading} heading"
            )
        if not _contains_completed_objectives_table(operation["content"]):
            raise ContextValidationError(
                "The first completed-objectives project group must include the "
                "required table"
            )
        return _strip_completed_empty_markers(current_markdown)

    if operation["operation"] != "replace_section":
        raise ContextValidationError(
            "An existing completed-objectives project group requires replace_section"
        )

    replacement_headings = _completed_project_headings(operation["content"])
    if replacement_headings != current_headings:
        raise ContextValidationError(
            "A completed-objectives replacement must preserve every existing "
            "project heading in order"
        )
    return current_markdown


def _validate_preserved_tables(
    original: str,
    patched: str,
    archive_target: str,
    project_name: str,
    project_directory: str,
    objective_ids: list[str],
) -> None:
    original_tables = _markdown_table_entries(original)
    patched_tables = _markdown_table_entries(patched)
    patched_by_heading: dict[str, list[tuple[str, list[str]]]] = {}
    for heading, header, rows in patched_tables:
        patched_by_heading.setdefault(heading, []).append((header, rows))

    original_occurrences: dict[str, int] = {}
    for heading, header, rows in original_tables:
        occurrence = original_occurrences.get(heading, 0)
        original_occurrences[heading] = occurrence + 1
        candidates = patched_by_heading.get(heading, [])
        if occurrence >= len(candidates):
            raise ContextValidationError(
                f"Patched document removes a required table: {archive_target} {heading}"
            )
        patched_header, patched_rows = candidates[occurrence]
        if patched_header != header:
            raise ContextValidationError(
                f"Patched table header differs from the original: {archive_target} {heading}"
            )
        for row in rows:
            requested_objective_row = any(
                objective_id in row for objective_id in objective_ids
            )
            summary_table_headers = {
                "| Project | Purpose | Active objective | Pending objectives | "
                "Branch | Main context | QA context | Documentation |",
                "| Project | QA context | Test count | Passed | Failed | Coverage | "
                "SonarQube status | Last execution | Overall risk | Evidence |",
            }
            current_project_summary = (
                archive_target in {
                    "SBM-SUITE/context/PROJECT_CONTEXT.md",
                    "SBM-SUITE/context/QA_CONTEXT.md",
                }
                and header in summary_table_headers
                and any(
                    marker.casefold() in row.casefold()
                    for marker in (project_name, project_directory)
                )
            )
            if not requested_objective_row and not current_project_summary:
                if row not in patched_rows:
                    raise ContextValidationError(
                        "Patch removes or changes an unrelated table row: "
                        f"{archive_target} {heading}"
                    )

    reusable_heading = "## Reusable components"
    reusable_tables = [
        (header, rows)
        for heading, header, rows in original_tables
        if heading == reusable_heading
    ]
    if reusable_tables:
        expected_header = "| File name | Path | Description |"
        if any(header != expected_header for header, _ in reusable_tables):
            raise ContextValidationError(
                "Reusable components table has an invalid header"
            )


def _validate_complete_replacement_sections(
    original: str,
    patched: str,
    operations: list[dict[str, str]],
    archive_target: str,
) -> None:
    for operation in operations:
        if operation["operation"] != "replace_section":
            continue
        heading = operation["heading"]
        original_section = _section_markdown(original, heading)
        patched_section = _section_markdown(patched, heading)
        original_nested = [
            entry
            for _, entry in sorted(
                entry
                for level in range(3, 7)
                for entry in _markdown_heading_entries(original_section, level)
            )
        ]
        patched_nested = [
            entry
            for _, entry in sorted(
                entry
                for level in range(3, 7)
                for entry in _markdown_heading_entries(patched_section, level)
            )
        ]
        cursor = 0
        for nested_heading in patched_nested:
            if cursor < len(original_nested) and nested_heading == original_nested[cursor]:
                cursor += 1
        if cursor != len(original_nested):
            raise ContextValidationError(
                "replace_section must preserve the complete section structure: "
                f"{archive_target} {heading}"
            )


def _validate_objective_transition(
    originals: dict[str, str],
    staged: dict[str, str],
    lifecycle_phase: str,
    objectives: list[dict],
    project_directory: str,
    completed_markdown: str,
) -> None:
    objective_ids = [objective["objective_id"] for objective in objectives]
    context_targets = {
        target
        for target in staged
        if target == "SBM-SUITE/context/PROJECT_CONTEXT.md"
        or target.endswith("/context/PROJECT_CONTEXT.md")
    }

    completed_ids = _objective_ids(completed_markdown)

    if lifecycle_phase == "implementation-closure":
        objective_id = objective_ids[0]
        for target in context_targets:
            active_before = _objective_ids(
                _section_markdown(originals[target], ACTIVE_OBJECTIVE_HEADING)
            )
            if objective_id not in active_before:
                raise ContextValidationError(
                    f"Objective {objective_id} must exist as active before closure"
                )
            if objective_id in _objective_ids(staged[target]):
                raise ContextValidationError(
                    f"Objective {objective_id} was not removed during closure"
                )
            other_before = [
                value
                for value in _objective_ids(originals[target])
                if value != objective_id
            ]
            other_after = [
                value
                for value in _objective_ids(staged[target])
                if value != objective_id
            ]
            if other_before != other_after:
                raise ContextValidationError(
                    "Closure removes or changes an objective other than "
                    f"{objective_id}"
                )

        completed_target = "SBM-SUITE/context/COMPLETED_OBJECTIVES.md"
        original_completed = originals[completed_target]
        staged_completed = staged[completed_target]
        original_ids = _objective_ids(original_completed)
        staged_ids = _objective_ids(staged_completed)
        if len(original_ids) != len(set(original_ids)):
            raise ContextValidationError("Completed objective IDs must be unique")
        if objective_id in original_ids:
            raise ContextValidationError(
                f"Completed objective ID is duplicated: {objective_id}"
            )
        if staged_ids.count(objective_id) != 1:
            raise ContextValidationError(
                "Closure must append exactly one completed objective entry"
            )
        if [value for value in staged_ids if value != objective_id] != original_ids:
            raise ContextValidationError(
                "Closure modifies unrelated completed objective history"
            )
        project_heading = f"### {project_directory}"
        original_headings = _completed_project_headings(original_completed)
        staged_headings = _completed_project_headings(staged_completed)
        if len(original_headings) != len(set(original_headings)):
            raise ContextValidationError(
                "COMPLETED_OBJECTIVES.md contains duplicate project headings"
            )
        if len(staged_headings) != len(set(staged_headings)):
            raise ContextValidationError(
                "Closure must not create duplicate project headings"
            )

        original_project_count = original_headings.count(project_heading)
        if original_project_count > 1:
            raise ContextValidationError(
                f"COMPLETED_OBJECTIVES.md contains duplicate {project_heading} headings"
            )
        if original_project_count == 0:
            if staged_headings != [*original_headings, project_heading]:
                raise ContextValidationError(
                    "Closure must append exactly one new project heading and preserve "
                    "all existing project groups"
                )
        elif staged_headings != original_headings:
            raise ContextValidationError(
                "Closure must preserve every existing project heading in order"
            )

        project_section = _completed_project_section(
            staged_completed,
            project_heading,
        )
        if not _contains_completed_objectives_table(project_section):
            raise ContextValidationError(
                "Completed objective project group has an invalid table"
            )
        if _objective_ids(project_section).count(objective_id) != 1:
            raise ContextValidationError(
                "The completed objective must be recorded under its project heading"
            )
    elif lifecycle_phase == "implementation-progress":
        objective_id = objective_ids[0]
        for target in context_targets:
            status_before = _operational_objective_status(
                originals[target],
                objective_id,
            )
            status_after = _operational_objective_status(
                staged[target],
                objective_id,
            )
            if status_after != status_before:
                raise ContextValidationError(
                    "implementation-progress must preserve objective status: "
                    f"{objective_id}"
                )
    elif lifecycle_phase == "objective-activation" and context_targets:
        objective = objectives[0]
        objective_id = objective["objective_id"]
        if objective_id in completed_ids:
            raise ContextValidationError(
                f"objective-activation cannot activate completed objective: "
                f"{objective_id}"
            )

        for target in context_targets:
            active_before = _objective_ids(
                _section_markdown(originals[target], ACTIVE_OBJECTIVE_HEADING)
            )
            pending_before = _objective_ids(
                _section_markdown(originals[target], PENDING_OBJECTIVE_HEADING)
            )
            if active_before.count(objective_id) != 0:
                raise ContextValidationError(
                    "objective-activation requires a pending objective, but it is "
                    f"already active: {objective_id}"
                )
            if pending_before.count(objective_id) != 1:
                raise ContextValidationError(
                    "objective-activation pending objective must exist exactly once: "
                    f"{objective_id}"
                )

            pending_objective = {**objective, "status": "pending"}
            global_context = target == "SBM-SUITE/context/PROJECT_CONTEXT.md"
            _validate_planning_objective_fields(
                originals[target],
                pending_objective,
                global_context=global_context,
                project_directory=project_directory,
                lifecycle_phase=lifecycle_phase,
            )
            _validate_planning_objective_fields(
                staged[target],
                objective,
                global_context=global_context,
                project_directory=project_directory,
                lifecycle_phase=lifecycle_phase,
            )
            pending_cells = _planning_objective_row(
                originals[target],
                pending_objective,
                lifecycle_phase,
            )
            active_cells = _planning_objective_row(
                staged[target],
                objective,
                lifecycle_phase,
            )
            status_index = 3 if global_context else 2
            expected_active_cells = list(pending_cells)
            expected_active_cells[status_index] = "active"
            if active_cells != expected_active_cells:
                raise ContextValidationError(
                    "objective-activation may change only the status cell: "
                    f"{objective_id}"
                )

            active_after = _objective_ids(
                _section_markdown(staged[target], ACTIVE_OBJECTIVE_HEADING)
            )
            pending_after = _objective_ids(
                _section_markdown(staged[target], PENDING_OBJECTIVE_HEADING)
            )
            if active_after.count(objective_id) != 1:
                raise ContextValidationError(
                    "objective-activation must place the objective exactly once in "
                    f"the active table: {objective_id}"
                )
            if objective_id in pending_after:
                raise ContextValidationError(
                    "objective-activation must remove the objective from the pending "
                    f"table: {objective_id}"
                )

            unrelated_before = [
                value
                for value in _objective_ids(originals[target])
                if value != objective_id
            ]
            unrelated_after = [
                value
                for value in _objective_ids(staged[target])
                if value != objective_id
            ]
            if unrelated_after != unrelated_before:
                raise ContextValidationError(
                    "objective-activation must preserve every unrelated objective"
                )
    elif lifecycle_phase == "planning-activation" and context_targets:
        requested = set(objective_ids)
        completed_duplicates = requested & set(completed_ids)
        if completed_duplicates:
            raise ContextValidationError(
                "planning-activation cannot reuse completed objective IDs: "
                + ", ".join(sorted(completed_duplicates))
            )
        for target in context_targets:
            original_ids = _objective_ids(originals[target])
            staged_ids = _objective_ids(staged[target])

            duplicates = requested & set(original_ids)
            if duplicates:
                raise ContextValidationError(
                    "planning-activation cannot reuse existing objective IDs: "
                    + ", ".join(sorted(duplicates))
                )

            for objective_id in objective_ids:
                if staged_ids.count(objective_id) != 1:
                    raise ContextValidationError(
                        "planning-activation must add each requested objective "
                        f"exactly once: {objective_id}"
                    )

            global_context = target == "SBM-SUITE/context/PROJECT_CONTEXT.md"
            for objective in objectives:
                _validate_planning_objective_fields(
                    staged[target],
                    objective,
                    global_context=global_context,
                    project_directory=project_directory,
                )

            unrelated_after = [value for value in staged_ids if value not in requested]
            if unrelated_after != original_ids:
                raise ContextValidationError(
                    "planning-activation must preserve every unrelated objective"
                )


def _validate_staged_preservation(
    replacements: dict[str, tuple[Path, str]],
    project_name: str,
    project_directory: str,
    lifecycle_phase: str,
    objectives: list[dict],
    completed_markdown: str,
) -> None:
    originals = {
        target: _read_utf8(path, target) for target, (path, _) in replacements.items()
    }
    staged = {target: content for target, (_, content) in replacements.items()}
    for target, original in originals.items():
        _validate_preserved_tables(
            original,
            staged[target],
            target,
            project_name,
            project_directory,
            [objective["objective_id"] for objective in objectives],
        )
    _validate_objective_transition(
        originals,
        staged,
        lifecycle_phase,
        objectives,
        project_directory,
        completed_markdown,
    )


def _validate_noop_progress_objective(
    project_name: str,
    suite_context_root: Path,
    project_root: Path,
    objectives: list[dict],
) -> None:
    objective_id = objectives[0]["objective_id"]
    operational_targets = [suite_context_root / "PROJECT_CONTEXT.md"]
    if not is_suite_scoped_project(project_name):
        operational_targets.append(project_root / "context/PROJECT_CONTEXT.md")

    completed_markdown = _read_utf8(
        suite_context_root / "COMPLETED_OBJECTIVES.md",
        "SBM-SUITE/context/COMPLETED_OBJECTIVES.md",
    )
    if objective_id in _objective_ids(completed_markdown):
        raise ContextValidationError(
            f"implementation-progress cannot target completed objective: {objective_id}"
        )

    operational_statuses: list[str] = []
    for target in operational_targets:
        markdown = _read_utf8(target, target.as_posix())
        operational_statuses.append(
            _operational_objective_status(markdown, objective_id)
        )

    if len(set(operational_statuses)) != 1:
        raise ContextValidationError(
            "implementation-progress objective status differs between operational "
            f"contexts: {objective_id}"
        )


def validate_and_build_replacements(
    staging_directory: Path,
    updated_files: list[str],
    project_name: str,
    suite_context_root: Path,
    project_root: Path,
    lifecycle_phase: str,
    objectives: list[dict],
) -> dict[str, tuple[Path, str]]:
    format_path = suite_context_root / FORMAT_CONTEXT_FILENAME
    if format_path.is_symlink() or not format_path.is_file():
        raise ContextValidationError(f"Missing required format contract: {format_path}")
    format_markdown = _read_utf8(format_path, "FORMAT_CONTEXT.md")
    project_label = lifecycle_objective_label(project_name)
    replacements: dict[str, tuple[Path, str]] = {}
    target_headings_seen: set[tuple[str, str]] = set()

    for patch_path in updated_files:
        if patch_path not in PATCH_DEFINITIONS:
            continue
        definition = PATCH_DEFINITIONS[patch_path]
        expected_target = patch_target_file(patch_path, project_name)
        target = _resolve_target(
            definition.scope,
            definition.relative_target,
            suite_context_root,
            project_root,
        )
        current_markdown = replacements.get(
            expected_target,
            (target, _read_utf8(target, expected_target)),
        )[1]
        if patch_path in {
            "patches/global-readme.json",
            "patches/project-readme.json",
        }:
            allowed_headings = _document_headings(current_markdown)
            if patch_path == "patches/project-readme.json" and (
                "## Reusable components" not in allowed_headings
            ):
                raise ContextValidationError(
                    "Project README must contain ## Reusable components"
                )
        else:
            allowed_headings = _extract_contract_headings(
                format_markdown,
                definition.contract_section,
            )
        try:
            payload = json.loads(
                _read_utf8(
                    staging_directory.joinpath(*PurePosixPath(patch_path).parts),
                    patch_path,
                )
            )
        except json.JSONDecodeError as exc:
            raise ContextValidationError(
                f"{patch_path} must contain valid JSON"
            ) from exc

        operations = _validate_patch_payload(
            patch_path,
            payload,
            expected_target,
            set(allowed_headings),
        )
        if patch_path == COMPLETED_OBJECTIVES_PATCH:
            current_markdown = _prepare_completed_objectives_operation(
                current_markdown,
                operations,
                project_label,
            )
        elif any(
            operation["operation"] not in definition.allowed_operations
            for operation in operations
        ):
            raise ContextValidationError(
                f"{patch_path} contains an operation forbidden by PATCH_DEFINITIONS"
            )
        for operation in operations:
            key = (expected_target, operation["heading"])
            if key in target_headings_seen:
                raise ContextValidationError(
                    f"Duplicate target heading across patches: {expected_target} {operation['heading']}"
                )
            target_headings_seen.add(key)

        patched_markdown = _apply_operations(current_markdown, operations)
        _validate_complete_replacement_sections(
            current_markdown,
            patched_markdown,
            operations,
            expected_target,
        )
        actual_headings = _document_headings(patched_markdown)
        if actual_headings != allowed_headings:
            raise ContextValidationError(
                f"Patched document violates FORMAT_CONTEXT.md: {expected_target}"
            )
        replacements[expected_target] = (target, patched_markdown)

    if not replacements:
        if lifecycle_phase != "implementation-progress":
            raise ContextValidationError("No valid context replacements were generated")
        _validate_noop_progress_objective(
            project_name,
            suite_context_root,
            project_root,
            objectives,
        )
        return {}
    _validate_staged_preservation(
        replacements,
        project_name,
        project_label,
        lifecycle_phase,
        objectives,
        _read_utf8(
            suite_context_root / "COMPLETED_OBJECTIVES.md",
            "SBM-SUITE/context/COMPLETED_OBJECTIVES.md",
        ),
    )
    return replacements


def _copy_file(source: Path, destination: Path):
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def create_upgrade_backup(
    staging_directory: Path,
    updated_files: list[str],
    replacements: dict[str, tuple[Path, str]],
    backup_root: Path,
    project_name: str,
    timestamp: str,
    generated_at: str,
    motivo: str,
) -> Path:
    backup_directory = backup_root / f"{timestamp}_{project_name}"
    try:
        backup_directory.mkdir(parents=True, exist_ok=False)
        (backup_directory / "previous").mkdir()
        (backup_directory / "applied").mkdir()
        (backup_directory / "patches").mkdir()

        for info_name in INFORMATIONAL_FILES:
            staged_info = staging_directory / info_name
            if staged_info.is_file():
                _copy_file(staged_info, backup_directory / info_name)

        for patch_path in updated_files:
            if patch_path in PATCH_DEFINITIONS:
                staged_patch = staging_directory.joinpath(
                    *PurePosixPath(patch_path).parts
                )
                _copy_file(
                    staged_patch,
                    backup_directory / PurePosixPath(patch_path),
                )

        backed_up_files = []
        sha256_by_file = {}
        for archive_target in sorted(replacements):
            target, patched_content = replacements[archive_target]
            previous_path = (
                backup_directory / "previous" / PurePosixPath(archive_target)
            )
            _copy_file(
                target,
                previous_path,
            )
            original_hash = content_hash(_read_utf8(target, archive_target))
            sha256_by_file[archive_target] = original_hash
            backed_up_files.append(
                {
                    "original_path": archive_target,
                    "backup_path": (
                        PurePosixPath("previous") / PurePosixPath(archive_target)
                    ).as_posix(),
                    "sha256": original_hash,
                }
            )
            applied_path = backup_directory / "applied" / PurePosixPath(archive_target)
            applied_path.parent.mkdir(parents=True, exist_ok=True)
            applied_path.write_text(patched_content, encoding="utf-8")

        backup_manifest = {
            "project_name": project_name,
            "workflow": UPGRADE_WORKFLOW,
            "generated_at": generated_at,
            "motivo": motivo,
            "backed_up_files": backed_up_files,
        }
        (backup_directory / "BACKUP_MANIFEST.json").write_text(
            json.dumps(backup_manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except (OSError, shutil.Error) as exc:
        raise ContextUpgradeOperationalError(
            "Unable to create context upgrade backup"
        ) from exc
    return backup_directory


def _fsync_directory(directory: Path):
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write_text(content: str, target: Path):
    temporary_path: Path | None = None
    try:
        target_mode = stat.S_IMODE(target.stat().st_mode)
        with tempfile.NamedTemporaryFile(
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".upgrade",
            delete=False,
            mode="w",
            encoding="utf-8",
            newline="",
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.chmod(temporary_path, target_mode)
        os.replace(temporary_path, target)
        _fsync_directory(target.parent)
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()


def rollback_replacements(
    replaced_targets: list[str],
    replacements: dict[str, tuple[Path, str]],
    backup_directory: Path,
):
    errors: list[str] = []
    for archive_target in reversed(replaced_targets):
        target = replacements[archive_target][0]
        previous = backup_directory / "previous" / PurePosixPath(archive_target)
        try:
            _atomic_write_text(_read_utf8(previous, archive_target), target)
        except Exception as exc:  # pragma: no cover - emergency path
            errors.append(f"{archive_target}: {type(exc).__name__}")
    if errors:
        raise ContextUpgradeOperationalError(
            "Context upgrade failed and rollback was incomplete: " + ", ".join(errors)
        )


def apply_replacements(
    replacements: dict[str, tuple[Path, str]],
    backup_directory: Path,
):
    replaced_targets: list[str] = []
    try:
        for archive_target, (target, patched_content) in replacements.items():
            replaced_targets.append(archive_target)
            _atomic_write_text(patched_content, target)
    except Exception as exc:
        rollback_replacements(replaced_targets, replacements, backup_directory)
        raise ContextUpgradeOperationalError(
            "Context upgrade failed; replaced files were rolled back"
        ) from exc


def cleanup_upgrade_input(zip_path: Path):
    try:
        zip_path.unlink()
    except OSError as exc:
        raise ContextUpgradeOperationalError(
            "Upgrade applied but input ZIP could not be removed"
        ) from exc


def upgrade_contexts(
    input_directory: str = CONTEXT_UPGRADE_INPUT_ROOT,
    suite_context_root: str = CONTEXT_UPGRADE_SUITE_CONTEXT_ROOT,
    project_root: str = CONTEXT_UPGRADE_PROJECT_ROOT,
    backup_root: str = CONTEXT_UPGRADE_BACKUP_ROOT,
    now: Callable[[], datetime] = datetime.now,
) -> ContextUpgradeResponse:
    input_path = resolve_existing_directory(
        input_directory,
        "context_upgrade_input_directory",
    )
    suite_root = resolve_existing_directory(
        suite_context_root,
        "context_upgrade_suite_context_root",
    )
    if input_path != (suite_root / "input").resolve():
        raise ContextValidationError(
            "context upgrade input must be suite_context_root/input"
        )
    backup_path = Path(backup_root).expanduser()
    if not backup_path.is_absolute() or ".." in backup_path.parts:
        raise ContextValidationError(
            "context_upgrade_backup_root must be an absolute safe path"
        )
    try:
        backup_path.mkdir(parents=True, exist_ok=True)
        backup_path = backup_path.resolve(strict=True)
    except OSError as exc:
        raise ContextUpgradeOperationalError(
            "Unable to create context upgrade backup root"
        ) from exc
    if backup_path != (suite_root / "backup").resolve():
        raise ContextValidationError(
            "context upgrade backup must be suite_context_root/backup"
        )

    zip_path = locate_upgrade_zip(input_path)
    with tempfile.TemporaryDirectory(prefix="context-upgrade-") as temporary:
        staging_directory = Path(temporary)
        if staging_directory.is_relative_to(input_path):
            raise ContextUpgradeOperationalError(
                "Staging directory must be outside input"
            )
        manifest, actual_files = validate_and_stage_zip(
            zip_path,
            staging_directory,
        )
        manifest_project_name = manifest.get("project_name")
        if not isinstance(manifest_project_name, str):
            raise ContextValidationError("manifest.project_name must be a string")
        try:
            _, resolved_project_root = resolve_allowed_project_root(
                manifest_project_name,
                Path(project_root),
            )
        except ProjectRegistryError as exc:
            raise ContextValidationError(str(exc)) from exc
        format_path = suite_root / FORMAT_CONTEXT_FILENAME
        if format_path.is_symlink() or not format_path.is_file():
            raise ContextValidationError(
                f"Missing required format contract: {format_path}"
            )
        format_markdown = _read_utf8(
            format_path,
            FORMAT_CONTEXT_FILENAME,
        )
        try:
            validate_format_context(format_markdown)
        except ValueError as exc:
            raise ContextValidationError(str(exc)) from exc
        (
            project_name,
            updated_files,
            lifecycle_phase,
            objectives,
        ) = validate_upgrade_manifest(
            manifest,
            actual_files,
            staging_directory,
            resolved_project_root,
            format_markdown,
        )
        replacements = validate_and_build_replacements(
            staging_directory,
            updated_files,
            project_name,
            suite_root,
            resolved_project_root,
            lifecycle_phase,
            objectives,
        )
        generated_at = now()
        timestamp = generated_at.strftime("%Y%m%d_%H%M%S_%f")
        backup_directory: Path | None = None
        if replacements:
            backup_directory = create_upgrade_backup(
                staging_directory,
                updated_files,
                replacements,
                backup_path,
                project_name,
                timestamp,
                generated_at.isoformat(),
                f"Apply validated context lifecycle and section patches for {project_name}",
            )
            apply_replacements(replacements, backup_directory)
        cleanup_upgrade_input(zip_path)

    suite_parent = suite_root.parent

    def relative_output_path(path: Path) -> str:
        return path.relative_to(suite_parent).as_posix()

    return ContextUpgradeResponse(
        project_name=project_name,
        workflow=UPGRADE_WORKFLOW,
        updated_files=sorted(replacements),
        backup_directory=(
            relative_output_path(backup_directory) if backup_directory else ""
        ),
        commit_message_file=(
            relative_output_path(backup_directory / "COMMIT_MESSAGE.md")
            if backup_directory
            and (backup_directory / "COMMIT_MESSAGE.md").is_file()
            else ""
        ),
        executive_readme_file=(
            relative_output_path(backup_directory / "EXECUTIVE_README.md")
            if backup_directory
            and (backup_directory / "EXECUTIVE_README.md").is_file()
            else ""
        ),
        input_cleaned=not zip_path.exists(),
        errors=[],
    )
