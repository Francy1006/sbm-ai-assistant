from __future__ import annotations

import hashlib
import logging
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timezone

from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
)

from app.services.contexts.models import ContextSource, MarkdownChunk
from app.services.embedding_service import create_embeddings
from app.services.qdrant_service import (
    DEFAULT_DISTANCE,
    DEFAULT_VECTOR_SIZE,
    collection_exists,
    create_collection,
    deactivate_points,
    save_embeddings,
    scroll_all_points,
    update_points_payload,
)


CONTEXT_COLLECTION_NAME = "sbm_contexts"
POINT_NAMESPACE = uuid.UUID("3d4ef55a-5ab3-4f43-9c76-e79d900d3fc3")
logger = logging.getLogger("uvicorn.error.context_export.index")
logger.setLevel(logging.INFO)


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _point_id(
    project_name: str,
    source_path: str,
    source_hash: str,
    chunk: MarkdownChunk,
) -> str:
    identity = "|".join(
        (
            "context-deploy",
            project_name,
            source_path,
            source_hash,
            str(chunk.chunk_index),
            chunk.section,
        )
    )
    return str(uuid.uuid5(POINT_NAMESPACE, identity))


def _source_filter(
    project_name: str,
    source_path: str,
    active_only: bool = False,
) -> Filter:
    conditions = [
        FieldCondition(
            key="project_name",
            match=MatchValue(value=project_name),
        ),
        FieldCondition(
            key="source_path",
            match=MatchValue(value=source_path),
        ),
        FieldCondition(
            key="workflow",
            match=MatchValue(value="context-deploy"),
        ),
    ]

    if active_only:
        conditions.append(
            FieldCondition(
                key="is_active",
                match=MatchValue(value=True),
            )
        )

    return Filter(
        must=conditions,
    )


def _scroll_source_points(
    source: ContextSource,
    project_name: str,
    active_only: bool,
) -> list:
    source_paths = [str(source.source_path)]

    if (
        source.legacy_source_path
        and source.legacy_source_path not in source_paths
    ):
        source_paths.append(source.legacy_source_path)

    points_by_id = {}

    for source_path in source_paths:
        points = scroll_all_points(
            scroll_filter=_source_filter(
                project_name,
                source_path,
                active_only=active_only,
            ),
            collection_name=CONTEXT_COLLECTION_NAME,
        )

        for point in points:
            points_by_id[str(point.id)] = point

    return list(points_by_id.values())


def _points_match_unchanged_content(
    points: list,
    chunks: list[MarkdownChunk],
    source_hash: str,
) -> bool:
    if len(points) != len(chunks):
        return False

    expected_chunks = {
        (chunk.chunk_index, chunk.section)
        for chunk in chunks
    }
    indexed_chunks = {
        (
            point.payload.get("chunk_index"),
            point.payload.get("section"),
        )
        for point in points
        if point.payload.get("content_hash") == source_hash
    }
    return indexed_chunks == expected_chunks


