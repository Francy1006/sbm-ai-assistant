from __future__ import annotations

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    FilterSelector,
)

from app.config.settings import (
    QDRANT_URL,
    QDRANT_COLLECTION_NAME,
)

COLLECTION_NAME = QDRANT_COLLECTION_NAME
DEFAULT_VECTOR_SIZE = 1024
DEFAULT_DISTANCE = Distance.COSINE

client = QdrantClient(url=QDRANT_URL)


def collection_exists(collection_name: str) -> bool:
    return client.collection_exists(collection_name)


def create_collection(
    collection_name: str | None = None,
    vector_size: int = DEFAULT_VECTOR_SIZE,
    distance: Distance = DEFAULT_DISTANCE,
):
    target_collection = collection_name or COLLECTION_NAME

    if not client.collection_exists(target_collection):
        client.create_collection(
            collection_name=target_collection,
            vectors_config=VectorParams(
                size=vector_size,
                distance=distance,
            )
        )
        return

    collection_info = client.get_collection(target_collection)
    vectors_config = collection_info.config.params.vectors

    if isinstance(vectors_config, dict):
        raise ValueError(
            f"Collection '{target_collection}' uses named vectors; "
            "a single unnamed vector is required"
        )

    if (
        vectors_config.size != vector_size
        or vectors_config.distance != distance
    ):
        raise ValueError(
            f"Collection '{target_collection}' has incompatible vector "
            f"configuration: expected size={vector_size}, distance={distance}"
        )


def save_embedding(
    point_id: str,
    vector: list[float],
    text: str,
    metadata: dict,
    collection_name: str | None = None,
):
    target_collection = collection_name or COLLECTION_NAME

    client.upsert(
        collection_name=target_collection,
        points=[
            PointStruct(
                id=point_id,
                vector=vector,
                payload={
                    "text": text,
                    **metadata
                }
            )
        ]
    )


def save_embeddings(
    points: list[PointStruct],
    collection_name: str | None = None,
):
    if not points:
        return

    client.upsert(
        collection_name=collection_name or COLLECTION_NAME,
        points=points,
        wait=True,
    )


def scroll_all_points(
    scroll_filter: Filter,
    collection_name: str | None = None,
) -> list:
    target_collection = collection_name or COLLECTION_NAME
    points = []
    offset = None
    seen_offsets = set()

    while True:
        batch, offset = client.scroll(
            collection_name=target_collection,
            scroll_filter=scroll_filter,
            with_payload=True,
            with_vectors=False,
            limit=100,
            offset=offset,
        )
        points.extend(batch)

        if offset is None:
            return points

        offset_marker = str(offset)

        if offset_marker in seen_offsets:
            raise RuntimeError(
                f"Qdrant returned a repeated scroll offset for "
                f"collection '{target_collection}'"
            )

        seen_offsets.add(offset_marker)


def deactivate_points(
    point_ids: list,
    collection_name: str | None = None,
):
    if not point_ids:
        return

    client.set_payload(
        collection_name=collection_name or COLLECTION_NAME,
        payload={"is_active": False},
        points=point_ids,
        wait=True,
    )


def update_points_payload(
    point_ids: list,
    payload: dict,
    collection_name: str | None = None,
):
    if not point_ids:
        return

    client.set_payload(
        collection_name=collection_name or COLLECTION_NAME,
        payload=payload,
        points=point_ids,
        wait=True,
    )


def search_similar(
    vector: list[float],
    limit: int = 3,
    collection_name: str | None = None,
    query_filter: Filter | None = None,
):
    response = client.query_points(
        collection_name=collection_name or COLLECTION_NAME,
        query=vector,
        query_filter=query_filter or Filter(
            must=[
                FieldCondition(
                    key="is_active",
                    match=MatchValue(value=True)
                )
            ]
        ),
        limit=limit,
        with_payload=True
    )

    return response.points


def delete_points_by_page_id(page_id: str):
    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=FilterSelector(
            filter=Filter(
                must=[
                    FieldCondition(
                        key="page_id",
                        match=MatchValue(value=page_id)
                    )
                ]
            )
        ),
        wait=True
    )


def deactivate_old_syncs(page_id: str, current_sync_run_id: str):
    points = client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=Filter(
            must=[
                FieldCondition(
                    key="page_id",
                    match=MatchValue(value=page_id)
                ),
                FieldCondition(
                    key="is_active",
                    match=MatchValue(value=True)
                ),
            ]
        ),
        with_payload=True,
        with_vectors=False,
        limit=100
    )[0]

    old_point_ids = [
        point.id
        for point in points
        if point.payload.get("sync_run_id") != current_sync_run_id
    ]

    if old_point_ids:
        client.set_payload(
            collection_name=COLLECTION_NAME,
            payload={"is_active": False},
            points=old_point_ids,
            wait=True
        )



def cleanup_inactive_same_version(page_id: str, page_version: int):
    points = client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=Filter(
            must=[
                FieldCondition(
                    key="page_id",
                    match=MatchValue(value=page_id)
                ),
                FieldCondition(
                    key="page_version",
                    match=MatchValue(value=page_version)
                ),
                FieldCondition(
                    key="is_active",
                    match=MatchValue(value=False)
                ),
            ]
        ),
        with_payload=True,
        with_vectors=False,
        limit=100
    )[0]

    point_ids = [point.id for point in points]

    if point_ids:
        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=point_ids,
            wait=True
        )

    return len(point_ids)


def get_active_page_version(page_id: str):
    if not client.collection_exists(COLLECTION_NAME):
        return None

    points = client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=Filter(
            must=[
                FieldCondition(
                    key="page_id",
                    match=MatchValue(value=page_id)
                ),
                FieldCondition(
                    key="is_active",
                    match=MatchValue(value=True)
                ),
            ]
        ),
        with_payload=True,
        with_vectors=False,
        limit=1
    )[0]

    if not points:
        return None

    return points[0].payload.get("page_version")


def cleanup_old_inactive_versions(page_id: str, keep_last_versions: int = 1):
    points = client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=Filter(
            must=[
                FieldCondition(
                    key="page_id",
                    match=MatchValue(value=page_id)
                ),
                FieldCondition(
                    key="is_active",
                    match=MatchValue(value=False)
                ),
            ]
        ),
        with_payload=True,
        with_vectors=False,
        limit=100
    )[0]

    versions = {}

    for point in points:
        page_version = point.payload.get("page_version")

        if page_version not in versions:
            versions[page_version] = []

        versions[page_version].append(point.id)

    versions_to_delete = sorted(versions.keys(), reverse=True)[keep_last_versions:]

    point_ids_to_delete = [
        point_id
        for version in versions_to_delete
        for point_id in versions[version]
    ]

    if point_ids_to_delete:
        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=point_ids_to_delete,
            wait=True
        )

    return len(point_ids_to_delete) 
