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
    DOCUMENTATION_UPGRADE_BACKUP_ROOT,
    DOCUMENTATION_UPGRADE_DOCUMENTATION_ROOT,
    DOCUMENTATION_UPGRADE_INPUT_DIRECTORY,
)
from app.schemas.documentation import DocumentationUpgradeResponse
from app.services.contexts.context_index_service import content_hash
from app.services.contexts.file_discovery_service import (
    ContextValidationError,
    resolve_existing_directory,
)


UPGRADE_ZIP_NAME = "documentation-upgrade.zip"
UPGRADE_WORKFLOW = "documentation-upgrade"
DOCUMENTATION_ROOT_NAME = "documentation"
INFORMATIONAL_FILES = frozenset(
    {
        "EXECUTIVE_README.md",
        "COMMIT_MESSAGE.md",
        "USER_PROMPT.md",
        "manifest.json",
    }
)
PROTECTED_DOCUMENTATION_PATHS = frozenset(
    {
        "documentation/FORMAT_CONTEXT.md",
        "documentation/SYS_PROMPT.md",
    }
)


class DocumentationUpgradeOperationalError(RuntimeError):
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
            "Expected exactly one ZIP file in " f"{input_directory}"
        )

    zip_path = zip_files[0]

    if zip_path.name != UPGRADE_ZIP_NAME:
        raise ContextValidationError(f"ZIP file must be named {UPGRADE_ZIP_NAME}")

    if zip_path.is_symlink():
        raise ContextValidationError("Upgrade ZIP must not be a symlink")

    return zip_path


def _validate_member_name(
    name: str,
) -> PurePosixPath:
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
            file_members = []
            seen_names = set()

            for info in archive.infolist():
                member_path = _validate_member_name(info.filename)

                if _is_zip_symlink(info):
                    raise ContextValidationError(
                        "ZIP symlinks are not allowed: " f"{info.filename}"
                    )

                if info.is_dir():
                    continue

                member_name = member_path.as_posix()

                if member_name in seen_names:
                    raise ContextValidationError(
                        "Duplicate ZIP member: " f"{member_name}"
                    )

                if info.flag_bits & 0x1:
                    raise ContextValidationError(
                        "Encrypted ZIP members are not " f"allowed: {member_name}"
                    )

                seen_names.add(member_name)
                file_members.append((info, member_path))

            corrupt_member = archive.testzip()

            if corrupt_member:
                raise ContextValidationError("Corrupt ZIP member: " f"{corrupt_member}")

            if "manifest.json" not in seen_names:
                raise ContextValidationError("ZIP must contain manifest.json")

            for info, member_path in file_members:
                destination = staging_directory.joinpath(*member_path.parts)
                destination.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                with (
                    archive.open(info) as source,
                    destination.open("xb") as target,
                ):
                    shutil.copyfileobj(
                        source,
                        target,
                    )
                    target.flush()
                    os.fsync(target.fileno())
    except BadZipFile as exc:
        raise ContextValidationError("Upgrade ZIP is corrupt") from exc
    except RuntimeError as exc:
        raise ContextValidationError("Upgrade ZIP cannot be read safely") from exc
    except OSError as exc:
        raise DocumentationUpgradeOperationalError(
            "Unable to stage upgrade ZIP"
        ) from exc

    manifest_path = staging_directory / "manifest.json"

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
    ) as exc:
        raise ContextValidationError("manifest.json must be valid UTF-8 JSON") from exc

    if not isinstance(manifest, dict):
        raise ContextValidationError("manifest.json must contain a JSON object")

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
            f"manifest.{field_name} must be " "a unique string list"
        )

    return value


def _validate_documentation_archive_path(
    archive_path: str,
) -> PurePosixPath:
    path = _validate_member_name(archive_path)

    if not path.parts or path.parts[0] != DOCUMENTATION_ROOT_NAME:
        raise ContextValidationError(
            "Documentation output paths must begin " "with documentation/"
        )

    if path.suffix.lower() != ".md":
        raise ContextValidationError(
            "Documentation output files must use " f".md: {archive_path}"
        )

    if archive_path in PROTECTED_DOCUMENTATION_PATHS:
        raise ContextValidationError(
            "Protected documentation file cannot " f"be upgraded: {archive_path}"
        )

    return path


def _read_utf8_file(
    path: Path,
    label: str,
) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (
        OSError,
        UnicodeError,
    ) as exc:
        raise ContextValidationError(f"{label} must be a readable UTF-8 file") from exc


