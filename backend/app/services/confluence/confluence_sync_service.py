from app.config.settings import CONFLUENCE_EXCLUDED_TITLES

from app.services.confluence.confluence_client import (
    list_pages,
    get_page_content,
)
from app.services.qdrant_service import get_active_page_version


def sync_confluence_pages(ingest_page_func):
    pages = list_pages()

    excluded_titles = [
        title.strip()
        for title in CONFLUENCE_EXCLUDED_TITLES.split(",")
        if title.strip()
    ]

    indexed_pages = []
    skipped_pages = []

    for page_item in pages["response"]["results"]:
        page_id = page_item["id"]
        title = page_item["title"]

        if title in excluded_titles:
            skipped_pages.append(
                {
                    "page_id": page_id,
                    "title": title,
                    "reason": "excluded_title",
                }
            )
            continue

        page = get_page_content(page_id)
        confluence_version = page["response"]["version"]["number"]
        active_qdrant_version = get_active_page_version(page_id)

        if active_qdrant_version == confluence_version:
            skipped_pages.append(
                {
                    "page_id": page_id,
                    "title": title,
                    "reason": "already_synced",
                    "page_version": confluence_version,
                }
            )
            continue

        result = ingest_page_func(page_id)

        indexed_pages.append(
            {
                "page_id": page_id,
                "title": result["title"],
                "previous_version": active_qdrant_version,
                "new_version": result["page_version"],
                "chunks_count": result["chunks_count"],
                "sync_run_id": result["sync_run_id"],
            }
        )

    return {
        "status": "sync_completed",
        "checked_pages": len(pages["response"]["results"]),
        "indexed_count": len(indexed_pages),
        "skipped_count": len(skipped_pages),
        "indexed_pages": indexed_pages,
        "skipped_pages": skipped_pages,
    }
