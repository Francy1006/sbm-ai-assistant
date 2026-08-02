import json
import logging
import os
import tempfile
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from app.config.settings import EMBEDDING_MODEL_NAME
from app.services.contexts.context_index_service import (
    CONTEXT_COLLECTION_NAME,
    content_hash,
)
from app.services.contexts.models import (
    FullContextFile,
    RetrievedContextChunk,
)


logger = logging.getLogger("uvicorn.error.context_export.zip")
logger.setLevel(logging.INFO)

FORMAT_CONTEXT_ARCHIVE_PATH = "FORMAT_CONTEXT.md"
PROJECT_TREE_ARCHIVE_PATH = "project-tree.txt"
PROJECT_TREE_SOURCE_PATH = "SBM-SUITE/context/project-tree.txt"


def _render_retrieved_context(
    retrieved_chunks: list[RetrievedContextChunk],
) -> str:
    grouped = OrderedDict()

    for chunk in retrieved_chunks:
        key = (chunk.source_path, chunk.archive_path)
        grouped.setdefault(key, []).append(chunk)

    lines = ["# Retrieved Context", ""]

    if not grouped:
        lines.extend(
            ["No relevant context chunks were retrieved.", ""]
        )
        return "\n".join(lines)

    for (source_path, archive_path), chunks in grouped.items():
        lines.extend(
            [
                f"## {archive_path}",
                "",
                f"- source_path: `{source_path}`",
                f"- archive_path: `{archive_path}`",
                "",
            ]
        )

        for chunk in chunks:
            lines.extend(
                [
                    f"### {chunk.section or 'Sin sección'}",
                    "",
                    f"Score: {chunk.score:.6f}",
                    "",
                    chunk.content,
                    "",
                ]
            )

    return "\n".join(lines)


def _text_file(content: str, empty_message: str) -> str:
    normalized = content.strip()
    return (
        f"{normalized}\n"
        if normalized
        else f"{empty_message}\n"
    )


def _project_tree_manifest(project_tree: str) -> dict:
    if not project_tree.strip():
        return {
            "included": False,
            "source_path": PROJECT_TREE_SOURCE_PATH,
            "archive_path": None,
            "content_hash": None,
        }

    return {
        "included": True,
        "source_path": PROJECT_TREE_SOURCE_PATH,
        "archive_path": PROJECT_TREE_ARCHIVE_PATH,
        "content_hash": content_hash(project_tree),
    }