def index_context_source(
    source: ContextSource,
    markdown: str,
    chunks: list[MarkdownChunk],
    project_name: str,
    embed: Callable[[str], list[float]] | None = None,
    embed_many: Callable[
        [list[str]],
        list[list[float]],
    ] = create_embeddings,
) -> int:
    if not chunks:
        return 0

    source_hash = content_hash(markdown)
    updated_at = datetime.fromtimestamp(
        source.source_path.stat().st_mtime,
        tz=timezone.utc,
    ).isoformat()
    point_ids = [
        _point_id(
            project_name=project_name,
            source_path=(
                source.legacy_source_path
                or str(source.source_path)
            ),
            source_hash=source_hash,
            chunk=chunk,
        )
        for chunk in chunks
    ]

    if collection_exists(CONTEXT_COLLECTION_NAME):
        create_collection(
            collection_name=CONTEXT_COLLECTION_NAME,
            vector_size=DEFAULT_VECTOR_SIZE,
            distance=DEFAULT_DISTANCE,
        )
        logger.info(
            "[CONTEXT_EXPORT] active chunk lookup start source=%s",
            source.source_path,
        )
        active_points = _scroll_source_points(
            source=source,
            project_name=project_name,
            active_only=True,
        )
        active_point_ids = {str(point.id) for point in active_points}
        logger.info(
            "[CONTEXT_EXPORT] active chunk lookup complete "
            "source=%s active_points=%d",
            source.source_path,
            len(active_points),
        )

        if (
            active_point_ids == set(point_ids)
            or _points_match_unchanged_content(
                active_points,
                chunks,
                source_hash,
            )
        ):
            update_points_payload(
                point_ids=[point.id for point in active_points],
                payload={
                    "project": project_name,
                    "project_name": project_name,
                    "repository": source.repository,
                    "context_type": source.context_type,
                    "source_path": str(source.source_path),
                    "archive_path": source.archive_path,
                    "updated_at": updated_at,
                    "version": source_hash[:12],
                    "is_active": True,
                    "content_hash": source_hash,
                    "workflow": "context-deploy",
                },
                collection_name=CONTEXT_COLLECTION_NAME,
            )
            logger.info(
                "[CONTEXT_EXPORT] unchanged source skip complete "
                "source=%s chunks=%d",
                source.source_path,
                len(chunks),
            )
            return len(chunks)

    embedding_started_at = time.monotonic()
    logger.info(
        "[CONTEXT_EXPORT] embedding start source=%s chunks=%d",
        source.source_path,
        len(chunks),
    )

    if embed is not None:
        vectors = [embed(chunk.content) for chunk in chunks]
    else:
        vectors = embed_many([chunk.content for chunk in chunks])

    logger.info(
        "[CONTEXT_EXPORT] embedding complete source=%s vectors=%d "
        "duration_seconds=%.3f",
        source.source_path,
        len(vectors),
        time.monotonic() - embedding_started_at,
    )

    if len(vectors) != len(chunks):
        raise ValueError(
            "Embedding service returned a different number of vectors "
            "than chunks"
        )

    vector_size = len(vectors[0])

    if vector_size == 0 or any(len(vector) != vector_size for vector in vectors):
        raise ValueError("Embedding service returned inconsistent dimensions")

    create_collection(
        collection_name=CONTEXT_COLLECTION_NAME,
        vector_size=vector_size,
        distance=DEFAULT_DISTANCE,
    )

    points = [
        PointStruct(
            id=point_id,
            vector=vector,
            payload={
                "text": chunk.content,
                "project": project_name,
                "project_name": project_name,
                "repository": source.repository,
                "context_type": source.context_type,
                "section": chunk.section,
                "source_path": str(source.source_path),
                "archive_path": source.archive_path,
                "updated_at": updated_at,
                "version": source_hash[:12],
                "is_active": True,
                "content_hash": source_hash,
                "workflow": "context-deploy",
                "chunk_index": chunk.chunk_index,
            },
        )
        for point_id, vector, chunk in zip(point_ids, vectors, chunks)
    ]

    logger.info(
        "[CONTEXT_EXPORT] qdrant upsert start source=%s points=%d",
        source.source_path,
        len(points),
    )
    save_embeddings(
        points=points,
        collection_name=CONTEXT_COLLECTION_NAME,
    )
    logger.info(
        "[CONTEXT_EXPORT] qdrant upsert complete source=%s points=%d",
        source.source_path,
        len(points),
    )

    current_ids = set(point_ids)
    logger.info(
        "[CONTEXT_EXPORT] obsolete chunk lookup start source=%s",
        source.source_path,
    )
    previous_points = _scroll_source_points(
        source=source,
        project_name=project_name,
        active_only=False,
    )
    logger.info(
        "[CONTEXT_EXPORT] obsolete chunk lookup complete "
        "source=%s points=%d",
        source.source_path,
        len(previous_points),
    )
    obsolete_ids = [
        point.id
        for point in previous_points
        if str(point.id) not in current_ids
        and point.payload.get("is_active", False)
    ]
    logger.info(
        "[CONTEXT_EXPORT] obsolete chunk deactivation start "
        "source=%s points=%d",
        source.source_path,
        len(obsolete_ids),
    )
    deactivate_points(
        point_ids=obsolete_ids,
        collection_name=CONTEXT_COLLECTION_NAME,
    )
    logger.info(
        "[CONTEXT_EXPORT] obsolete chunk deactivation complete "
        "source=%s points=%d",
        source.source_path,
        len(obsolete_ids),
    )

    return len(points)
