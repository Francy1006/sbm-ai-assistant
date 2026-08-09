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
    DOCUMENTATION_UPGRADE_BACKUP_ROOT,
    DOCUMENTATION_UPGRADE_DOCUMENTATION_ROOT,
    DOCUMENTATION_UPGRADE_INPUT_ROOT,
)
from app.schemas.documentation import DocumentationUpgradeResponse
from app.services.contexts.context_index_service import content_hash
from app.services.contexts.file_discovery_service import (
    ContextValidationError,
    resolve_existing_directory,
)
from app.services.project_registry import (
    ProjectRegistryError,
    get_project_location,
)


UPGRADE_ZIP_NAME = "documentation-upgrade.zip"
UPGRADE_WORKFLOW = "documentation-upgrade"
DOCUMENTATION_ROOT_NAME = "documentation"
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
PROTECTED_DOCUMENTATION_PATHS = frozenset(
    {
        "documentation/FORMAT_CONTEXT.md",
        "documentation/SYS_PROMPT.md",
    }
)

MAIN_PAGE_HEADINGS = [
    "## 1. Overview",
    "## 2. Scope",
    "## 3. Current state",
    "## 4. Core concepts",
    "## 5. Architecture or operating model",
    "## 6. Components",
    "## 7. Workflows",
    "## 8. Configuration",
    "## 9. Security",
    "## 10. Validation",
    "## 11. Known limitations",
    "## 12. Roadmap",
    "## 13. Related pages",
    "## 14. Subpages",
    "## 15. Document boundary",
]

SUBPAGE_HEADINGS = [
    "## 1. Overview",
    "## 2. Scope",
    "## 3. Current state",
    "## 4. Detailed design or procedure",
    "## 5. Inputs and prerequisites",
    "## 6. Execution or usage",
    "## 7. Outputs and evidence",
    "## 8. Security considerations",
    "## 9. Validation",
    "## 10. Known limitations",
    "## 11. Pending work",
    "## 12. Related documentation",
    "## 13. Parent page",
    "## 14. Document boundary",
]


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


def _metadata_value(
    lines: list[str],
    marker_index: int,
    marker: str,
    archive_path: str,
) -> str:
    index = marker_index + 1

    while index < len(lines) and not lines[index].strip():
        index += 1

    while index < len(lines) and lines[index].strip() == ">":
        index += 1

    if index >= len(lines):
        raise ContextValidationError(
            f"Documentation metadata has no value after {marker!r}: "
            f"{archive_path}"
        )

    value = lines[index].strip()

    if not value.startswith(">"):
        raise ContextValidationError(
            f"Documentation metadata value must be a blockquote after "
            f"{marker!r}: {archive_path}"
        )

    value = value[1:].strip()

    if not value:
        raise ContextValidationError(
            f"Documentation metadata has an empty value after {marker!r}: "
            f"{archive_path}"
        )

    return value


