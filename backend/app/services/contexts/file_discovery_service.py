from dataclasses import dataclass
from pathlib import Path
import re

from app.services.contexts.models import ContextSource
from app.services.project_registry import (
    ProjectRegistryError,
    get_project_location,
)


GLOBAL_CONTEXT_FILES = (
    (
        "context/PROJECT_CONTEXT.md",
        "context/PROJECT_CONTEXT.md",
        "project_context",
        "PROJECT_CONTEXT.md",
    ),
    (
        "context/README.md",
        "context/README.md",
        "suite_readme",
        "README.md",
    ),
    (
        "context/COMPLETED_OBJECTIVES.md",
        "context/COMPLETED_OBJECTIVES.md",
        "completed_objectives",
        "COMPLETED_OBJECTIVES.md",
    ),
    (
        "context/SUITE_CONTEXT.md",
        "context/SUITE_CONTEXT.md",
        "suite_context",
        "context/SUITE_CONTEXT.md",
    ),
    (
        "context/BUSINESS_CONTEXT.md",
        "context/BUSINESS_CONTEXT.md",
        "business_context",
        "context/BUSINESS_CONTEXT.md",
    ),
    (
        "context/QA_CONTEXT.md",
        "context/QA_CONTEXT.md",
        "qa_context",
        "context/QA_CONTEXT.md",
    ),
    (
        "context/SECURITY_CONTEXT.md",
        "context/SECURITY_CONTEXT.md",
        "security_context",
        "context/SECURITY_CONTEXT.md",
    ),
    (
        "context/DATA_CONTEXT.md",
        "context/DATA_CONTEXT.md",
        "data_context",
        "context/DATA_CONTEXT.md",
    ),
    (
        "context/DECISIONS_CONTEXT.md",
        "context/DECISIONS_CONTEXT.md",
        "decisions_context",
        "context/DECISIONS_CONTEXT.md",
    ),
    (
        "context/SYS_PROMPT.md",
        "context/SYS_PROMPT.md",
        "system_prompt",
        "context/SYS_PROMPT.md",
    ),
    (
        "context/FORMAT_CONTEXT.md",
        "context/FORMAT_CONTEXT.md",
        "format_context",
        "context/FORMAT_CONTEXT.md",
    ),
)

PROJECT_CONTEXT_FILES = (
    ("README.md", "project_readme"),
    ("context/PROJECT_CONTEXT.md", "project_context"),
    ("context/QA_CONTEXT.md", "qa_context"),
    ("context/DEPLOY_CONTEXT.md", "deploy_context"),
)

FULL_CONTEXT_FILE_MAPPINGS = (
    (
        "global",
        "context/PROJECT_CONTEXT.md",
        "SBM-SUITE/context/PROJECT_CONTEXT.md",
    ),
    (
        "global",
        "context/README.md",
        "SBM-SUITE/context/README.md",
    ),
    (
        "global",
        "context/SUITE_CONTEXT.md",
        "SBM-SUITE/context/SUITE_CONTEXT.md",
    ),
    (
        "global",
        "context/COMPLETED_OBJECTIVES.md",
        "SBM-SUITE/context/COMPLETED_OBJECTIVES.md",
    ),
    (
        "global",
        "context/QA_CONTEXT.md",
        "SBM-SUITE/context/QA_CONTEXT.md",
    ),
    (
        "global",
        "context/BUSINESS_CONTEXT.md",
        "SBM-SUITE/context/BUSINESS_CONTEXT.md",
    ),
    (
        "global",
        "context/SECURITY_CONTEXT.md",
        "SBM-SUITE/context/SECURITY_CONTEXT.md",
    ),
    (
        "global",
        "context/DATA_CONTEXT.md",
        "SBM-SUITE/context/DATA_CONTEXT.md",
    ),
    (
        "global",
        "context/DECISIONS_CONTEXT.md",
        "SBM-SUITE/context/DECISIONS_CONTEXT.md",
    ),
    (
        "global",
        "context/FORMAT_CONTEXT.md",
        "FORMAT_CONTEXT.md",
    ),
    (
        "project",
        "context/PROJECT_CONTEXT.md",
        "SBM-SUITE/{project_relative_root}/context/PROJECT_CONTEXT.md",
    ),
    (
        "project",
        "README.md",
        "SBM-SUITE/{project_relative_root}/README.md",
    ),
    (
        "project",
        "context/QA_CONTEXT.md",
        "SBM-SUITE/{project_relative_root}/context/QA_CONTEXT.md",
    ),
    (
        "project",
        "context/DEPLOY_CONTEXT.md",
        "SBM-SUITE/{project_relative_root}/context/DEPLOY_CONTEXT.md",
    ),
)


class ContextValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ValidatedExportPaths:
    project_root: Path
    source_context_root: Path
    format_context_path: Path
    output_directory: Path


def _reject_traversal(value: str, field_name: str) -> Path:
    path = Path(value).expanduser()

    if not path.is_absolute():
        raise ContextValidationError(
            f"{field_name} must be an absolute path"
        )

    if ".." in path.parts:
        raise ContextValidationError(
            f"{field_name} must not contain path traversal segments"
        )

    return path


def _resolve_existing_directory(
    value: str,
    field_name: str,
) -> Path:
    path = _reject_traversal(value, field_name)

    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ContextValidationError(
            f"{field_name} does not exist or cannot be resolved"
        ) from exc

    if not resolved.is_dir():
        raise ContextValidationError(
            f"{field_name} must be a directory"
        )

    return resolved


def _resolve_existing_file(
    value: str,
    field_name: str,
    allowed_root: Path,
) -> Path:
    path = _reject_traversal(value, field_name)

    if path.is_symlink():
        raise ContextValidationError(
            f"{field_name} must not be a symlink"
        )

    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ContextValidationError(
            f"{field_name} does not exist or cannot be resolved"
        ) from exc

    if not resolved.is_file():
        raise ContextValidationError(
            f"{field_name} must be a file"
        )

    if not resolved.is_relative_to(allowed_root):
        raise ContextValidationError(
            f"{field_name} must be inside source_context_root"
        )

    return resolved


def _validate_project_name(project_name: str) -> str:
    normalized = project_name.strip()

    if not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._-]*",
        normalized,
    ):
        raise ContextValidationError(
            "project_name must be a single safe path segment"
        )

    return normalized


def resolve_existing_directory(
    value: str,
    field_name: str,
) -> Path:
    return _resolve_existing_directory(value, field_name)


def validate_project_name(project_name: str) -> str:
    return _validate_project_name(project_name)


def validate_export_paths(
    project_name: str,
    project_root: str,
    source_context_root: str,
    format_context_path: str,
    output_directory: str,
) -> tuple[str, ValidatedExportPaths]:
    safe_project_name = _validate_project_name(project_name)
    try:
        location = get_project_location(safe_project_name)
    except ProjectRegistryError as exc:
        raise ContextValidationError(str(exc)) from exc
    safe_project_name = location.project_name

    requested_context_root = _resolve_existing_directory(
        source_context_root,
        "source_context_root",
    )

    context_root = (
        requested_context_root
        if requested_context_root.name == "context"
        else requested_context_root / "context"
    )
    if not context_root.is_dir():
        raise ContextValidationError(
            "source_context_root must be /suite/context or its suite parent"
        )
    source_root = context_root.parent

    resolved_project_root = _resolve_existing_directory(
        project_root,
        "project_root",
    )

    suite_root = context_root.parent
    expected_project_root = suite_root / location.relative_root
    if resolved_project_root != expected_project_root.absolute():
        raise ContextValidationError(
            "project_root does not match the project allowlist"
        )
    try:
        expected_project_root = expected_project_root.resolve(strict=True)
    except OSError as exc:
        raise ContextValidationError(
            "allowlisted project_root does not exist"
        ) from exc

    if resolved_project_root != expected_project_root:
        raise ContextValidationError("project_root resolves outside the allowlist")

    resolved_format_context = _resolve_existing_file(
        format_context_path,
        "format_context_path",
        source_root,
    )

    expected_format_context = (context_root / "FORMAT_CONTEXT.md").resolve()

    if resolved_format_context != expected_format_context:
        raise ContextValidationError(
            "format_context_path must point to "
            "/suite/context/FORMAT_CONTEXT.md"
        )

    output_path = _reject_traversal(
        output_directory,
        "output_directory",
    )

    try:
        output_path.mkdir(parents=True, exist_ok=True)
        resolved_output = output_path.resolve(strict=True)
    except OSError as exc:
        raise ContextValidationError(
            "output_directory cannot be created or resolved"
        ) from exc

    if not resolved_output.is_dir():
        raise ContextValidationError(
            "output_directory must be a directory"
        )

    return safe_project_name, ValidatedExportPaths(
        project_root=resolved_project_root,
        source_context_root=source_root,
        format_context_path=resolved_format_context,
        output_directory=resolved_output,
    )


