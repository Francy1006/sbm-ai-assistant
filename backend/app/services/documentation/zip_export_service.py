import json
import logging
import os
import re
import tempfile
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import List
from zipfile import ZIP_DEFLATED, ZipFile

from app.config.settings import EMBEDDING_MODEL_NAME
from app.services.contexts.context_index_service import content_hash
from app.services.contexts.models import RetrievedContextChunk
from app.services.documentation.documentation_index_service import (
    DOCUMENTATION_COLLECTION_NAME,
)
from app.services.documentation.models import DocumentationFile


logger = logging.getLogger(
    "uvicorn.error.documentation_export.zip"
)
logger.setLevel(logging.INFO)

FORMAT_CONTEXT_ARCHIVE_PATH = "FORMAT_CONTEXT.md"
SYSTEM_PROMPT_ARCHIVE_PATH = "SYS_PROMPT.md"
PROJECT_TREE_ARCHIVE_PATH = "project-tree.txt"
DOCUMENTATION_FILES_ARCHIVE_PATH = "documentation-files.txt"
PROJECT_NAME_TEMPLATE = "{{PROJECT_NAME}}"
UNRESOLVED_TEMPLATE_PATTERN = re.compile(r"{{[A-Z0-9_]+}}")



def _read_contract(path: Path, label: str) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be an existing regular file")

    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"{label} must be readable UTF-8") from exc

    if not content.strip():
        raise ValueError(f"{label} must not be empty")

    return content


def _render_system_prompt(
    system_prompt_path: Path,
    project_name: str,
) -> str:
    source = _read_contract(system_prompt_path, "SYS_PROMPT.md")

    if PROJECT_NAME_TEMPLATE not in source:
        raise ValueError(
            "SYS_PROMPT.md must contain {{PROJECT_NAME}}"
        )

    rendered = source.replace(PROJECT_NAME_TEMPLATE, project_name)
    unresolved = sorted(
        set(UNRESOLVED_TEMPLATE_PATTERN.findall(rendered))
    )

    if unresolved:
        raise ValueError(
            "SYS_PROMPT.md contains unresolved template tokens: "
            + ", ".join(unresolved)
        )

    return rendered


def _render_retrieved_chunks(
    title: str,
    empty_message: str,
    chunks: List[RetrievedContextChunk],
) -> str:
    grouped = OrderedDict()

    for chunk in chunks:
        key = chunk.archive_path
        grouped.setdefault(key, []).append(chunk)

    lines = [f"# {title}", ""]

    if not grouped:
        lines.extend([empty_message, ""])
        return "\n".join(lines)

    for archive_path, source_chunks in grouped.items():
        lines.extend(
            [
                f"## {archive_path}",
                "",
                f"- source_path: `{archive_path}`",
                f"- archive_path: `{archive_path}`",
                "",
            ]
        )

        for chunk in source_chunks:
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
    return f"{normalized}\n" if normalized else f"{empty_message}\n"


def _project_tree_manifest(project_tree: str) -> dict:
    if not project_tree:
        return {
            "included": False,
            "archive_path": None,
            "content_hash": None,
        }

    return {
        "included": True,
        "archive_path": PROJECT_TREE_ARCHIVE_PATH,
        "content_hash": content_hash(project_tree),
    }