def _validate_markdown_structure(
    markdown: str,
    archive_path: str,
) -> None:
    lines = markdown.splitlines()

    if not lines or not re.fullmatch(r"#\s+.+", lines[0].strip()):
        raise ContextValidationError(
            "Documentation file must begin with exactly one level-one heading: "
            f"{archive_path}"
        )

    headings = [
        line.strip()
        for line in lines
        if re.fullmatch(r"#{1,6}\s+.+", line.strip())
    ]

    level_one_headings = [
        heading for heading in headings if heading.startswith("# ")
    ]

    if len(level_one_headings) != 1:
        raise ContextValidationError(
            "Documentation file must contain exactly one level-one heading: "
            f"{archive_path}"
        )

    is_subpage = "/subpages/" in archive_path
    last_updated_positions = [
        index
        for index, line in enumerate(lines)
        if re.fullmatch(
            r"> \*\*Last updated:\*\* \d{4}-\d{2}-\d{2}",
            line.strip(),
        )
    ]

    if len(last_updated_positions) != 1:
        raise ContextValidationError(
            "Documentation metadata must contain exactly one "
            f"'> **Last updated:** YYYY-MM-DD': {archive_path}"
        )

    required_metadata = [
        *(["> **Parent page:**"] if is_subpage else []),
        "> **Purpose:**",
        "> **Source of truth:**",
    ]

    positions: list[int] = [last_updated_positions[0]]

    for marker in required_metadata:
        marker_positions = [
            index
            for index, line in enumerate(lines)
            if line.strip() == marker
        ]

        if len(marker_positions) != 1:
            raise ContextValidationError(
                f"Documentation metadata must contain exactly one {marker!r}: "
                f"{archive_path}"
            )

        positions.append(marker_positions[0])

    if positions != sorted(positions):
        raise ContextValidationError(
            "Documentation metadata labels are out of order: "
            f"{archive_path}"
        )

    forbidden_variants = (
        "> **Last updated**",
        "> **Purpose**",
        "> **Source of truth**",
        "> **Parent page**",
    )

    for marker in forbidden_variants:
        if any(line.strip() == marker for line in lines):
            raise ContextValidationError(
                "Documentation metadata label is missing final colon "
                f"{marker!r}: {archive_path}"
            )

    for marker, marker_index in zip(required_metadata, positions[1:]):
        value = _metadata_value(
            lines,
            marker_index,
            marker,
            archive_path,
        )

        if marker == "> **Parent page:**":
            if not re.fullmatch(r"`[^`]+`", value):
                raise ContextValidationError(
                    "Documentation Parent page value must be one "
                    f"repository-relative path in backticks: {archive_path}"
                )

            parent_path = value[1:-1]

            if (
                parent_path.startswith("/")
                or ".." in PurePosixPath(parent_path).parts
                or not parent_path.endswith(".md")
            ):
                raise ContextValidationError(
                    f"Invalid documentation Parent page path: {archive_path}"
                )

    actual_h2_headings = [
        heading for heading in headings if heading.startswith("## ")
    ]
    expected_h2_headings = (
        SUBPAGE_HEADINGS if is_subpage else MAIN_PAGE_HEADINGS
    )

    if actual_h2_headings != expected_h2_headings:
        raise ContextValidationError(
            "Documentation level-two headings do not match FORMAT_CONTEXT.md: "
            f"{archive_path}"
        )

    if is_subpage:
        parent_heading_index = lines.index("## 13. Parent page")
        parent_section = lines[parent_heading_index + 1 :]

        next_h2_index = next(
            (
                index
                for index, line in enumerate(parent_section)
                if line.strip().startswith("## ")
            ),
            len(parent_section),
        )
        parent_section = parent_section[:next_h2_index]

        return_links = [
            line.strip()
            for line in parent_section
            if re.fullmatch(r"\[Return to .+\]\(.+\.md\)", line.strip())
        ]

        if len(return_links) != 1:
            raise ContextValidationError(
                "Documentation subpage must contain exactly one parent return link: "
                f"{archive_path}"
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
    try:
        project_name = get_project_location(project_name).project_name
    except ProjectRegistryError as exc:
        raise ContextValidationError(str(exc)) from exc

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

    missing_required_files = REQUIRED_ROOT_FILES - actual_files
    if missing_required_files:
        raise ContextValidationError(
            "ZIP is missing required files: "
            + ", ".join(sorted(missing_required_files))
        )

    if "manifest.json" not in declared_allowlist:
        raise ContextValidationError(
            "manifest.allowed_files must include manifest.json"
        )

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
    missing_declared_files = declared_allowlist - actual_files

    if missing_declared_files:
        raise ContextValidationError(
            "manifest.allowed_files contains files absent from ZIP: "
            + ", ".join(sorted(missing_declared_files))
        )

    if undeclared_files:
        raise ContextValidationError(
            "ZIP contains files absent from "
            "manifest.allowed_files: " + ", ".join(sorted(undeclared_files))
        )

    if not set(updated_files).issubset(declared_allowlist):
        raise ContextValidationError(
            "manifest.updated_files must be a subset of manifest.allowed_files"
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

    for archive_path, digest in content_hashes.items():
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ContextValidationError(
                f"manifest.content_hashes contains invalid SHA-256 for {archive_path}"
            )

    commit_type = commit_metadata.get("type")
    commit_scope = commit_metadata.get("scope")
    commit_subject = commit_metadata.get("subject")
    commit_message_file = commit_metadata.get("message_file")

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

    if commit_type not in {"docs", "chore", "refactor", "fix", "feat"}:
        raise ContextValidationError(
            f"Unsupported manifest.commit.type: {commit_type}"
        )

    commit_message = _read_utf8_file(
        staging_directory / "COMMIT_MESSAGE.md",
        "COMMIT_MESSAGE.md",
    )
    first_line = next(
        (line.strip() for line in commit_message.splitlines() if line.strip()),
        "",
    )
    expected_commit = f"{commit_type}({commit_scope}): {commit_subject}"
    if first_line != expected_commit:
        raise ContextValidationError(
            "manifest.commit metadata does not match COMMIT_MESSAGE.md"
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
        project_name,
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
    generated_at: str,
    reason: str,
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
            previous_path = (
                backup_directory / "previous" / PurePosixPath(archive_path)
            )
            _copy_file(
                target,
                previous_path,
            )

        backed_up_files = []
        sha256_by_file = {}
        for archive_path, target in sorted(targets.items()):
            previous_path = (
                backup_directory / "previous" / PurePosixPath(archive_path)
            )
            original_hash = content_hash(
                _read_utf8_file(target, archive_path)
            )
            sha256_by_file[archive_path] = original_hash
            backed_up_files.append(
                {
                    "archive_path": archive_path,
                    "original_path": archive_path,
                    "backup_path": (
                        PurePosixPath("previous") / PurePosixPath(archive_path)
                    ).as_posix(),
                    "sha256": original_hash,
                }
            )

        backup_manifest = {
            "project_name": project_name,
            "workflow": UPGRADE_WORKFLOW,
            "generated_at": generated_at,
            "reason": reason,
            "original_path": [item["original_path"] for item in backed_up_files],
            "backup_path": (
                PurePosixPath("context/backup") / backup_directory.name
            ).as_posix(),
            "sha256": sha256_by_file,
            "backed_up_files": backed_up_files,
        }
        (backup_directory / "BACKUP_MANIFEST.json").write_text(
            json.dumps(backup_manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
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

            replaced_files.append(archive_path)
            _atomic_replace_file(
                staged_file,
                target,
            )

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
    input_directory: str = (DOCUMENTATION_UPGRADE_INPUT_ROOT),
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
    if input_path != (resolved_documentation_root / "input").resolve():
        raise ContextValidationError(
            "documentation upgrade input must be documentation_root/input"
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
    if backup_path != (resolved_documentation_root.parent / "backup").resolve():
        raise ContextValidationError(
            "documentation upgrade backup must resolve to context/backup"
        )

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

        generated_at = now()
        timestamp = generated_at.strftime("%Y%m%d_%H%M%S_%f")
        backup_directory = create_upgrade_backup(
            staging_directory=(staging_directory),
            updated_files=updated_files,
            targets=targets,
            backup_root=backup_path,
            project_name=project_name,
            timestamp=timestamp,
            generated_at=generated_at.isoformat(),
            reason=f"Apply validated documentation update for {project_name}",
        )
        apply_replacements(
            staging_directory=(staging_directory),
            targets=targets,
            backup_directory=(backup_directory),
        )
        cleanup_upgrade_input(zip_path)

    commit_message = backup_directory / "COMMIT_MESSAGE.md"
    executive_readme = backup_directory / "EXECUTIVE_README.md"
    suite_root = resolved_documentation_root.parent.parent

    def relative_output_path(path: Path) -> str:
        return path.relative_to(suite_root).as_posix()

    return DocumentationUpgradeResponse(
        project_name=project_name,
        workflow=UPGRADE_WORKFLOW,
        updated_files=updated_files,
        backup_directory=relative_output_path(backup_directory),
        commit_message_file=(
            relative_output_path(commit_message)
            if commit_message.is_file()
            else ""
        ),
        executive_readme_file=(
            relative_output_path(executive_readme)
            if executive_readme.is_file()
            else ""
        ),
        input_cleaned=not zip_path.exists(),
        errors=[],
    )
