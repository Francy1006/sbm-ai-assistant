import uuid

from app.services.embedding_service import create_embedding
from app.services.qdrant_service import (
    create_collection,
    save_embedding,
    deactivate_old_syncs,
    cleanup_inactive_same_version,
    cleanup_old_inactive_versions,
)
from app.services.chunk_service import split_text_into_chunks
from app.services.confluence.confluence_client import get_page_content
from app.services.confluence.html_parser import clean_html_to_text

def ingest_confluence_page(page_id: str):
    page = get_page_content(page_id)

    raw_html = page["response"]["body"]["storage"]["value"]
    title = page["response"]["title"]
    page_version = page["response"]["version"]["number"]
    sync_run_id = str(uuid.uuid4())

    text = clean_html_to_text(raw_html)

    chunks = split_text_into_chunks(text)

    create_collection()

    saved_chunks = []

    for index, chunk in enumerate(chunks):
        vector = create_embedding(chunk)
        point_id = str(uuid.uuid4())

        save_embedding(
            point_id=point_id,
            vector=vector,
            text=chunk,
            metadata={
                "source": "confluence",
                "page_id": page_id,
                "page_title": title,
                "page_version": page_version,
                "sync_run_id": sync_run_id,
                "chunk_index": index,
                "is_active": True,
            },
        )

        saved_chunks.append(
            {
                "point_id": point_id,
                "chunk_index": index,
            }
        )

    deactivate_old_syncs(page_id, sync_run_id)

    deleted_old_same_version = cleanup_inactive_same_version(page_id, page_version)
    deleted_old_versions = cleanup_old_inactive_versions(page_id)

    return {
        "status": "indexed",
        "page_id": page_id,
        "title": title,
        "chunks_count": len(saved_chunks),
        "chunks": saved_chunks,
        "page_version": page_version,
        "sync_run_id": sync_run_id,
        "deleted_old_same_version": deleted_old_same_version,
        "deleted_old_versions": deleted_old_versions,
    }