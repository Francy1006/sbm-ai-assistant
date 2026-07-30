from __future__ import annotations

import hashlib

from qdrant_client.models import FieldCondition, Filter, MatchValue

from app.config.settings import CONTEXT_EXPORT_TOP_K
from app.services.contexts.context_index_service import (
    CONTEXT_COLLECTION_NAME,
)
from app.services.contexts.models import RetrievedContextChunk
from app.services.embedding_service import create_embedding
from app.services.qdrant_service import search_similar


GLOBAL_REPOSITORY = "SBM-SUITE"
CONTEXT_WORKFLOW = "context-deploy"


def build_context_query(
    project_name: str,
    change_summary: str | None,
    changed_files: list[str],
    git_diff: str,
    qa_results: str,
) -> str:
    sections = [
        f"Proyecto: {project_name}",
    ]

    if change_summary and change_summary.strip():
        sections.append(
            f"Resumen del cambio:\n{change_summary.strip()}"
        )

    if changed_files:
        sections.append(
            "Archivos modificados:\n" + "\n".join(changed_files)
        )

    if git_diff.strip():
        sections.append(f"Diff Git:\n{git_diff.strip()}")

    if qa_results.strip():
        sections.append(
            f"Resultados QA:\n{qa_results.strip()}"
        )

    if len(sections) == 1:
        sections.append("Cambio actual sin detalles adicionales.")

    return "\n\n".join(sections)


def _scope_filter(
    project_name: str,
    global_scope: bool,
) -> Filter:
    repository_condition = FieldCondition(
        key="repository",
        match=MatchValue(value=GLOBAL_REPOSITORY),
    )
    must = [
        FieldCondition(
            key="project_name",
            match=MatchValue(value=project_name),
        ),
        FieldCondition(
            key="workflow",
            match=MatchValue(value=CONTEXT_WORKFLOW),
        ),
        FieldCondition(
            key="is_active",
            match=MatchValue(value=True),
        ),
    ]

    if global_scope:
        must.append(repository_condition)
        return Filter(must=must)

    return Filter(
        must=must,
        must_not=[repository_condition],
    )


def _deduplication_key(point) -> tuple[str, str, str]:
    payload = point.payload
    text = payload.get("text", "")
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return (
        payload.get("archive_path", ""),
        payload.get("section", ""),
        text_hash,
    )


def retrieve_relevant_context_chunks(
    project_name: str,
    query: str,
    top_k: int = CONTEXT_EXPORT_TOP_K,
) -> list[RetrievedContextChunk]:
    if top_k < 1:
        raise ValueError("top_k must be greater than zero")

    vector = create_embedding(query)
    candidates = []

    for global_scope in (True, False):
        candidates.extend(
            search_similar(
                vector=vector,
                limit=top_k,
                collection_name=CONTEXT_COLLECTION_NAME,
                query_filter=_scope_filter(
                    project_name=project_name,
                    global_scope=global_scope,
                ),
            )
        )

    candidates.sort(key=lambda point: point.score, reverse=True)
    unique_chunks = []
    seen = set()

    for point in candidates:
        key = _deduplication_key(point)

        if key in seen:
            continue

        seen.add(key)
        payload = point.payload
        unique_chunks.append(
            RetrievedContextChunk(
                point_id=str(point.id),
                source_path=payload.get("source_path", ""),
                archive_path=payload.get("archive_path", ""),
                section=payload.get("section", ""),
                score=float(point.score),
                content=payload.get("text", ""),
            )
        )

    return unique_chunks
