from pydantic import BaseModel, Field


class RagQueryRequest(BaseModel):
    question: str = Field(min_length=1)


class RagSource(BaseModel):
    source: str | None = None
    page_id: str | None = None
    page_title: str | None = None
    page_version: int | None = None
    chunk_index: int | None = None
    score: float


class RagQueryResponse(BaseModel):
    question: str
    answer: str
    sources: list[RagSource]