def create_context_package(
    output_directory: Path,
    project_name: str,
    query: str,
    retrieved_chunks: list[RetrievedContextChunk],
    change_summary: str,
    changed_files: list[str],
    git_diff: str,
    git_log: str,
    qa_results: str,
    project_tree: str,
    top_k: int,
    full_context_files: list[FullContextFile],
    missing_full_context_files: list[str],
) -> Path:
    destination = output_directory / "context-package.zip"

    format_context_files = [
        context_file
        for context_file in full_context_files
        if context_file.archive_path
        == FORMAT_CONTEXT_ARCHIVE_PATH
    ]

    if len(format_context_files) != 1:
        raise ValueError(
            "Exactly one FORMAT_CONTEXT.md full context file "
            "is required"
        )

    format_context_file = format_context_files[0]
    packaged_context_files = [
        context_file
        for context_file in full_context_files
        if context_file.archive_path
        != FORMAT_CONTEXT_ARCHIVE_PATH
    ]

    logger.info(
        "[CONTEXT_EXPORT] manifest creation start "
        "project=%s sources=%d",
        project_name,
        len(retrieved_chunks),
    )

    retrieved_sources = [
        {
            "source_path": source_path,
            "archive_path": archive_path,
        }
        for source_path, archive_path in sorted(
            {
                (
                    chunk.source_path,
                    chunk.archive_path,
                )
                for chunk in retrieved_chunks
            }
        )
    ]
    full_context_file_manifest = [
        {
            "source_path": str(
                context_file.source_path
            ),
            "archive_path": (
                context_file.archive_path
            ),
        }
        for context_file in full_context_files
    ]
    content_hashes = {
        context_file.archive_path: content_hash(
            context_file.content
        )
        for context_file in full_context_files
    }

    normalized_project_tree = project_tree.strip()
    packaged_project_tree = (
        f"{normalized_project_tree}\n"
        if normalized_project_tree
        else ""
    )
    project_tree_manifest = _project_tree_manifest(
        packaged_project_tree
    )

    if normalized_project_tree:
        content_hashes[
            PROJECT_TREE_ARCHIVE_PATH
        ] = project_tree_manifest["content_hash"]

    manifest = {
        "project_name": project_name,
        "workflow": "context-deploy",
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "query": query,
        "collection_name": CONTEXT_COLLECTION_NAME,
        "chunk_count": len(retrieved_chunks),
        "retrieved_chunk_count": len(
            retrieved_chunks
        ),
        "retrieved_sources": retrieved_sources,
        "full_context_files": (
            full_context_file_manifest
        ),
        "format_context_file": {
            "source_path": str(
                format_context_file.source_path
            ),
            "archive_path": (
                FORMAT_CONTEXT_ARCHIVE_PATH
            ),
            "protected": True,
            "complete": True,
        },
        "project_tree": project_tree_manifest,
        "missing_full_context_files": (
            missing_full_context_files
        ),
        "content_hashes": content_hashes,
        "filters_applied": {
            "project_name": project_name,
            "workflow": "context-deploy",
            "is_active": True,
            "global_repository": "SBM-SUITE",
            "project_repository": (
                "not SBM-SUITE"
            ),
        },
        "embedding_model": EMBEDDING_MODEL_NAME,
        "top_k": top_k,
    }
    manifest_json = json.dumps(
        manifest,
        ensure_ascii=False,
        indent=2,
    )

    logger.info(
        "[CONTEXT_EXPORT] manifest creation complete "
        "project=%s bytes=%d project_tree=%s",
        project_name,
        len(manifest_json.encode("utf-8")),
        "included"
        if normalized_project_tree
        else "missing",
    )

    temporary_path = None

    try:
        logger.info(
            "[CONTEXT_EXPORT] zip creation start "
            "project=%s destination=%s",
            project_name,
            destination.name,
        )

        with tempfile.NamedTemporaryFile(
            dir=output_directory,
            prefix=".context-package-",
            suffix=".zip",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(
                temporary_file.name
            )

        logger.info(
            "[CONTEXT_EXPORT] temporary zip "
            "allocation complete project=%s",
            project_name,
        )

        with ZipFile(
            temporary_path,
            mode="w",
            compression=ZIP_DEFLATED,
        ) as archive:
            archive.writestr(
                FORMAT_CONTEXT_ARCHIVE_PATH,
                format_context_file.content,
            )
            archive.writestr(
                "retrieved-context.md",
                _render_retrieved_context(
                    retrieved_chunks
                ),
            )
            archive.writestr(
                "change-summary.md",
                _text_file(
                    change_summary,
                    "No change summary was provided.",
                ),
            )
            archive.writestr(
                "changed-files.txt",
                _text_file(
                    "\n".join(changed_files),
                    (
                        "No changed files were "
                        "detected."
                    ),
                ),
            )
            archive.writestr(
                "git-diff.patch",
                _text_file(
                    git_diff,
                    (
                        "No Git diff was provided "
                        "or detected."
                    ),
                ),
            )
            archive.writestr(
                "git-log.txt",
                _text_file(
                    git_log,
                    "No Git log was available.",
                ),
            )
            archive.writestr(
                "qa-results.md",
                _text_file(
                    qa_results,
                    (
                        "No QA results were "
                        "provided."
                    ),
                ),
            )

            if packaged_project_tree:
                archive.writestr(
                    PROJECT_TREE_ARCHIVE_PATH,
                    packaged_project_tree,
                )

            for context_file in (
                packaged_context_files
            ):
                archive.writestr(
                    context_file.archive_path,
                    context_file.content,
                )

            archive.writestr(
                "manifest.json",
                manifest_json,
            )

        logger.info(
            "[CONTEXT_EXPORT] temporary zip close "
            "complete project=%s",
            project_name,
        )
        logger.info(
            "[CONTEXT_EXPORT] zip creation "
            "complete project=%s",
            project_name,
        )
        logger.info(
            "[CONTEXT_EXPORT] atomic replace start "
            "project=%s",
            project_name,
        )

        os.replace(
            temporary_path,
            destination,
        )
        resolved_destination = (
            destination.resolve(strict=True)
        )

        logger.info(
            "[CONTEXT_EXPORT] atomic replace "
            "complete project=%s zip_bytes=%d",
            project_name,
            resolved_destination.stat().st_size,
        )

        return resolved_destination
    finally:
        if (
            temporary_path
            and temporary_path.exists()
        ):
            temporary_path.unlink()
