import os
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

QDRANT_URL = os.getenv("QDRANT_URL")
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_NAME")

client = QdrantClient(url=QDRANT_URL)


def create_collection():
    if not client.collection_exists(COLLECTION_NAME):
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=1024,
                distance=Distance.COSINE
            )
        )


def save_embedding(point_id: str, vector: list[float], text: str, metadata: dict):
    client.upsert(
        collection_name=COLLECTION_NAME,
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


def search_similar(vector: list[float], limit: int = 3):
    response = client.query_points(
        collection_name=COLLECTION_NAME,
        query=vector,
        query_filter=Filter(
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