def create_documentation_package(
    output_directory: Path,
    project_name: str,
    query: str,
    retrieved_documentation_chunks: List[RetrievedContextChunk],
    retrieved_context_chunks: List[RetrievedContextChunk],
    documentation_files: List[DocumentationFile],
    change_summary: str,
    changed_files: List[str],
    git_diff: str,
    git_log: str,
    qa_results: str,
    project_tree: str,
    top_k: int,
    format_context_path: Path,
    system_prompt_path: Path,
    errors: List[str],
) -> Path:
    destination = output_directory / "documentation-package.zip"

    format_context_content = _read_contract(
        format_context_path,
        "FORMAT_CONTEXT.md",
    )
    rendered_system_prompt = _render_system_prompt(
        system_prompt_path,
        project_name,
    )

    protected_contract_paths = {
        FORMAT_CONTEXT_ARCHIVE_PATH,
        SYSTEM_PROMPT_ARCHIVE_PATH,
    }
    retrieved_documentation_paths = {
        chunk.archive_path
        for chunk in retrieved_documentation_chunks
        if chunk.archive_path
        and chunk.archive_path not in protected_contract_paths
    }
    available_documentation_by_path = {
        documentation_file.archive_path: documentation_file
        for documentation_file in documentation_files
        if documentation_file.archive_path
        not in protected_contract_paths
    }
    missing_snapshot_paths = sorted(
        retrieved_documentation_paths
        - set(available_documentation_by_path)
    )

    if missing_snapshot_paths:
        raise ValueError(
            "RAG-selected documentation candidates are missing complete "
            "source snapshots: " + ", ".join(missing_snapshot_paths)
        )

    packaged_documentation_files = [
        available_documentation_by_path[archive_path]
        for archive_path in sorted(retrieved_documentation_paths)
    ]

    documentation_paths = [
        documentation_file.archive_path
        for documentation_file in packaged_documentation_files
    ]
    documentation_files_content = _text_file(
        "\n".join(documentation_paths),
        "No authorized documentation files were discovered.",
    )

    normalized_project_tree = project_tree.strip()
    project_tree_manifest = _project_tree_manifest(
        normalized_project_tree
    )

    content_hashes = {
        FORMAT_CONTEXT_ARCHIVE_PATH: content_hash(
            format_context_content
        ),
        SYSTEM_PROMPT_ARCHIVE_PATH: content_hash(
            rendered_system_prompt
        ),
        DOCUMENTATION_FILES_ARCHIVE_PATH: content_hash(
            documentation_files_content
        ),
        **{
            documentation_file.archive_path: content_hash(
                documentation_file.content
            )
            for documentation_file in packaged_documentation_files
        },
    }

    if normalized_project_tree:
        content_hashes[PROJECT_TREE_ARCHIVE_PATH] = content_hash(
            normalized_project_tree
        )

    manifest = {
        "project_name": project_name,
        "workflow": "documentation-deploy",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "query": query,
        "collection_name": DOCUMENTATION_COLLECTION_NAME,
        "retrieved_documentation_chunk_count": len(
            retrieved_documentation_chunks
        ),
        "retrieved_context_chunk_count": len(
            retrieved_context_chunks
        ),
        "retrieved_documentation_sources": [
            {
                "source_path": archive_path,
                "archive_path": archive_path,
            }
            for archive_path in sorted(
                {
                    chunk.archive_path
                    for chunk in retrieved_documentation_chunks
                }
            )
        ],
        "retrieved_context_sources": [
            {
                "source_path": archive_path,
                "archive_path": archive_path,
            }
            for archive_path in sorted(
                {
                    chunk.archive_path
                    for chunk in retrieved_context_chunks
                }
            )
        ],
        "snapshot_policy": "rag-selected-complete",
        "documentation_files": [
            {
                "source_path": documentation_file.archive_path,
                "archive_path": documentation_file.archive_path,
                "complete": True,
                "selected_by_rag": True,
                "content_hash": content_hash(documentation_file.content),
            }
            for documentation_file in packaged_documentation_files
        ],
        "format_context_file": {
            "source_path": FORMAT_CONTEXT_ARCHIVE_PATH,
            "archive_path": FORMAT_CONTEXT_ARCHIVE_PATH,
            "protected": True,
            "complete": True,
        },
        "system_prompt_file": {
            "source_path": SYSTEM_PROMPT_ARCHIVE_PATH,
            "archive_path": SYSTEM_PROMPT_ARCHIVE_PATH,
            "protected": True,
            "complete": True,
            "rendered_project_name": project_name,
        },
        "documentation_files_file": {
            "archive_path": DOCUMENTATION_FILES_ARCHIVE_PATH,
            "content_hash": content_hash(documentation_files_content),
        },
        "project_tree": project_tree_manifest,
        "content_hashes": content_hashes,
        "embedding_model": EMBEDDING_MODEL_NAME,
        "top_k": top_k,
        "errors": list(errors),
        "filters_applied": {
            "project_name": project_name,
            "workflow": "documentation-deploy",
            "is_active": True,
        },
    }
    manifest_json = json.dumps(
        manifest,
        ensure_ascii=False,
        indent=2,
    )

    output_directory.mkdir(parents=True, exist_ok=True)
    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            dir=output_directory,
            prefix=".documentation-package-",
            suffix=".zip",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)

        with ZipFile(
            temporary_path,
            mode="w",
            compression=ZIP_DEFLATED,
        ) as archive:
            archive.writestr(
                FORMAT_CONTEXT_ARCHIVE_PATH,
                format_context_content,
            )
            archive.writestr(
                SYSTEM_PROMPT_ARCHIVE_PATH,
                rendered_system_prompt,
            )
            archive.writestr(
                DOCUMENTATION_FILES_ARCHIVE_PATH,
                documentation_files_content,
            )
            archive.writestr(
                "retrieved-documentation.md",
                _render_retrieved_chunks(
                    "Retrieved Documentation",
                    "No relevant documentation chunks were retrieved.",
                    retrieved_documentation_chunks,
                ),
            )
            archive.writestr(
                "retrieved-context.md",
                _render_retrieved_chunks(
                    "Retrieved Context",
                    "No relevant context chunks were provided.",
                    retrieved_context_chunks,
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
                    "No changed files were detected.",
                ),
            )
            archive.writestr(
                "git-diff.patch",
                _text_file(
                    git_diff,
                    "No Git diff was provided or detected.",
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
                    "No QA results were provided.",
                ),
            )

            if normalized_project_tree:
                archive.writestr(
                    PROJECT_TREE_ARCHIVE_PATH,
                    normalized_project_tree,
                )

            for documentation_file in packaged_documentation_files:
                archive.writestr(
                    documentation_file.archive_path,
                    documentation_file.content,
                )

            archive.writestr("manifest.json", manifest_json)

        os.replace(temporary_path, destination)
        return destination.resolve(strict=True)
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()
