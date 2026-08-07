from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

from app.config.settings import DOCUMENTATION_EXPORT_TOP_K
from app.schemas.documentation import (
    DocumentationExportRequest,
    DocumentationExportResponse,
)

from app.services.contexts.context_retrieval_service import (
    retrieve_relevant_context_chunks,
)
from app.services.contexts.file_discovery_service import (
    ContextValidationError,
)
from app.services.contexts.models import RetrievedContextChunk
from app.services.documentation.documentation_index_service import (
    DOCUMENTATION_COLLECTION_NAME,
    index_documentation_source,
)
from app.services.documentation.documentation_retrieval_service import (
    build_documentation_query,
    retrieve_relevant_documentation_chunks,
)
from app.services.documentation.file_discovery_service import (
    discover_documentation_sources,
    resolve_documentation_export_paths,
)
from app.services.documentation.markdown_chunk_service import (
    split_documentation_markdown,
)
from app.services.documentation.models import DocumentationFile
from app.services.documentation.zip_export_service import (
    create_documentation_package,
)


logger = logging.getLogger("uvicorn.error.documentation_export.service")
logger.setLevel(logging.INFO)

GIT_COMMAND_TIMEOUT_SECONDS = 10
PROJECT_TREE_FILENAME = "project-tree.txt"
MAX_PROJECT_TREE_BYTES = 2 * 1024 * 1024
PROJECT_NAME_TEMPLATE = "{{PROJECT_NAME}}"
UNRESOLVED_TEMPLATE_PATTERN = re.compile(r"{{[A-Z0-9_]+}}")


class DocumentationExportInfrastructureError(RuntimeError):
    pass


def _run_git(
    project_root: Path,
    arguments: list[str],
) -> str:
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(project_root),
                *arguments,
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_COMMAND_TIMEOUT_SECONDS,
        )
    except (
        OSError,
        subprocess.SubprocessError,
    ):
        return ""

    if result.returncode != 0:
        return ""

    return result.stdout.strip()


def _is_safe_relative_path(path: str) -> bool:
    candidate = Path(path)

    if candidate.is_absolute() or ".." in candidate.parts:
        return False

    return not any(
        part == ".env" or part.startswith(".env.") for part in candidate.parts
    )


def _collect_changed_files(
    project_root: Path,
) -> list[str]:
    tracked = _run_git(
        project_root,
        [
            "diff",
            "--name-only",
            "HEAD",
            "--",
        ],
    ).splitlines()
    untracked = _run_git(
        project_root,
        [
            "ls-files",
            "--others",
            "--exclude-standard",
        ],
    ).splitlines()

    return sorted(
        {
            path.strip()
            for path in [
                *tracked,
                *untracked,
            ]
            if (path.strip() and _is_safe_relative_path(path.strip()))
        }
    )


def _collect_git_diff(
    project_root: Path,
    changed_files: list[str],
) -> str:
    if not changed_files:
        return ""

    return _run_git(
        project_root,
        [
            "diff",
            "--no-ext-diff",
            "HEAD",
            "--",
            *changed_files,
        ],
    )


def _collect_git_log(
    project_root: Path,
) -> str:
    return _run_git(
        project_root,
        [
            "log",
            "--max-count=20",
            "--date=iso-strict",
            "--pretty=format:%h %ad %s",
        ],
    )


def _collect_project_tree(
    project_root: Path,
) -> str:
    project_tree_path = project_root / PROJECT_TREE_FILENAME

    if not project_tree_path.exists():
        return ""

    if not project_tree_path.is_file() or project_tree_path.is_symlink():
        raise ContextValidationError(
            f"{PROJECT_TREE_FILENAME} must be " "a regular file"
        )

    try:
        size = project_tree_path.stat().st_size
    except OSError as exc:
        raise ContextValidationError(
            f"Unable to inspect " f"{PROJECT_TREE_FILENAME}"
        ) from exc

    if size > MAX_PROJECT_TREE_BYTES:
        raise ContextValidationError(
            f"{PROJECT_TREE_FILENAME} exceeds " f"{MAX_PROJECT_TREE_BYTES} bytes"
        )

    try:
        return project_tree_path.read_text(encoding="utf-8").strip()
    except (
        OSError,
        UnicodeError,
    ) as exc:
        raise ContextValidationError(
            f"Unable to read " f"{PROJECT_TREE_FILENAME} as UTF-8"
        ) from exc