def _validate_markdown_structure(
    markdown: str,
    archive_path: str,
) -> None:
    headings = [
        line.strip() for line in markdown.splitlines() if line.strip().startswith("#")
    ]

    if not headings:
        raise ContextValidationError(
            "Documentation file has no headings: " f"{archive_path}"
        )

    if not headings[0].startswith("# "):
        raise ContextValidationError(
            "Documentation file must begin with one "
            f"level-one heading: {archive_path}"
        )

    level_one_headings = [heading for heading in headings if heading.startswith("# ")]

    if len(level_one_headings) != 1:
        raise ContextValidationError(
            "Documentation file must contain exactly "
            f"one level-one heading: {archive_path}"
        )

    required_metadata = (
        "> **Last updated:**",
        "> **Purpose:**",
        "> **Source of truth:**",
    )

    for marker in required_metadata:
        if marker not in markdown:
            raise ContextValidationError(
                "Documentation metadata is missing " f"{marker!r}: {archive_path}"
            )

    if "## " not in markdown:
        raise ContextValidationError(
            "Documentation file must contain " f"level-two sections: {archive_path}"
        )

    if "Document boundary" not in markdown:
        raise ContextValidationError(
            "Documentation file must preserve a " f"document boundary: {archive_path}"
        )


def _resolve_target(
    archive_path: str,
    documentation_root: Path,
) -> Path:
    member_path = _validate_documentation_archive_path(archive_path)
    relative_parts = member_path.parts[1:]
    target = documentation_root.joinpath(*relative_parts)

    if not target.is_relative_to(documentation_root):
        raise ContextValidationError(
            "Target escapes configured " f"documentation root: {archive_path}"
        )

    current = documentation_root

    for part in relative_parts:
        current = current / part

        if current.is_symlink():
            raise ContextValidationError(
                "Target symlinks are not allowed: " f"{archive_path}"
            )

    if not target.is_file():
        raise ContextValidationError(
            "Target must be an existing regular " f"file: {archive_path}"
        )

    return target


