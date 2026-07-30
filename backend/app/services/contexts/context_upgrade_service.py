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
FORMAT_CONTRACT_SECTIONS = {
    "global_project_context": "## 2. Global `PROJECT_CONTEXT.md`",
    "global_suite_context": "## 3. Global `SUITE_CONTEXT.md`",
    "global_business_context": "## 4. Global `BUSINESS_CONTEXT.md`",
    "global_qa_context": "## 5. Global `QA_CONTEXT.md`",
    "global_security_context": "## 6. Global `SECURITY_CONTEXT.md`",
    "global_data_context": "## 7. Global `DATA_CONTEXT.md`",
    "global_decisions_context": "## 8. Global `DECISIONS_CONTEXT.md`",
    "project_project_context": "## 9. Project `context/PROJECT_CONTEXT.md`",
    "project_qa_context": "## 10. Project `context/QA_CONTEXT.md`",
}
INFORMATIONAL_FILES = frozenset(
    {
        "EXECUTIVE_README.md",
        "COMMIT_MESSAGE.md",
        "USER_PROMPT.md",
        "manifest.json",
    }
)


class ContextUpgradeOperationalError(RuntimeError):
    pass


def _replaceable_paths(project_name: str) -> dict[str, tuple[str, str]]:
    return {
        "SBM-SUITE/context/PROJECT_CONTEXT.md": (
            "suite",
            "PROJECT_CONTEXT.md",
        ),
        "SBM-SUITE/context/SUITE_CONTEXT.md": (
            "suite",
            "SUITE_CONTEXT.md",
        ),
        "SBM-SUITE/context/BUSINESS_CONTEXT.md": (
            "suite",
            "BUSINESS_CONTEXT.md",
        ),
        "SBM-SUITE/context/QA_CONTEXT.md": (
            "suite",
            "QA_CONTEXT.md",
        ),
        "SBM-SUITE/context/SECURITY_CONTEXT.md": (
            "suite",
            "SECURITY_CONTEXT.md",
        ),
        "SBM-SUITE/context/DATA_CONTEXT.md": (
            "suite",
            "DATA_CONTEXT.md",
        ),
        "SBM-SUITE/context/DECISIONS_CONTEXT.md": (
            "suite",
            "DECISIONS_CONTEXT.md",
        ),
        f"SBM-SUITE/{project_name}/context/PROJECT_CONTEXT.md": (
            "project",
            "context/PROJECT_CONTEXT.md",
        ),
        f"SBM-SUITE/{project_name}/context/QA_CONTEXT.md": (
            "project",
            "context/QA_CONTEXT.md",
        ),
    }


