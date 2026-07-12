import uuid

from fastapi import APIRouter

from app.services.embedding_service import create_embedding
from app.services.qdrant_service import (
    create_collection,
    save_embedding,
    search_similar,
)

from app.services.llm_service import generate_answer

router = APIRouter(
    prefix="/ai",
    tags=["AI"],
)


@router.post("/embeddings/test")
def test_embedding(data: dict):
    vector = create_embedding(data["text"])

    return {
        "dimensions": len(vector),
        "preview": vector[:5],
    }


@router.post("/qdrant/test")
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

    return {
        "status": "saved",
        "collection": "sbm_docs",
        "point_id": point_id,
    }


@router.post("/search/test")
def test_search(data: dict):
    vector = create_embedding(data["question"])
    results = search_similar(vector)

    return {
        "question": data["question"],
        "results": [
            {
                "score": result.score,
                "payload": result.payload,
            }
            for result in results
        ],
    }


@router.post("/rag/test")
def test_rag(data: dict):
    question = data["question"]

    vector = create_embedding(question)
    results = search_similar(vector, limit=3)

    context = "\n\n".join(result.payload["text"] for result in results)

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
