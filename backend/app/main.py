from fastapi import FastAPI
import os
import uuid

from app.services.embedding_service import create_embedding
from app.services.qdrant_service import (
    create_collection,
    save_embedding,
    search_similar,
    delete_points_by_page_id,
    deactivate_old_syncs,
    cleanup_inactive_same_version,
    get_active_page_version,
    cleanup_old_inactive_versions,
)
from app.services.llm_service import generate_answer
from app.services.confluence.confluence_client import (
    test_confluence_connection,
    list_pages,
    get_page_content,
)
from app.services.confluence.html_parser import clean_html_to_text
from app.services.chunk_service import split_text_into_chunks
from app.services.confluence.confluence_sync_service import sync_confluence_pages
from contextlib import asynccontextmanager
from app.services.scheduler_service import start_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler(ingest_confluence_page)
    yield


app = FastAPI(title="SBM AI Assistant", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ai/embeddings/test")
def test_embedding(data: dict):
    vector = create_embedding(data["text"])

    return {"dimensions": len(vector), "preview": vector[:5]}


@app.post("/ai/qdrant/test")
def test_qdrant(data: dict):
    create_collection()

    vector = create_embedding(data["text"])

    point_id = str(uuid.uuid4())

    save_embedding(
        point_id=point_id,
        vector=vector,
        text=data["text"],
        metadata={
            "source": data.get("source", "manual_test"),
            "area": data.get("area", "general"),
        },
    )

    return {"status": "saved", "collection": "sbm_docs", "point_id": point_id}


@app.post("/ai/search/test")
def test_search(data: dict):
    vector = create_embedding(data["question"])

    results = search_similar(vector)

    return {
        "question": data["question"],
        "results": [
            {"score": result.score, "payload": result.payload} for result in results
        ],
    }


@app.post("/ai/rag/test")
def test_rag(data: dict):
    question = data["question"]

    vector = create_embedding(question)

    results = search_similar(vector, limit=3)

    context = "\n\n".join([result.payload["text"] for result in results])

    answer = generate_answer(question, context)

    return {
        "question": question,
        "answer": answer,
        "sources": [
            {
                "source": result.payload.get("source"),
                "page_id": result.payload.get("page_id"),
                "page_title": result.payload.get("page_title"),
                "page_version": result.payload.get("page_version"),
                "chunk_index": result.payload.get("chunk_index"),
                "score": result.score,
            }
            for result in results
        ],
    }


@app.get("/confluence/test")
def confluence_test():
    return test_confluence_connection()


@app.get("/confluence/pages")
def confluence_pages():
    return list_pages()


@app.get("/confluence/pages/{page_id}")
def confluence_page(page_id: str):
    return get_page_content(page_id)


@app.get("/confluence/pages/{page_id}/text")
def confluence_page_text(page_id: str):
    page = get_page_content(page_id)

    raw_html = page["response"]["body"]["storage"]["value"]

    text = clean_html_to_text(raw_html)

    return {"page_id": page_id, "title": page["response"]["title"], "text": text}


@app.get("/confluence/pages/{page_id}/chunks")
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


@app.post("/confluence/pages/{page_id}/ingest")
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


@app.post("/confluence/ingest")
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


@app.post("/confluence/sync")
def sync_confluence_space():
    return sync_confluence_pages(ingest_confluence_page)
