import os

from fastapi import APIRouter

from app.services.chunk_service import split_text_into_chunks
from app.services.confluence.confluence_client import (
    get_page_content,
    list_pages,
    test_confluence_connection,
)
from app.services.confluence.confluence_ingest_service import (
    ingest_confluence_page,
)
from app.services.confluence.confluence_sync_service import (
    sync_confluence_pages,
)
from app.services.confluence.html_parser import clean_html_to_text

router = APIRouter(
    prefix="/confluence",
    tags=["Confluence"],
)


@router.get("/test")
def confluence_test():
    return test_confluence_connection()


@router.get("/pages")
def confluence_pages():
    return list_pages()


@router.get("/pages/{page_id}")
def confluence_page(page_id: str):
    return get_page_content(page_id)


@router.get("/pages/{page_id}/text")
def confluence_page_text(page_id: str):
    page = get_page_content(page_id)

    raw_html = page["response"]["body"]["storage"]["value"]
    text = clean_html_to_text(raw_html)

    return {
        "page_id": page_id,
        "title": page["response"]["title"],
        "text": text,
    }


@router.get("/pages/{page_id}/chunks")
def confluence_page_chunks(page_id: str):
    page = get_page_content(page_id)

    raw_html = page["response"]["body"]["storage"]["value"]
    text = clean_html_to_text(raw_html)
    chunks = split_text_into_chunks(text)

    return {
        "page_id": page_id,
        "title": page["response"]["title"],
        "chunks_count": len(chunks),
        "chunks": chunks,
    }


@router.post("/pages/{page_id}/ingest")
def ingest_confluence_page_route(page_id: str):
    return ingest_confluence_page(page_id)


@router.post("/ingest")
def ingest_confluence_space():
    pages = list_pages()

    excluded_titles = [
        title.strip()
        for title in os.getenv("CONFLUENCE_EXCLUDED_TITLES", "").split(",")
        if title.strip()
    ]

    indexed_pages = []

    for page_item in pages["response"]["results"]:
        page_id = page_item["id"]
        title = page_item["title"]

        if title in excluded_titles:
            continue

        result = ingest_confluence_page(page_id)

        indexed_pages.append(
            {
                "page_id": page_id,
                "title": result["title"],
                "page_version": result["page_version"],
                "chunks_count": result["chunks_count"],
                "sync_run_id": result["sync_run_id"],
                "deleted_old_same_version": result["deleted_old_same_version"],
            }
        )

    return {
        "status": "space_indexed",
        "pages_count": len(indexed_pages),
        "pages": indexed_pages,
    }


@router.post("/sync")
def sync_confluence_space():
    return sync_confluence_pages(ingest_confluence_page)
