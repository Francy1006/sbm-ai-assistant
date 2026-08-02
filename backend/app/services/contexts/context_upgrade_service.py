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
    CONTEXT_UPGRADE_INPUT_DIRECTORY,
    CONTEXT_UPGRADE_PROJECT_ROOT,
    CONTEXT_UPGRADE_SUITE_CONTEXT_ROOT,
)
from app.schemas.contexts import ContextUpgradeResponse
from app.services.contexts.context_index_service import content_hash
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

PATCH_DEFINITIONS = {
    "patches/global-project-context.json": (
        "SBM-SUITE/context/PROJECT_CONTEXT.md",
        "suite",
        "PROJECT_CONTEXT.md",
        "## 2. Global `PROJECT_CONTEXT.md`",
    ),
    "patches/suite-context.json": (
        "SBM-SUITE/context/SUITE_CONTEXT.md",
        "suite",
        "SUITE_CONTEXT.md",
        "## 3. Global `SUITE_CONTEXT.md`",
    ),
    "patches/business-context.json": (
        "SBM-SUITE/context/BUSINESS_CONTEXT.md",
        "suite",
        "BUSINESS_CONTEXT.md",
        "## 4. Global `BUSINESS_CONTEXT.md`",
    ),
    "patches/global-qa-context.json": (
        "SBM-SUITE/context/QA_CONTEXT.md",
        "suite",
        "QA_CONTEXT.md",
        "## 5. Global `QA_CONTEXT.md`",
    ),
    "patches/security-context.json": (
        "SBM-SUITE/context/SECURITY_CONTEXT.md",
        "suite",
        "SECURITY_CONTEXT.md",
        "## 6. Global `SECURITY_CONTEXT.md`",
    ),
    "patches/data-context.json": (
        "SBM-SUITE/context/DATA_CONTEXT.md",
        "suite",
        "DATA_CONTEXT.md",
        "## 7. Global `DATA_CONTEXT.md`",
    ),
    "patches/decisions-context.json": (
        "SBM-SUITE/context/DECISIONS_CONTEXT.md",
        "suite",
        "DECISIONS_CONTEXT.md",
        "## 8. Global `DECISIONS_CONTEXT.md`",
    ),
    "patches/global-readme.json": (
        "SBM-SUITE/README.md",
        "suite_parent",
        "README.md",
        "## 13. Project and suite `README.md`",
    ),
    "patches/project-context.json": (
        "SBM-SUITE/{project_name}/context/PROJECT_CONTEXT.md",
        "project",
        "context/PROJECT_CONTEXT.md",
        "## 10. Project `context/PROJECT_CONTEXT.md`",
    ),
    "patches/project-qa-context.json": (
        "SBM-SUITE/{project_name}/context/QA_CONTEXT.md",
        "project",
        "context/QA_CONTEXT.md",
        "## 11. Project `context/QA_CONTEXT.md`",
    ),
    "patches/project-deploy-context.json": (
        "SBM-SUITE/{project_name}/context/DEPLOY_CONTEXT.md",
        "project",
        "context/DEPLOY_CONTEXT.md",
        "## 12. Project `context/DEPLOY_CONTEXT.md`",
    ),
    "patches/project-readme.json": (
        "SBM-SUITE/{project_name}/README.md",
        "project",
        "README.md",
        "## 13. Project and suite `README.md`",
    ),
}


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
        raise ContextValidationError(
            f"ZIP file must be named {UPGRADE_ZIP_NAME}"
        )
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
                    raise ContextValidationError(
                        f"Duplicate ZIP member: {member_name}"
                    )
                if info.flag_bits & 0x1:
                    raise ContextValidationError(
                        f"Encrypted ZIP members are not allowed: {member_name}"
                    )
                seen_names.add(member_name)
                members.append((info, member_path))

            corrupt_member = archive.testzip()
            if corrupt_member:
                raise ContextValidationError(
                    f"Corrupt ZIP member: {corrupt_member}"
                )
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
        raise ContextUpgradeOperationalError(
            "Unable to stage upgrade ZIP"
        ) from exc

    try:
        manifest = json.loads(
            (staging_directory / "manifest.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContextValidationError(
            "manifest.json must be valid UTF-8 JSON"
        ) from exc
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
        raise ContextValidationError(
            f"{label} must be a readable UTF-8 file"
        ) from exc


def validate_upgrade_manifest(
    manifest: dict,
    actual_files: set[str],
    staging_directory: Path,
    project_root: Path,
) -> tuple[str, list[str]]:
    project_name_value = manifest.get("project_name")
    if not isinstance(project_name_value, str):
        raise ContextValidationError("manifest.project_name must be a string")
    project_name = validate_project_name(project_name_value)
    if project_name.casefold() != project_root.name.casefold():
        raise ContextValidationError(
            "manifest.project_name does not match configured project"
        )
    if manifest.get("workflow") != UPGRADE_WORKFLOW:
        raise ContextValidationError(
            f"manifest.workflow must be {UPGRADE_WORKFLOW}"
        )

    allowed_files = _require_unique_string_list(manifest, "allowed_files")
    updated_files = _require_unique_string_list(manifest, "updated_files")
    content_hashes = manifest.get("content_hashes")
    execution_mode = manifest.get("execution_mode", "evidence")
    user_prompt_file = manifest.get("user_prompt_file")

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
        raise ContextValidationError(
            "manifest.content_hashes must be a string map"
        )

    system_allowlist = set(PATCH_DEFINITIONS) | set(INFORMATIONAL_FILES)
    missing_required_files = REQUIRED_ROOT_FILES - actual_files
    if missing_required_files:
        raise ContextValidationError(
            "ZIP is missing required files: "
            + ", ".join(sorted(missing_required_files))
        )

    unauthorized_files = actual_files - system_allowlist
    if unauthorized_files:
        raise ContextValidationError(
            "ZIP contains unauthorized files: "
            + ", ".join(sorted(unauthorized_files))
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
    if not set(updated_files).issubset(declared_allowlist):
        raise ContextValidationError(
            "manifest.updated_files must be a subset of manifest.allowed_files"
        )
    if not (expected_updated_files & set(PATCH_DEFINITIONS)):
        raise ContextValidationError(
            "Upgrade ZIP must contain at least one authorized patch file"
        )
    if set(updated_files) != expected_updated_files:
        raise ContextValidationError(
            "manifest.updated_files must match non-manifest ZIP files"
        )
    if set(content_hashes) != expected_updated_files:
        raise ContextValidationError(
            "manifest.content_hashes must match non-manifest ZIP files"
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
            raise ContextValidationError(
                f"SHA-256 mismatch for {archive_path}"
            )

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
        raise ContextValidationError(
            f"Unsupported manifest.commit.type: {commit_type}"
        )

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

    return project_name, updated_files


def _extract_contract_headings(
    format_markdown: str,
    contract_section: str,
) -> list[str]:
    section_start = format_markdown.find(contract_section)
    if section_start < 0:
        raise ContextValidationError(
            f"FORMAT_CONTEXT.md is missing contract section: {contract_section}"
        )

    section_body = format_markdown[section_start + len(contract_section) :]
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
            raise ContextValidationError(
                f"Target symlinks are not allowed: {target}"
            )
    if not target.is_file():
        raise ContextValidationError(
            f"Target must be an existing regular file: {target}"
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


def validate_and_build_replacements(
    staging_directory: Path,
    updated_files: list[str],
    project_name: str,
    suite_context_root: Path,
    project_root: Path,
) -> dict[str, tuple[Path, str]]:
    format_path = suite_context_root / FORMAT_CONTEXT_FILENAME
    if format_path.is_symlink() or not format_path.is_file():
        raise ContextValidationError(
            f"Missing required format contract: {format_path}"
        )
    format_markdown = _read_utf8(format_path, "FORMAT_CONTEXT.md")
    replacements: dict[str, tuple[Path, str]] = {}
    target_headings_seen: set[tuple[str, str]] = set()

    for patch_path in updated_files:
        if patch_path not in PATCH_DEFINITIONS:
            continue
        target_template, scope, relative_path, contract_section = PATCH_DEFINITIONS[
            patch_path
        ]
        expected_target = target_template.format(project_name=project_name)
        target = _resolve_target(
            scope,
            relative_path,
            suite_context_root,
            project_root,
        )
        allowed_headings = _extract_contract_headings(
            format_markdown,
            contract_section,
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
        for operation in operations:
            key = (expected_target, operation["heading"])
            if key in target_headings_seen:
                raise ContextValidationError(
                    f"Duplicate target heading across patches: {expected_target} {operation['heading']}"
                )
            target_headings_seen.add(key)

        current_markdown = replacements.get(expected_target, (target, _read_utf8(target, expected_target)))[1]
        patched_markdown = _apply_operations(current_markdown, operations)
        actual_headings = _document_headings(patched_markdown)
        if actual_headings != allowed_headings:
            raise ContextValidationError(
                f"Patched document violates FORMAT_CONTEXT.md: {expected_target}"
            )
        replacements[expected_target] = (target, patched_markdown)

    if not replacements:
        raise ContextValidationError("No valid context replacements were generated")
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

        for archive_target in sorted(replacements):
            target, patched_content = replacements[archive_target]
            _copy_file(
                target,
                backup_directory / "previous" / PurePosixPath(archive_target),
            )
            applied_path = (
                backup_directory / "applied" / PurePosixPath(archive_target)
            )
            applied_path.parent.mkdir(parents=True, exist_ok=True)
            applied_path.write_text(patched_content, encoding="utf-8")
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
            "Context upgrade failed and rollback was incomplete: "
            + ", ".join(errors)
        )


def apply_replacements(
    replacements: dict[str, tuple[Path, str]],
    backup_directory: Path,
):
    replaced_targets: list[str] = []
    try:
        for archive_target, (target, patched_content) in replacements.items():
            _atomic_write_text(patched_content, target)
            replaced_targets.append(archive_target)
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
    input_directory: str = CONTEXT_UPGRADE_INPUT_DIRECTORY,
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
    resolved_project_root = resolve_existing_directory(
        project_root,
        "context_upgrade_project_root",
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
        project_name, updated_files = validate_upgrade_manifest(
            manifest,
            actual_files,
            staging_directory,
            resolved_project_root,
        )
        replacements = validate_and_build_replacements(
            staging_directory,
            updated_files,
            project_name,
            suite_root,
            resolved_project_root,
        )
        timestamp = now().strftime("%Y%m%d_%H%M%S_%f")
        backup_directory = create_upgrade_backup(
            staging_directory,
            updated_files,
            replacements,
            backup_path,
            project_name,
            timestamp,
        )
        apply_replacements(replacements, backup_directory)
        cleanup_upgrade_input(zip_path)

    commit_message = backup_directory / "COMMIT_MESSAGE.md"
    executive_readme = backup_directory / "EXECUTIVE_README.md"
    return ContextUpgradeResponse(
        project_name=project_name,
        workflow=UPGRADE_WORKFLOW,
        updated_files=sorted(replacements),
        backup_directory=str(backup_directory),
        commit_message_file=(
            str(commit_message) if commit_message.is_file() else ""
        ),
        executive_readme_file=(
            str(executive_readme) if executive_readme.is_file() else ""
        ),
        input_cleaned=not zip_path.exists(),
        errors=[],
    )
