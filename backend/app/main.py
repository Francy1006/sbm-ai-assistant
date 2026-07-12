from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes.ai import router as ai_router
from app.api.routes.confluence import router as confluence_router
from app.api.routes.health import router as health_router
from app.api.routes.rag import router as rag_router
from app.api.routes.slack import router as slack_router
from app.services.confluence.confluence_ingest_service import (
    ingest_confluence_page as ingest_confluence_page_service,
)
from app.services.scheduler_service import start_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler(ingest_confluence_page_service)
    yield


app = FastAPI(
    title="SBM AI Assistant",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(rag_router)
app.include_router(slack_router)
app.include_router(confluence_router)
app.include_router(ai_router)