def _read_documentation_file(
    source_path: Path,
    archive_path: str,
) -> str:
    try:
        return source_path.read_text(encoding="utf-8")
    except (
        OSError,
        UnicodeError,
    ) as exc:
        raise ContextValidationError(
            "Unable to read authorized "
            "documentation Markdown as UTF-8: "
            f"{archive_path}"
        ) from exc


def _normalize_requested_paths(
    paths: list[str],
) -> list[str]:
    normalized = sorted(
        {
            path.strip()
            for path in paths
            if (path and path.strip() and _is_safe_relative_path(path.strip()))
        }
    )

    if len(normalized) != len(
        {path.strip() for path in paths if path and path.strip()}
    ):
        raise ContextValidationError(
            "Documentation paths must be " "unique safe relative paths"
        )

    return normalized



def _validate_workflow_contracts(
    format_context_path: Path,
    system_prompt_path: Path,
    project_name: str,
) -> None:
    for path, label in (
        (format_context_path, "FORMAT_CONTEXT.md"),
        (system_prompt_path, "SYS_PROMPT.md"),
    ):
        if path.is_symlink() or not path.is_file():
            raise ContextValidationError(
                f"{label} must be an existing regular file"
            )

    try:
        format_context = format_context_path.read_text(encoding="utf-8")
        system_prompt = system_prompt_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ContextValidationError(
            "Documentation workflow contracts must be readable UTF-8 files"
        ) from exc

    if not format_context.strip():
        raise ContextValidationError("FORMAT_CONTEXT.md must not be empty")
    if not system_prompt.strip():
        raise ContextValidationError("SYS_PROMPT.md must not be empty")
    if PROJECT_NAME_TEMPLATE not in system_prompt:
        raise ContextValidationError(
            "SYS_PROMPT.md must contain {{PROJECT_NAME}}"
        )

    rendered_prompt = system_prompt.replace(
        PROJECT_NAME_TEMPLATE,
        project_name,
    )
    unresolved_tokens = sorted(
        set(UNRESOLVED_TEMPLATE_PATTERN.findall(rendered_prompt))
    )
    if unresolved_tokens:
        raise ContextValidationError(
            "SYS_PROMPT.md contains unresolved template tokens after rendering: "
            + ", ".join(unresolved_tokens)
        )


