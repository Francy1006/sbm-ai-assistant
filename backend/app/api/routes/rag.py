from fastapi import APIRouter

from app.services.embedding_service import create_embedding
from app.services.qdrant_service import search_similar
from app.services.llm_service import generate_answer


router = APIRouter(
    prefix="/rag",
    tags=["RAG"],
)


@router.post("/query")
def rag_query(data: dict):
    question = data["question"]

    vector = create_embedding(question)
    results = search_similar(vector, limit=3)

    context = "\n\n".join(
        result.payload["text"]
        for result in results
    )

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