def locate_upgrade_zip(input_directory: Path) -> Path:
    zip_files = sorted(
        path
        for path in input_directory.iterdir()
        if path.is_file() and path.suffix.lower() == ".zip"
    )

    if not zip_files:
        raise ContextValidationError(
            f"No ZIP file found in {input_directory}"
        )

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
        raise ContextValidationError(
            f"Invalid ZIP member path: {name!r}"
        )

    path = PurePosixPath(name)

    if path.is_absolute() or ".." in path.parts:
        raise ContextValidationError(
            f"Unsafe ZIP member path: {name}"
        )

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
            file_members = []
            seen_names = set()

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
                        f"Encrypted ZIP members are not allowed: "
                        f"{member_name}"
                    )

                seen_names.add(member_name)
                file_members.append((info, member_path))

            corrupt_member = archive.testzip()

            if corrupt_member:
                raise ContextValidationError(
                    f"Corrupt ZIP member: {corrupt_member}"
                )

            if "manifest.json" not in seen_names:
                raise ContextValidationError(
                    "ZIP must contain manifest.json"
                )

            for info, member_path in file_members:
                destination = staging_directory.joinpath(
                    *member_path.parts
                )
                destination.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                with (
                    archive.open(info) as source,
                    destination.open("xb") as target,
                ):
                    shutil.copyfileobj(source, target)
                    target.flush()
                    os.fsync(target.fileno())
    except BadZipFile as exc:
        raise ContextValidationError("Upgrade ZIP is corrupt") from exc
    except RuntimeError as exc:
        raise ContextValidationError(
            "Upgrade ZIP cannot be read safely"
        ) from exc
    except OSError as exc:
        raise ContextUpgradeOperationalError(
            "Unable to stage upgrade ZIP"
        ) from exc

    manifest_path = staging_directory / "manifest.json"

    try:
        manifest = json.loads(
            manifest_path.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContextValidationError(
            "manifest.json must be valid UTF-8 JSON"
        ) from exc

    if not isinstance(manifest, dict):
        raise ContextValidationError(
            "manifest.json must contain a JSON object"
        )

    return manifest, seen_names


def _require_unique_string_list(
    manifest: dict,
    field_name: str,
) -> list[str]:
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


def validate_upgrade_manifest(
    manifest: dict,
    actual_files: set[str],
    staging_directory: Path,
    project_root: Path,
) -> tuple[str, list[str], dict[str, tuple[str, str]]]:
    project_name_value = manifest.get("project_name")

    if not isinstance(project_name_value, str):
        raise ContextValidationError(
            "manifest.project_name must be a string"
        )

    project_name = validate_project_name(project_name_value)

    if project_name.casefold() != project_root.name.casefold():
        raise ContextValidationError(
            "manifest.project_name does not match configured project"
        )

    if manifest.get("workflow") != UPGRADE_WORKFLOW:
        raise ContextValidationError(
            f"manifest.workflow must be {UPGRADE_WORKFLOW}"
        )

    allowed_files = _require_unique_string_list(
        manifest,
        "allowed_files",
    )
    updated_files = _require_unique_string_list(
        manifest,
        "updated_files",
    )
    content_hashes = manifest.get("content_hashes")
    output_filename = manifest.get("output_filename")
    commit_field = (
        "commit"
        if "commit" in manifest
        else "commit_metadata"
    )
    commit_metadata = manifest.get(commit_field)
    rag_metadata = manifest.get("rag")
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

    if execution_mode == "user-guided":
        if user_prompt_file != "USER_PROMPT.md":
            raise ContextValidationError(
                "manifest.user_prompt_file must be USER_PROMPT.md "
                "in user-guided mode"
            )

        if "USER_PROMPT.md" not in actual_files:
            raise ContextValidationError(
                "USER_PROMPT.md is required in user-guided mode"
            )

    if (
        "output_filename" in manifest
        and output_filename != UPGRADE_ZIP_NAME
    ):
        raise ContextValidationError(
            f"manifest.output_filename must be {UPGRADE_ZIP_NAME}"
        )

    if not isinstance(content_hashes, dict) or any(
        not isinstance(path, str)
        or not isinstance(digest, str)
        for path, digest in content_hashes.items()
    ):
        raise ContextValidationError(
            "manifest.content_hashes must be a string map"
        )

    if not isinstance(commit_metadata, dict) or not commit_metadata:
        raise ContextValidationError(
            f"manifest.{commit_field} must be a non-empty object"
        )

    if rag_metadata is not None and not isinstance(rag_metadata, dict):
        raise ContextValidationError(
            "manifest.rag must be an object when provided"
        )

    replaceable_paths = _replaceable_paths(project_name)
    system_allowlist = set(replaceable_paths) | set(
        INFORMATIONAL_FILES
    )

    unauthorized_files = actual_files - system_allowlist

    if unauthorized_files:
        raise ContextValidationError(
            "ZIP contains unauthorized files: "
            + ", ".join(sorted(unauthorized_files))
        )

    declared_allowlist = set(allowed_files)
    unauthorized_allowed_files = declared_allowlist - system_allowlist

    if unauthorized_allowed_files:
        raise ContextValidationError(
            "manifest.allowed_files contains unauthorized files: "
            + ", ".join(sorted(unauthorized_allowed_files))
        )

    undeclared_files = actual_files - declared_allowlist

    if undeclared_files:
        raise ContextValidationError(
            "ZIP contains files absent from manifest.allowed_files: "
            + ", ".join(sorted(undeclared_files))
        )

    expected_updated_files = actual_files - {"manifest.json"}

    replaceable_updated_files = expected_updated_files & set(replaceable_paths)

    if not replaceable_updated_files:
        raise ContextValidationError(
            "Upgrade ZIP must contain at least one authorized context file"
        )

    if set(updated_files) != expected_updated_files:
        raise ContextValidationError(
            "manifest.updated_files must match non-manifest ZIP files"
        )

    hashed_files = expected_updated_files

    if any(
        path not in replaceable_paths and path not in INFORMATIONAL_FILES
        for path in hashed_files
    ):
        raise ContextValidationError(
            "Upgrade ZIP contains an unsupported hashed file"
        )

    if set(content_hashes) != hashed_files:
        raise ContextValidationError(
            "manifest.content_hashes must match non-manifest ZIP files"
        )

    for archive_path in sorted(hashed_files):
        staged_file = staging_directory.joinpath(
            *PurePosixPath(archive_path).parts
        )

        try:
            with staged_file.open(
                "r",
                encoding="utf-8",
                newline="",
            ) as file_handle:
                content = file_handle.read()
        except (OSError, UnicodeError) as exc:
            raise ContextValidationError(
                f"ZIP file must be UTF-8: {archive_path}"
            ) from exc

        if content_hash(content) != content_hashes[archive_path]:
            raise ContextValidationError(
                f"SHA-256 mismatch for {archive_path}"
            )

    return project_name, updated_files, replaceable_paths



def _read_utf8_file(path: Path, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ContextValidationError(
            f"{label} must be a readable UTF-8 file"
        ) from exc


def _extract_contract_headings(
    format_markdown: str,
    section_heading: str,
) -> list[str]:
    section_start = format_markdown.find(section_heading)

    if section_start < 0:
        raise ContextValidationError(
            f"FORMAT_CONTEXT.md is missing contract section: "
            f"{section_heading}"
        )

    section_body_start = section_start + len(section_heading)
    section_body = format_markdown[section_body_start:]

    format_block = re.search(
        r"```text\s*\n(?P<body>.*?)\n```",
        section_body,
        flags=re.DOTALL,
    )

    if format_block is None:
        raise ContextValidationError(
            f"FORMAT_CONTEXT.md contract section has no text block: "
            f"{section_heading}"
        )

    headings = [
        line.strip()
        for line in format_block.group("body").splitlines()
        if re.fullmatch(r"#{1,2}\s+.+", line.strip())
    ]

    if not headings:
        raise ContextValidationError(
            f"FORMAT_CONTEXT.md contract section has no headings: "
            f"{section_heading}"
        )

    if len(headings) != len(set(headings)):
        raise ContextValidationError(
            f"FORMAT_CONTEXT.md contains duplicated required headings: "
            f"{section_heading}"
        )

    return headings


def _document_headings(markdown: str) -> list[str]:
    headings = []

    for line in markdown.splitlines():
        normalized = line.strip()

        if re.fullmatch(r"#{1,2}\s+.+", normalized):
            headings.append(normalized)

    return headings


def _contract_key_for_archive_path(
    archive_path: str,
    project_name: str,
) -> str | None:
    global_paths = {
        "SBM-SUITE/context/PROJECT_CONTEXT.md": "global_project_context",
        "SBM-SUITE/context/SUITE_CONTEXT.md": "global_suite_context",
        "SBM-SUITE/context/BUSINESS_CONTEXT.md": "global_business_context",
        "SBM-SUITE/context/QA_CONTEXT.md": "global_qa_context",
        "SBM-SUITE/context/SECURITY_CONTEXT.md": "global_security_context",
        "SBM-SUITE/context/DATA_CONTEXT.md": "global_data_context",
        "SBM-SUITE/context/DECISIONS_CONTEXT.md": "global_decisions_context",
    }

    if archive_path in global_paths:
        return global_paths[archive_path]

    if (
        archive_path
        == f"SBM-SUITE/{project_name}/context/PROJECT_CONTEXT.md"
    ):
        return "project_project_context"

    if (
        archive_path
        == f"SBM-SUITE/{project_name}/context/QA_CONTEXT.md"
    ):
        return "project_qa_context"

    return None


def validate_staged_context_formats(
    staging_directory: Path,
    updated_files: list[str],
    project_name: str,
    suite_root: Path,
):
    format_context_path = suite_root / FORMAT_CONTEXT_FILENAME

    if format_context_path.is_symlink():
        raise ContextValidationError(
            "FORMAT_CONTEXT.md must not be a symlink"
        )

    if not format_context_path.is_file():
        raise ContextValidationError(
            f"Missing required format contract: {format_context_path}"
        )

    format_markdown = _read_utf8_file(
        format_context_path,
        "FORMAT_CONTEXT.md",
    )
    expected_by_key = {
        contract_key: _extract_contract_headings(
            format_markdown,
            section_heading,
        )
        for contract_key, section_heading in FORMAT_CONTRACT_SECTIONS.items()
    }

    for archive_path in updated_files:
        contract_key = _contract_key_for_archive_path(
            archive_path,
            project_name,
        )

        if contract_key is None:
            continue

        staged_path = staging_directory.joinpath(
            *PurePosixPath(archive_path).parts
        )
        markdown = _read_utf8_file(
            staged_path,
            archive_path,
        )
        actual_headings = _document_headings(markdown)
        expected_headings = expected_by_key[contract_key]

        if len(actual_headings) != len(set(actual_headings)):
            raise ContextValidationError(
                f"Duplicated headings in {archive_path}"
            )

        if actual_headings != expected_headings:
            missing = [
                heading
                for heading in expected_headings
                if heading not in actual_headings
            ]
            unexpected = [
                heading
                for heading in actual_headings
                if heading not in expected_headings
            ]

            details = []

            if missing:
                details.append(
                    "missing: " + ", ".join(missing)
                )

            if unexpected:
                details.append(
                    "unexpected: " + ", ".join(unexpected)
                )

            if not missing and not unexpected:
                details.append("required headings are out of order")

            raise ContextValidationError(
                f"Context format validation failed for {archive_path}: "
                + "; ".join(details)
            )



def _validated_target(
    archive_path: str,
    mapping: tuple[str, str],
    suite_root: Path,
    project_root: Path,
) -> Path:
    scope, relative_path = mapping
    root = suite_root if scope == "suite" else project_root
    target = root / relative_path

    if not target.is_relative_to(root):
        raise ContextValidationError(
            f"Target escapes configured root: {archive_path}"
        )

    current = root

    for part in target.relative_to(root).parts:
        current = current / part

        if current.is_symlink():
            raise ContextValidationError(
                f"Target symlinks are not allowed: {archive_path}"
            )

    if not target.is_file():
        raise ContextValidationError(
            f"Target must be an existing regular file: {archive_path}"
        )

    return target


def _copy_file(source: Path, destination: Path):
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def create_upgrade_backup(
    staging_directory: Path,
    updated_files: list[str],
    replaceable_paths: dict[str, tuple[str, str]],
    suite_root: Path,
    project_root: Path,
    backup_root: Path,
    project_name: str,
    timestamp: str,
) -> tuple[Path, dict[str, Path]]:
    backup_directory = backup_root / f"{timestamp}_{project_name}"

    try:
        backup_directory.mkdir(parents=True, exist_ok=False)
        (backup_directory / "previous").mkdir()
        (backup_directory / "applied").mkdir()

        for info_name in INFORMATIONAL_FILES:
            staged_info = staging_directory / info_name

            if staged_info.is_file():
                _copy_file(
                    staged_info,
                    backup_directory / info_name,
                )

        targets = {}

        for archive_path in updated_files:
            mapping = replaceable_paths.get(archive_path)

            if mapping is None:
                continue

            target = _validated_target(
                archive_path,
                mapping,
                suite_root,
                project_root,
            )
            targets[archive_path] = target
            _copy_file(
                target,
                backup_directory
                / "previous"
                / PurePosixPath(archive_path),
            )
    except (OSError, shutil.Error) as exc:
        raise ContextUpgradeOperationalError(
            "Unable to create context upgrade backup"
        ) from exc

    return backup_directory, targets


def _fsync_directory(directory: Path):
    descriptor = os.open(directory, os.O_RDONLY)

    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_replace_file(source: Path, target: Path):
    temporary_path = None

    try:
        target_mode = stat.S_IMODE(target.stat().st_mode)

        with tempfile.NamedTemporaryFile(
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".upgrade",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)

            with source.open("rb") as staged_file:
                shutil.copyfileobj(staged_file, temporary_file)

            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        os.chmod(temporary_path, target_mode)
        os.replace(temporary_path, target)
        _fsync_directory(target.parent)
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()


def rollback_replacements(
    replaced_files: list[str],
    targets: dict[str, Path],
    backup_directory: Path,
):
    rollback_errors = []

    for archive_path in reversed(replaced_files):
        previous_file = (
            backup_directory
            / "previous"
            / PurePosixPath(archive_path)
        )

        try:
            _atomic_replace_file(
                previous_file,
                targets[archive_path],
            )
        except Exception as exc:
            rollback_errors.append(
                f"{archive_path}: {type(exc).__name__}"
            )

    if rollback_errors:
        raise ContextUpgradeOperationalError(
            "Context upgrade failed and rollback was incomplete: "
            + ", ".join(rollback_errors)
        )


def apply_replacements(
    staging_directory: Path,
    updated_files: list[str],
    targets: dict[str, Path],
    backup_directory: Path,
):
    replaced_files = []

    try:
        for archive_path in updated_files:
            target = targets.get(archive_path)

            if target is None:
                continue

            staged_file = staging_directory.joinpath(
                *PurePosixPath(archive_path).parts
            )
            _atomic_replace_file(staged_file, target)
            replaced_files.append(archive_path)

        for archive_path in replaced_files:
            staged_file = staging_directory.joinpath(
                *PurePosixPath(archive_path).parts
            )
            _copy_file(
                staged_file,
                backup_directory
                / "applied"
                / PurePosixPath(archive_path),
            )
    except Exception as exc:
        rollback_replacements(
            replaced_files,
            targets,
            backup_directory,
        )
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

    with tempfile.TemporaryDirectory(
        prefix="context-upgrade-",
    ) as temporary_directory:
        staging_directory = Path(temporary_directory)

        if staging_directory.is_relative_to(input_path):
            raise ContextUpgradeOperationalError(
                "Staging directory must be outside input"
            )

        manifest, actual_files = validate_and_stage_zip(
            zip_path,
            staging_directory,
        )
        project_name, updated_files, replaceable_paths = (
            validate_upgrade_manifest(
                manifest,
                actual_files,
                staging_directory,
                resolved_project_root,
            )
        )
        validate_staged_context_formats(
            staging_directory=staging_directory,
            updated_files=updated_files,
            project_name=project_name,
            suite_root=suite_root,
        )

        timestamp = now().strftime("%Y%m%d_%H%M%S_%f")
        backup_directory, targets = create_upgrade_backup(
            staging_directory=staging_directory,
            updated_files=updated_files,
            replaceable_paths=replaceable_paths,
            suite_root=suite_root,
            project_root=resolved_project_root,
            backup_root=backup_path,
            project_name=project_name,
            timestamp=timestamp,
        )
        apply_replacements(
            staging_directory=staging_directory,
            updated_files=updated_files,
            targets=targets,
            backup_directory=backup_directory,
        )
        cleanup_upgrade_input(zip_path)

    commit_message = backup_directory / "COMMIT_MESSAGE.md"
    executive_readme = backup_directory / "EXECUTIVE_README.md"

    return ContextUpgradeResponse(
        project_name=project_name,
        workflow=UPGRADE_WORKFLOW,
        updated_files=updated_files,
        backup_directory=str(backup_directory),
        commit_message_file=(
            str(commit_message) if commit_message.is_file() else ""
        ),
        executive_readme_file=(
            str(executive_readme)
            if executive_readme.is_file()
            else ""
        ),
        input_cleaned=not zip_path.exists(),
        errors=[],
    )
