import logging
import subprocess
from pathlib import Path

from app.config.settings import (
    CONTEXT_EXPORT_TOP_K,
    CONTEXT_UPGRADE_SUITE_CONTEXT_ROOT,
)
from app.schemas.contexts import ContextExportRequest, ContextExportResponse
from app.services.contexts.context_index_service import (
    CONTEXT_COLLECTION_NAME,
    index_context_source,
)
from app.services.contexts.contract_registry import (
    PATCH_DEFINITIONS,
    build_contract_version,
    canonical_project_path,
    patch_target_file,
    supported_patch_paths_for_project,
    validate_format_context,
)
from app.services.contexts.context_retrieval_service import (
    build_context_query,
    retrieve_relevant_context_chunks,
)
from app.services.contexts.file_discovery_service import (
    ContextValidationError,
    discover_context_sources,
    resolve_full_context_sources,
    validate_export_paths,
)
from app.services.contexts.markdown_chunk_service import (
    split_markdown_into_chunks,
)
from app.services.contexts.models import FullContextFile
from app.services.contexts.zip_export_service import (
    create_context_package,
    create_context_upload_package,
)
from app.services.project_registry import (
    ProjectRegistryError,
    get_project_location,
)


logger = logging.getLogger("uvicorn.error.context_export.service")
logger.setLevel(logging.INFO)

GIT_COMMAND_TIMEOUT_SECONDS = 10
PROJECT_TREE_FILENAME = "project-tree.txt"
MAX_PROJECT_TREE_BYTES = 2 * 1024 * 1024


class ContextExportInfrastructureError(RuntimeError):
    pass


def _run_git(project_root: Path, arguments: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(project_root), *arguments],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_COMMAND_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return ""

    if result.returncode != 0:
        return ""

    return result.stdout.strip()


def _is_safe_changed_file(path: str) -> bool:
    candidate = Path(path)

    if candidate.is_absolute() or ".." in candidate.parts:
        return False

    return not any(
        part == ".env" or part.startswith(".env.")
        for part in candidate.parts
    )