def validate_upgrade_manifest(
    manifest: dict,
    actual_files: set[str],
    staging_directory: Path,
    documentation_root: Path,
) -> tuple[
    str,
    list[str],
    dict[str, Path],
]:
    project_name = manifest.get("project_name")

    if not isinstance(project_name, str) or not project_name.strip():
        raise ContextValidationError(
            "manifest.project_name must be " "a non-empty string"
        )

    if manifest.get("workflow") != UPGRADE_WORKFLOW:
        raise ContextValidationError("manifest.workflow must be " f"{UPGRADE_WORKFLOW}")

    if manifest.get("output_filename") != UPGRADE_ZIP_NAME:
        raise ContextValidationError(
            "manifest.output_filename must be " f"{UPGRADE_ZIP_NAME}"
        )

    if manifest.get("documentation_root") != DOCUMENTATION_ROOT_NAME:
        raise ContextValidationError(
            "manifest.documentation_root must be " f"{DOCUMENTATION_ROOT_NAME}"
        )

    execution_mode = manifest.get("execution_mode")
    user_prompt_file = manifest.get("user_prompt_file")

    if execution_mode not in {
        "evidence",
        "user-guided",
    }:
        raise ContextValidationError(
            "manifest.execution_mode must be " "evidence or user-guided"
        )

    if execution_mode == "evidence":
        if user_prompt_file is not None:
            raise ContextValidationError(
                "manifest.user_prompt_file must " "be null in evidence mode"
            )

        if "USER_PROMPT.md" in actual_files:
            raise ContextValidationError(
                "USER_PROMPT.md is not allowed " "in evidence mode"
            )

    if execution_mode == "user-guided":
        if user_prompt_file != "USER_PROMPT.md":
            raise ContextValidationError(
                "manifest.user_prompt_file must "
                "be USER_PROMPT.md in "
                "user-guided mode"
            )

        if "USER_PROMPT.md" not in actual_files:
            raise ContextValidationError(
                "USER_PROMPT.md is required in " "user-guided mode"
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
    commit_metadata = manifest.get("commit")
    rag_metadata = manifest.get("rag")
    evidence_metadata = manifest.get("evidence")

    if not isinstance(content_hashes, dict) or any(
        not isinstance(path, str) or not isinstance(digest, str)
        for path, digest in content_hashes.items()
    ):
        raise ContextValidationError("manifest.content_hashes must be " "a string map")

    if not isinstance(commit_metadata, dict) or not commit_metadata:
        raise ContextValidationError("manifest.commit must be a " "non-empty object")

    if not isinstance(rag_metadata, dict):
        raise ContextValidationError("manifest.rag must be an object")

    if not isinstance(
        evidence_metadata,
        dict,
    ):
        raise ContextValidationError("manifest.evidence must be an object")

    declared_allowlist = set(allowed_files)
    actual_without_manifest = actual_files - {"manifest.json"}

    system_allowlist = set(INFORMATIONAL_FILES)
    documentation_paths = {
        path
        for path in declared_allowlist
        if path.startswith(f"{DOCUMENTATION_ROOT_NAME}/")
    }

    for archive_path in documentation_paths:
        _validate_documentation_archive_path(archive_path)

    unauthorized_allowed_files = (
        declared_allowlist - system_allowlist - documentation_paths
    )

    if unauthorized_allowed_files:
        raise ContextValidationError(
            "manifest.allowed_files contains "
            "unauthorized files: " + ", ".join(sorted(unauthorized_allowed_files))
        )

    undeclared_files = actual_files - declared_allowlist

    if undeclared_files:
        raise ContextValidationError(
            "ZIP contains files absent from "
            "manifest.allowed_files: " + ", ".join(sorted(undeclared_files))
        )

    if set(updated_files) != (actual_without_manifest):
        raise ContextValidationError(
            "manifest.updated_files must match " "non-manifest ZIP files"
        )

    if set(content_hashes) != (actual_without_manifest):
        raise ContextValidationError(
            "manifest.content_hashes must match " "non-manifest ZIP files"
        )

    replaceable_files = sorted(
        path for path in updated_files if path.startswith(f"{DOCUMENTATION_ROOT_NAME}/")
    )

    if not replaceable_files:
        raise ContextValidationError(
            "Upgrade ZIP must contain at least " "one documentation file"
        )

    targets: dict[str, Path] = {}

    for archive_path in sorted(actual_without_manifest):
        staged_file = staging_directory.joinpath(*PurePosixPath(archive_path).parts)
        content = _read_utf8_file(
            staged_file,
            archive_path,
        )

        if content_hash(content) != content_hashes[archive_path]:
            raise ContextValidationError("SHA-256 mismatch for " f"{archive_path}")

        if archive_path.startswith(f"{DOCUMENTATION_ROOT_NAME}/"):
            _validate_markdown_structure(
                content,
                archive_path,
            )
            targets[archive_path] = _resolve_target(
                archive_path,
                documentation_root,
            )

    return (
        project_name.strip(),
        updated_files,
        targets,
    )


def _copy_file(
    source: Path,
    destination: Path,
) -> None:
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    shutil.copy2(
        source,
        destination,
    )


def create_upgrade_backup(
    staging_directory: Path,
    updated_files: list[str],
    targets: dict[str, Path],
    backup_root: Path,
    project_name: str,
    timestamp: str,
) -> Path:
    backup_directory = backup_root / f"{timestamp}_{project_name}"

    try:
        backup_directory.mkdir(
            parents=True,
            exist_ok=False,
        )
        (backup_directory / "previous").mkdir()
        (backup_directory / "applied").mkdir()

        for info_name in INFORMATIONAL_FILES:
            staged_info = staging_directory / info_name

            if staged_info.is_file():
                _copy_file(
                    staged_info,
                    backup_directory / info_name,
                )

        for archive_path, target in targets.items():
            _copy_file(
                target,
                backup_directory / "previous" / PurePosixPath(archive_path),
            )
    except (
        OSError,
        shutil.Error,
    ) as exc:
        raise (
            DocumentationUpgradeOperationalError(
                "Unable to create documentation " "upgrade backup"
            )
        ) from exc

    return backup_directory


def _fsync_directory(
    directory: Path,
) -> None:
    descriptor = os.open(
        directory,
        os.O_RDONLY,
    )

    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_replace_file(
    source: Path,
    target: Path,
) -> None:
    temporary_path = None

    try:
        target_mode = stat.S_IMODE(target.stat().st_mode)

        with tempfile.NamedTemporaryFile(
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".documentation-upgrade",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)

            with source.open("rb") as staged_file:
                shutil.copyfileobj(
                    staged_file,
                    temporary_file,
                )

            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        os.chmod(
            temporary_path,
            target_mode,
        )
        os.replace(
            temporary_path,
            target,
        )
        _fsync_directory(target.parent)
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()


def rollback_replacements(
    replaced_files: list[str],
    targets: dict[str, Path],
    backup_directory: Path,
) -> None:
    rollback_errors = []

    for archive_path in reversed(replaced_files):
        previous_file = backup_directory / "previous" / PurePosixPath(archive_path)

        try:
            _atomic_replace_file(
                previous_file,
                targets[archive_path],
            )
        except Exception as exc:
            rollback_errors.append(f"{archive_path}: " f"{type(exc).__name__}")

    if rollback_errors:
        raise (
            DocumentationUpgradeOperationalError(
                "Documentation upgrade failed "
                "and rollback was incomplete: " + ", ".join(rollback_errors)
            )
        )


def apply_replacements(
    staging_directory: Path,
    targets: dict[str, Path],
    backup_directory: Path,
) -> None:
    replaced_files: list[str] = []

    try:
        for archive_path in sorted(targets):
            staged_file = staging_directory.joinpath(*PurePosixPath(archive_path).parts)
            target = targets[archive_path]

            _atomic_replace_file(
                staged_file,
                target,
            )
            replaced_files.append(archive_path)

        for archive_path in replaced_files:
            staged_file = staging_directory.joinpath(*PurePosixPath(archive_path).parts)
            _copy_file(
                staged_file,
                backup_directory / "applied" / PurePosixPath(archive_path),
            )
    except Exception as exc:
        rollback_replacements(
            replaced_files,
            targets,
            backup_directory,
        )
        raise (
            DocumentationUpgradeOperationalError(
                "Documentation upgrade failed; " "replaced files were rolled back"
            )
        ) from exc


def cleanup_upgrade_input(
    zip_path: Path,
) -> None:
    try:
        zip_path.unlink()
    except OSError as exc:
        raise (
            DocumentationUpgradeOperationalError(
                "Upgrade applied but input ZIP " "could not be removed"
            )
        ) from exc


def upgrade_documentation(
    input_directory: str = (DOCUMENTATION_UPGRADE_INPUT_DIRECTORY),
    documentation_root: str = (DOCUMENTATION_UPGRADE_DOCUMENTATION_ROOT),
    backup_root: str = (DOCUMENTATION_UPGRADE_BACKUP_ROOT),
    now: Callable[[], datetime] = (datetime.now),
) -> DocumentationUpgradeResponse:
    input_path = resolve_existing_directory(
        input_directory,
        "documentation_upgrade_input_directory",
    )
    resolved_documentation_root = resolve_existing_directory(
        documentation_root,
        "documentation_upgrade_" "documentation_root",
    )
    backup_path = Path(backup_root).expanduser()

    if not backup_path.is_absolute() or ".." in backup_path.parts:
        raise ContextValidationError(
            "documentation_upgrade_backup_root " "must be an absolute safe path"
        )

    try:
        backup_path.mkdir(
            parents=True,
            exist_ok=True,
        )
        backup_path = backup_path.resolve(strict=True)
    except OSError as exc:
        raise (
            DocumentationUpgradeOperationalError(
                "Unable to create documentation " "upgrade backup root"
            )
        ) from exc

    zip_path = locate_upgrade_zip(input_path)

    with tempfile.TemporaryDirectory(
        prefix="documentation-upgrade-",
    ) as temporary_directory:
        staging_directory = Path(temporary_directory)

        if staging_directory.is_relative_to(input_path):
            raise (
                DocumentationUpgradeOperationalError(
                    "Staging directory must be " "outside input"
                )
            )

        manifest, actual_files = validate_and_stage_zip(
            zip_path,
            staging_directory,
        )
        (
            project_name,
            updated_files,
            targets,
        ) = validate_upgrade_manifest(
            manifest=manifest,
            actual_files=actual_files,
            staging_directory=(staging_directory),
            documentation_root=(resolved_documentation_root),
        )

        timestamp = now().strftime("%Y%m%d_%H%M%S_%f")
        backup_directory = create_upgrade_backup(
            staging_directory=(staging_directory),
            updated_files=updated_files,
            targets=targets,
            backup_root=backup_path,
            project_name=project_name,
            timestamp=timestamp,
        )
        apply_replacements(
            staging_directory=(staging_directory),
            targets=targets,
            backup_directory=(backup_directory),
        )
        cleanup_upgrade_input(zip_path)

    commit_message = backup_directory / "COMMIT_MESSAGE.md"
    executive_readme = backup_directory / "EXECUTIVE_README.md"

    return DocumentationUpgradeResponse(
        project_name=project_name,
        workflow=UPGRADE_WORKFLOW,
        updated_files=updated_files,
        backup_directory=str(backup_directory),
        commit_message_file=(str(commit_message) if commit_message.is_file() else ""),
        executive_readme_file=(
            str(executive_readme) if executive_readme.is_file() else ""
        ),
        input_cleaned=not zip_path.exists(),
        errors=[],
    )