def _add_source(
    sources: list[ContextSource],
    errors: list[str],
    source_path: Path,
    allowed_root: Path,
    archive_path: str,
    context_type: str,
    repository: str,
    legacy_source_path: str,
):
    if (
        not source_path.is_absolute()
        or not source_path.is_relative_to(allowed_root)
    ):
        raise ContextValidationError(
            f"Context source path must be inside {allowed_root}"
        )

    relative_source_path = source_path.relative_to(allowed_root)
    current_path = allowed_root

    for path_part in relative_source_path.parts:
        current_path = current_path / path_part

        if current_path.is_symlink():
            raise ContextValidationError(
                "Symlinks are not allowed for context files: "
                f"{archive_path}"
            )

    if not source_path.is_file():
        errors.append(
            f"Missing allowed context file: {archive_path}"
        )
        return

    sources.append(
        ContextSource(
            source_path=source_path,
            archive_path=archive_path,
            context_type=context_type,
            repository=repository,
            legacy_source_path=legacy_source_path,
        )
    )


def discover_context_sources(
    project_name: str,
    paths: ValidatedExportPaths,
) -> tuple[list[ContextSource], list[str]]:
    sources: list[ContextSource] = []
    errors: list[str] = []

    for (
        source_relative_path,
        archive_relative_path,
        context_type,
        point_identity_path,
    ) in GLOBAL_CONTEXT_FILES:
        _add_source(
            sources=sources,
            errors=errors,
            source_path=(
                paths.source_context_root
                / source_relative_path
            ),
            allowed_root=paths.source_context_root,
            archive_path=(
                f"SBM-SUITE/{archive_relative_path}"
            ),
            context_type=context_type,
            repository="SBM-SUITE",
            legacy_source_path=point_identity_path,
        )

    project_relative_root = paths.project_root.relative_to(
        paths.source_context_root
    ).as_posix()

    for relative_path, context_type in PROJECT_CONTEXT_FILES:
        _add_source(
            sources=sources,
            errors=errors,
            source_path=paths.project_root / relative_path,
            allowed_root=paths.source_context_root,
            archive_path=(
                f"SBM-SUITE/{project_relative_root}/{relative_path}"
            ),
            context_type=context_type,
            repository=paths.project_root.name,
            legacy_source_path=(
                f"{project_relative_root}/{relative_path}"
            ),
        )

    if not sources:
        raise ContextValidationError(
            "No allowed Markdown context files were found"
        )

    return sources, errors


def resolve_full_context_sources(
    sources: list[ContextSource],
    project_name: str,
    paths: ValidatedExportPaths,
) -> tuple[list[ContextSource], list[str]]:
    sources_by_path = {
        source.source_path: source
        for source in sources
    }

    full_context_sources = []
    missing_archive_paths = []

    for scope, relative_path, archive_template in (
        FULL_CONTEXT_FILE_MAPPINGS
    ):
        root = (
            paths.source_context_root
            if scope == "global"
            else paths.project_root
        )

        source_path = root / relative_path

        project_relative_root = paths.project_root.relative_to(
            paths.source_context_root
        ).as_posix()

        archive_path = archive_template.format(
            project_name=project_name,
            project_relative_root=project_relative_root,
        )

        validated_source = sources_by_path.get(source_path)

        if validated_source is None:
            missing_archive_paths.append(archive_path)
            continue

        full_context_sources.append(
            ContextSource(
                source_path=validated_source.source_path,
                archive_path=archive_path,
                context_type=validated_source.context_type,
                repository=validated_source.repository,
                legacy_source_path=(
                    validated_source.legacy_source_path
                ),
            )
        )

    return full_context_sources, missing_archive_paths
