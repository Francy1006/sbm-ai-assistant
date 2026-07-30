from __future__ import annotations

import json
import os
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
INFORMATIONAL_FILES = frozenset(
    {
        "EXECUTIVE_README.md",
        "COMMIT_MESSAGE.md",
        "manifest.json",
    }
)


class ContextUpgradeOperationalError(RuntimeError):
    pass


def _replaceable_paths(project_name: str) -> dict[str, tuple[str, str]]:
    return {
        "SBM-SUITE/PROJECT_CONTEXT.md": (
            "suite",
            "PROJECT_CONTEXT.md",
        ),
        "SBM-SUITE/README.md": (
            "suite",
            "README.md",
        ),
        "SBM-SUITE/context/SUITE_CONTEXT.md": (
            "suite",
            "SUITE_CONTEXT.md",
        ),
        (
            f"SBM-SUITE/{project_name}/context/PROJECT_CONTEXT.md"
        ): (
            "project",
            "context/PROJECT_CONTEXT.md",
        ),
        f"SBM-SUITE/{project_name}/README.md": (
            "project",
            "README.md",
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

    if set(updated_files) != expected_updated_files:
        raise ContextValidationError(
            "manifest.updated_files must match non-manifest ZIP files"
        )

    hashed_files = expected_updated_files

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
        timestamp = now().strftime("%Y%m%d_%H%M%S")
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