def _collect_changed_files(project_root: Path) -> list[str]:
    tracked = _run_git(
        project_root,
        ["diff", "--name-only", "HEAD", "--"],
    ).splitlines()
    untracked = _run_git(
        project_root,
        ["ls-files", "--others", "--exclude-standard"],
    ).splitlines()

    return sorted(
        {
            path.strip()
            for path in [*tracked, *untracked]
            if path.strip() and _is_safe_changed_file(path.strip())
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
        ["diff", "--no-ext-diff", "HEAD", "--", *changed_files],
    )


def _collect_git_log(project_root: Path) -> str:
    return _run_git(
        project_root,
        [
            "log",
            "--max-count=20",
            "--date=iso-strict",
            "--pretty=format:%h %ad %s",
        ],
    )


def _collect_project_tree(source_context_root: Path) -> str:
    project_tree_path = (
        source_context_root / "context" / PROJECT_TREE_FILENAME
    )

    if not project_tree_path.exists():
        return ""

    if (
        not project_tree_path.is_file()
        or project_tree_path.is_symlink()
    ):
        raise ContextValidationError(
            f"{PROJECT_TREE_FILENAME} must be a regular file"
        )

    try:
        size = project_tree_path.stat().st_size
    except OSError as exc:
        raise ContextValidationError(
            f"Unable to inspect {PROJECT_TREE_FILENAME}"
        ) from exc

    if size > MAX_PROJECT_TREE_BYTES:
        raise ContextValidationError(
            f"{PROJECT_TREE_FILENAME} exceeds "
            f"{MAX_PROJECT_TREE_BYTES} bytes"
        )

    try:
        return project_tree_path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        raise ContextValidationError(
            f"Unable to read {PROJECT_TREE_FILENAME} as UTF-8"
        ) from exc


def export_contexts(
    request: ContextExportRequest,
) -> ContextExportResponse:
    try:
        location = get_project_location(request.project_name)
    except ProjectRegistryError as exc:
        raise ContextValidationError(str(exc)) from exc

    suite_context_root = Path(CONTEXT_UPGRADE_SUITE_CONTEXT_ROOT)
    suite_root = suite_context_root.parent
    project_name, paths = validate_export_paths(
        project_name=request.project_name,
        project_root=str(suite_root / location.relative_root),
        source_context_root=str(suite_root),
        format_context_path=str(suite_context_root / "FORMAT_CONTEXT.md"),
        output_directory=str(suite_context_root / "output"),
    )
    try:
        format_markdown = paths.format_context_path.read_text(encoding="utf-8")
        validate_format_context(format_markdown)
    except (OSError, UnicodeError, ValueError) as exc:
        raise ContextValidationError(
            f"FORMAT_CONTEXT.md/backend contract divergence: {exc}"
        ) from exc

    logger.info(
        "[CONTEXT_EXPORT] file discovery start project=%s",
        project_name,
    )

    sources, errors = discover_context_sources(project_name, paths)

    logger.info(
        "[CONTEXT_EXPORT] file discovery complete project=%s "
        "sources=%d errors=%d",
        project_name,
        len(sources),
        len(errors),
    )

    chunks_by_source = []
    markdown_by_source_path = {}

    for source in sources:
        logger.info(
            "[CONTEXT_EXPORT] file reading start source=%s",
            source.source_path,
        )

        try:
            markdown = source.source_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ContextValidationError(
                "Unable to read allowed Markdown file as UTF-8: "
                f"{source.archive_path}"
            ) from exc

        logger.info(
            "[CONTEXT_EXPORT] file reading complete source=%s bytes=%d",
            source.source_path,
            len(markdown.encode("utf-8")),
        )
        logger.info(
            "[CONTEXT_EXPORT] chunking start source=%s",
            source.source_path,
        )

        chunks = split_markdown_into_chunks(
            text=markdown,
            default_section=source.source_path.name,
        )

        logger.info(
            "[CONTEXT_EXPORT] chunking complete source=%s chunks=%d",
            source.source_path,
            len(chunks),
        )

        chunks_by_source.append((source, markdown, chunks))
        markdown_by_source_path[source.source_path] = markdown

    if not any(chunks for _, _, chunks in chunks_by_source):
        raise ContextValidationError(
            "Allowed Markdown context files contain no indexable content"
        )

    full_context_sources, missing_full_context_files = (
        resolve_full_context_sources(
            sources=sources,
            project_name=project_name,
            paths=paths,
        )
    )
    full_context_files = [
        FullContextFile(
            source_path=source.source_path,
            archive_path=source.archive_path,
            content=markdown_by_source_path[source.source_path],
        )
        for source in full_context_sources
    ]

    project_supported_patches = set(
        supported_patch_paths_for_project(project_name)
    )
    required_full_targets = {
        patch_target_file(patch_path, project_name)
        for patch_path, definition in PATCH_DEFINITIONS.items()
        if patch_path in project_supported_patches
        and request.lifecycle_phase in definition.lifecycle_phases
    }
    missing_required_targets = required_full_targets & set(
        missing_full_context_files
    )
    if missing_required_targets:
        raise ContextValidationError(
            "Missing mandatory full target files for lifecycle phase "
            f"{request.lifecycle_phase}: "
            + ", ".join(sorted(missing_required_targets))
        )

    errors.extend(
        f"Missing authorized full context file: {archive_path}"
        for archive_path in missing_full_context_files
    )

    chunk_count = 0
    indexed_source_count = 0

    try:
        for source, markdown, chunks in chunks_by_source:
            indexed_chunks = index_context_source(
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
            "Context indexing failed for project=%s",
            project_name,
        )
        raise ContextExportInfrastructureError(
            "Context indexing failed"
        ) from exc

    try:
        requested_changed_files = (
            request.changed_files
            if request.changed_files is not None
            else _collect_changed_files(paths.project_root)
        )
        changed_files = sorted(
            {
                path.strip()
                for path in requested_changed_files
                if path.strip() and _is_safe_changed_file(path.strip())
            }
        )
        git_diff = (
            request.git_diff
            if request.git_diff is not None
            else _collect_git_diff(paths.project_root, changed_files)
        )
        qa_results = request.qa_results or ""
        change_summary = request.change_summary or ""
        git_log = _collect_git_log(paths.project_root)
        project_tree = _collect_project_tree(paths.source_context_root)

        query = build_context_query(
            project_name=project_name,
            change_summary=change_summary,
            changed_files=changed_files,
            git_diff=git_diff,
            qa_results=qa_results,
            project_tree=project_tree,
        )

        logger.info(
            "[CONTEXT_EXPORT] relevant context retrieval start "
            "project=%s top_k=%d project_tree=%s",
            project_name,
            CONTEXT_EXPORT_TOP_K,
            "included" if project_tree else "missing",
        )

        retrieved_chunks = retrieve_relevant_context_chunks(
            project_name=project_name,
            query=query,
            top_k=CONTEXT_EXPORT_TOP_K,
        )

        logger.info(
            "[CONTEXT_EXPORT] relevant context retrieval complete "
            "project=%s chunks=%d",
            project_name,
            len(retrieved_chunks),
        )
    except Exception as exc:
        logger.exception(
            "Relevant context retrieval failed for project=%s",
            project_name,
        )
        raise ContextExportInfrastructureError(
            "Relevant context retrieval failed"
        ) from exc

    try:
        context_zip_path = create_context_package(
            output_directory=paths.output_directory,
            project_name=project_name,
            query=query,
            retrieved_chunks=retrieved_chunks,
            change_summary=change_summary,
            changed_files=changed_files,
            git_diff=git_diff,
            git_log=git_log,
            qa_results=qa_results,
            project_tree=project_tree,
            top_k=CONTEXT_EXPORT_TOP_K,
            full_context_files=full_context_files,
            missing_full_context_files=missing_full_context_files,
            contract_version=build_contract_version(format_markdown),
            supported_patch_paths=sorted(project_supported_patches),
            canonical_project_path=canonical_project_path(project_name),
            lifecycle_phase=request.lifecycle_phase,
            execution_mode=request.execution_mode,
            objectives=[
                objective.model_dump(exclude_none=True)
                for objective in request.objectives
            ],
        )
    except Exception as exc:
        logger.exception(
            "Context ZIP creation failed for project=%s",
            project_name,
        )
        raise ContextExportInfrastructureError(
            "Context ZIP creation failed"
        ) from exc

    logger.info(
        "[CONTEXT_EXPORT] response construction start project=%s",
        project_name,
    )

    upload_zip_path = paths.output_directory / "context-deploy-package.zip"
    response_payload = {
        "status": "completed",
        "project_name": project_name,
        "workflow": "context-deploy",
        "lifecycle_phase": request.lifecycle_phase,
        "execution_mode": request.execution_mode,
        "objectives": [
            objective.model_dump(exclude_none=True)
            for objective in request.objectives
        ],
        "context_zip_path": "context/output/context-package.zip",
        "upload_zip_path": "context/output/context-deploy-package.zip",
        "indexed_source_count": indexed_source_count,
        "chunk_count": chunk_count,
        "collection_name": CONTEXT_COLLECTION_NAME,
        "errors": errors,
    }

    try:
        create_context_upload_package(
            output_directory=paths.output_directory,
            context_zip_path=context_zip_path,
            response_payload=response_payload,
        )
    except Exception as exc:
        logger.exception(
            "Context upload ZIP creation failed for project=%s",
            project_name,
        )
        raise ContextExportInfrastructureError(
            "Context upload ZIP creation failed"
        ) from exc

    response = ContextExportResponse(**response_payload)

    logger.info(
        "[CONTEXT_EXPORT] response construction complete project=%s "
        "sources=%d chunks=%d",
        project_name,
        indexed_source_count,
        chunk_count,
    )

    return response