def export_documentation(
    request: DocumentationExportRequest,
) -> DocumentationExportResponse:
    project_name, paths = resolve_documentation_export_paths(
        project_name=request.project_name,
        project_root=request.project_root,
        documentation_root=(request.documentation_root),
        format_context_path=(request.format_context_path),
        system_prompt_path=(request.system_prompt_path),
        output_directory=(request.output_directory),
    )

    _validate_workflow_contracts(
        format_context_path=paths.format_context_path,
        system_prompt_path=paths.system_prompt_path,
        project_name=project_name,
    )

    logger.info(
        "[DOCUMENTATION_EXPORT] discovery start " "project=%s",
        project_name,
    )

    sources, errors = discover_documentation_sources(
        project_name=project_name,
        paths=paths,
    )

    logger.info(
        "[DOCUMENTATION_EXPORT] discovery complete " "project=%s sources=%d errors=%d",
        project_name,
        len(sources),
        len(errors),
    )

    if not sources:
        raise ContextValidationError(
            "No authorized documentation files " "were discovered"
        )

    documentation_files: list[DocumentationFile] = []
    chunks_by_source = []

    for source in sources:
        markdown = _read_documentation_file(
            source.source_path,
            source.archive_path,
        )
        chunks = split_documentation_markdown(
            text=markdown,
            default_section=(source.source_path.name),
        )

        documentation_files.append(
            DocumentationFile(
                source_path=source.source_path,
                archive_path=(source.archive_path),
                content=markdown,
            )
        )
        chunks_by_source.append(
            (
                source,
                markdown,
                chunks,
            )
        )

    if not any(chunks for _, _, chunks in chunks_by_source):
        raise ContextValidationError(
            "Authorized documentation files " "contain no indexable content"
        )

    indexed_source_count = 0
    chunk_count = 0

    try:
        for (
            source,
            markdown,
            chunks,
        ) in chunks_by_source:
            indexed_chunks = index_documentation_source(
                source=source,
                markdown=markdown,
                chunks=chunks,
                project_name=project_name,
            )
            chunk_count += indexed_chunks

            if indexed_chunks:
                indexed_source_count += 1
    except Exception as exc:
        logger.exception(
            "Documentation indexing failed " "for project=%s",
            project_name,
        )
        raise (
            DocumentationExportInfrastructureError("Documentation indexing failed")
        ) from exc

    try:
        requested_changed_files = (
            request.changed_files
            if request.changed_files is not None
            else _collect_changed_files(paths.project_root)
        )
        changed_files = _normalize_requested_paths(requested_changed_files)

        git_diff = (
            request.git_diff
            if request.git_diff is not None
            else _collect_git_diff(
                paths.project_root,
                changed_files,
            )
        )
        git_log = _collect_git_log(paths.project_root)
        qa_results = request.qa_results or ""
        change_summary = request.change_summary or ""
        project_tree = _collect_project_tree(paths.project_root)

        documentation_paths = sorted({source.archive_path for source in sources})

        query = build_documentation_query(
            project_name=project_name,
            change_summary=change_summary,
            changed_files=changed_files,
            git_diff=git_diff,
            qa_results=qa_results,
            documentation_files=(documentation_paths),
            project_tree=project_tree,
        )

        logger.info(
            "[DOCUMENTATION_EXPORT] retrieval start " "project=%s top_k=%d",
            project_name,
            DOCUMENTATION_EXPORT_TOP_K,
        )

        retrieved_documentation_chunks = retrieve_relevant_documentation_chunks(
            project_name=project_name,
            query=query,
            top_k=(DOCUMENTATION_EXPORT_TOP_K),
            allowed_archive_paths=documentation_paths,
        )

        # Usa los contextos enviados o los recupera desde sbm_contexts
        if request.retrieved_context_chunks:
            retrieved_context_chunks = request.retrieved_context_chunks
        else:
            retrieved_context_chunks = retrieve_relevant_context_chunks(
                project_name=project_name,
                query=query,
                top_k=DOCUMENTATION_EXPORT_TOP_K,
            )

        logger.info(
            "[DOCUMENTATION_EXPORT] retrieval complete "
            "project=%s documentation_chunks=%d "
            "context_chunks=%d",
            project_name,
            len(retrieved_documentation_chunks),
            len(retrieved_context_chunks),
        )
    except Exception as exc:
        logger.exception(
            "Documentation retrieval failed " "for project=%s",
            project_name,
        )
        raise (
            DocumentationExportInfrastructureError("Documentation retrieval failed")
        ) from exc

    try:
        documentation_zip_path = create_documentation_package(
            output_directory=(paths.output_directory),
            project_name=project_name,
            query=query,
            retrieved_documentation_chunks=(retrieved_documentation_chunks),
            retrieved_context_chunks=(retrieved_context_chunks),
            documentation_files=(documentation_files),
            change_summary=change_summary,
            changed_files=changed_files,
            git_diff=git_diff,
            git_log=git_log,
            qa_results=qa_results,
            project_tree=project_tree,
            top_k=(DOCUMENTATION_EXPORT_TOP_K),
            format_context_path=(paths.format_context_path),
            system_prompt_path=(paths.system_prompt_path),
            errors=errors,
        )
    except Exception as exc:
        logger.exception(
            "Documentation ZIP creation failed " "for project=%s",
            project_name,
        )
        raise (
            DocumentationExportInfrastructureError("Documentation ZIP creation failed")
        ) from exc

    return DocumentationExportResponse(
        status="completed",
        project_name=project_name,
        workflow="documentation-deploy",
        documentation_zip_path=str(documentation_zip_path),
        indexed_source_count=(indexed_source_count),
        chunk_count=chunk_count,
        collection_name=(DOCUMENTATION_COLLECTION_NAME),
        errors=errors,
    )
