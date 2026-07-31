from dataclasses import dataclass
from pathlib import Path
import re
from typing import List, Tuple

from app.services.contexts.file_discovery_service import (
    ContextValidationError,
)
from app.services.documentation.models import DocumentationSource


EXCLUDED_DIRECTORY_NAMES = {
    "input",
    "output",
    "backups",
    "__pycache__",
}


FORMAT_CONTEXT_FILENAME = "FORMAT_CONTEXT.md"
SYSTEM_PROMPT_FILENAME = "SYS_PROMPT.md"


@dataclass(frozen=True)
class ValidatedDocumentationExportPaths:
    project_root: Path
    documentation_root: Path
    format_context_path: Path
    system_prompt_path: Path
    output_directory: Path


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


def _reject_traversal(
    value: str,
    field_name: str,
) -> Path:
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
    path = _reject_traversal(
        value,
        field_name,
    )

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
    path = _reject_traversal(
        value,
        field_name,
    )

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

    if not resolved.is_relative_to(
        allowed_root
    ):
        raise ContextValidationError(
            f"{field_name} must be inside documentation_root"
        )

    return resolved


def resolve_documentation_export_paths(
    project_name: str,
    project_root: str,
    documentation_root: str,
    format_context_path: str,
    system_prompt_path: str,
    output_directory: str,
) -> Tuple[
    str,
    ValidatedDocumentationExportPaths,
]:
    safe_project_name = _validate_project_name(
        project_name
    )
    resolved_project_root = (
        _resolve_existing_directory(
            project_root,
            "project_root",
        )
    )
    resolved_documentation_root = (
        _resolve_existing_directory(
            documentation_root,
            "documentation_root",
        )
    )

    resolved_format_context = (
        _resolve_existing_file(
            format_context_path,
            "format_context_path",
            resolved_documentation_root,
        )
    )
    resolved_system_prompt = (
        _resolve_existing_file(
            system_prompt_path,
            "system_prompt_path",
            resolved_documentation_root,
        )
    )

    if resolved_format_context != (
        resolved_documentation_root
        / FORMAT_CONTEXT_FILENAME
    ).resolve():
        raise ContextValidationError(
            "format_context_path must point to "
            "documentation_root/FORMAT_CONTEXT.md"
        )

    if resolved_system_prompt != (
        resolved_documentation_root
        / SYSTEM_PROMPT_FILENAME
    ).resolve():
        raise ContextValidationError(
            "system_prompt_path must point to "
            "documentation_root/SYS_PROMPT.md"
        )

    output_path = _reject_traversal(
        output_directory,
        "output_directory",
    )

    try:
        output_path.mkdir(
            parents=True,
            exist_ok=True,
        )
        resolved_output = output_path.resolve(
            strict=True
        )
    except OSError as exc:
        raise ContextValidationError(
            "output_directory cannot be created or resolved"
        ) from exc

    if not resolved_output.is_dir():
        raise ContextValidationError(
            "output_directory must be a directory"
        )

    return (
        safe_project_name,
        ValidatedDocumentationExportPaths(
            project_root=resolved_project_root,
            documentation_root=(
                resolved_documentation_root
            ),
            format_context_path=(
                resolved_format_context
            ),
            system_prompt_path=(
                resolved_system_prompt
            ),
            output_directory=resolved_output,
        ),
    )


def _add_source(
    sources: List[DocumentationSource],
    errors: List[str],
    source_path: Path,
    allowed_root: Path,
    archive_path: str,
    documentation_type: str,
) -> None:
    if (
        not source_path.is_absolute()
        or not source_path.is_relative_to(
            allowed_root
        )
    ):
        raise ContextValidationError(
            "Documentation source must be inside "
            "documentation_root"
        )

    relative_path = source_path.relative_to(
        allowed_root
    )
    current_path = allowed_root

    for path_part in relative_path.parts:
        current_path = (
            current_path / path_part
        )

        if current_path.is_symlink():
            raise ContextValidationError(
                "Symlinks are not allowed for "
                f"documentation files: {archive_path}"
            )

    if not source_path.is_file():
        errors.append(
            "Missing allowed documentation file: "
            f"{archive_path}"
        )
        return

    sources.append(
        DocumentationSource(
            source_path=source_path,
            archive_path=archive_path,
            documentation_type=(
                documentation_type
            ),
            repository="SBM-SUITE",
            legacy_source_path=None,
        )
    )


def _is_excluded_documentation_path(
    relative_path: Path,
) -> bool:
    return any(
        part in EXCLUDED_DIRECTORY_NAMES
        or part.startswith(".")
        for part in relative_path.parts[:-1]
    )


def _documentation_type(
    relative_path: Path,
) -> str:
    if len(relative_path.parts) > 1:
        return relative_path.parts[0]

    return relative_path.stem


def discover_documentation_sources(
    project_name: str,
    paths: ValidatedDocumentationExportPaths,
) -> Tuple[
    List[DocumentationSource],
    List[str],
]:
    del project_name

    sources: List[DocumentationSource] = []
    errors: List[str] = []

    documentation_files = sorted(
        paths.documentation_root.rglob("*.md"),
        key=lambda path: path.relative_to(
            paths.documentation_root
        ).as_posix().casefold(),
    )

    protected_paths = {
        paths.format_context_path,
        paths.system_prompt_path,
    }

    for source_path in documentation_files:
        resolved_source = source_path.resolve()

        if resolved_source in protected_paths:
            continue

        relative_path = resolved_source.relative_to(
            paths.documentation_root
        )

        if _is_excluded_documentation_path(
            relative_path
        ):
            continue

        _add_source(
            sources=sources,
            errors=errors,
            source_path=resolved_source,
            allowed_root=paths.documentation_root,
            archive_path=(
                "documentation/"
                f"{relative_path.as_posix()}"
            ),
            documentation_type=(
                _documentation_type(relative_path)
            ),
        )

    _add_source(
        sources=sources,
        errors=errors,
        source_path=paths.format_context_path,
        allowed_root=paths.documentation_root,
        archive_path=FORMAT_CONTEXT_FILENAME,
        documentation_type="format-context",
    )
    _add_source(
        sources=sources,
        errors=errors,
        source_path=paths.system_prompt_path,
        allowed_root=paths.documentation_root,
        archive_path=SYSTEM_PROMPT_FILENAME,
        documentation_type="system-prompt",
    )

    if len(sources) == 2:
        raise ContextValidationError(
            "No documentation page or subpage Markdown files "
            "were found"
        )

    return sources, errors
