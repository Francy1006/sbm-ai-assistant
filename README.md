# sbm-ai-assistant

AI-powered RAG assistant for SBM Manager, integrating Confluence, Qdrant, multilingual embeddings, and Cohere to provide grounded answers from business documentation.

Overview

SBM AI Assistant is a backend AI service that connects to Confluence as the source of truth, synchronizes business documentation into Qdrant, and exposes a RAG API capable of answering questions using only indexed documentation.

The system supports incremental sync, document versioning, automatic scheduler-based updates, multilingual embeddings, and auditable sources in every generated answer.

Main Features

* Confluence integration as documentation source.
* Automatic sync scheduler.
* Incremental indexing by page_version.
* Qdrant vector database for semantic search.
* Multilingual embeddings using FastEmbed.
* Cohere LLM integration for grounded responses.
* Source-aware RAG answers.
* Active/inactive version control for rollback.
* Cleanup of old inactive document versions.
* Docker-based local environment.

Architecture

Confluence
   |
   | list pages + get page content
   v
Sync Scheduler / Manual Sync
   |
   | detect new or modified pages
   v
HTML Parser
   |
   | clean Confluence HTML
   v
Chunking Service
   |
   | split text into chunks
   v
Embedding Service
   |
   | multilingual vector embeddings
   v
Qdrant
   |
   | semantic search over active chunks
   v
RAG API
   |
   | retrieve context + generate answer
   v
Cohere
   |
   v
Answer + Sources

Tech Stack

* Python
* FastAPI
* Docker Compose
* Qdrant
* FastEmbed
* Cohere
* Confluence REST API
* APScheduler
* BeautifulSoup

Project Structure

sbm-ai-assistant/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── services/
│   │   │   ├── embedding_service.py
│   │   │   ├── qdrant_service.py
│   │   │   ├── llm_service.py
│   │   │   ├── chunk_service.py
│   │   │   ├── scheduler_service.py
│   │   │   └── confluence/
│   │   │       ├── confluence_client.py
│   │   │       ├── confluence_sync_service.py
│   │   │       └── html_parser.py
│   ├── Dockerfile
│   └── requirements.txt
├── docker-compose.yml
├── .env.example
└── README.md

Environment Variables

Create a .env.example file with the required configuration:

QDRANT_URL=http://qdrant:6333
QDRANT_COLLECTION_NAME=sbm_docs
COHERE_API_KEY=your_cohere_api_key
COHERE_MODEL=command-a-03-2025
CONFLUENCE_BASE_URL=https://your-domain.atlassian.net/wiki
CONFLUENCE_EMAIL=your_email@example.com
CONFLUENCE_API_TOKEN=your_confluence_api_token
CONFLUENCE_SPACE_KEY=your_space_key
CONFLUENCE_EXCLUDED_TITLES=Descripción general,Notas en el espacio
CONFLUENCE_SYNC_INTERVAL_MINUTES=5

Running Locally

Build and start the project:

docker compose up --build

Restart only the backend after Python code changes:

docker compose restart backend

Stop the environment:

docker compose down

Avoid using docker compose down -v unless you intentionally want to delete the Qdrant volume.

Core Endpoints

Health Check

GET /health

Example:

curl http://localhost:8000/health

Test Confluence Connection

GET /confluence/test

Validates the Confluence API credentials and space access.

List Confluence Pages

GET /confluence/pages

Returns the pages available in the configured Confluence space.

Read Confluence Page Text

GET /confluence/pages/{page_id}/text

Reads one Confluence page, removes HTML, and returns clean text.

Ingest One Confluence Page

POST /confluence/pages/{page_id}/ingest

Indexes one specific Confluence page into Qdrant.

Ingest Full Confluence Space

POST /confluence/ingest

Indexes all valid Confluence pages, excluding titles configured in CONFLUENCE_EXCLUDED_TITLES.

Incremental Sync

POST /confluence/sync

Runs an incremental sync between Confluence and Qdrant.

It compares the current Confluence page_version against the active version stored in Qdrant. If the page changed, it reindexes only that page. If nothing changed, it skips the page.

RAG Query

POST /ai/rag/test

Example body:

{
  "question": "¿Qué secciones tiene la documentación de Ditaly Pasta?"
}

Example response:

{
  "question": "¿Qué secciones tiene la documentación de Ditaly Pasta?",
  "answer": "La documentación de Ditaly Pasta tiene las siguientes secciones: General, Locales, Procedimientos y Circulares.",
  "sources": [
    {
      "source": "confluence",
      "page_id": "360450",
      "page_title": "Ditaly Pasta",
      "page_version": 7,
      "chunk_index": 0,
      "score": 0.8654
    }
  ]
}

Incremental Sync Flow

Scheduler or manual request
   |
   v
List Confluence pages
   |
   v
Skip excluded titles
   |
   v
Get current Confluence page_version
   |
   v
Get active Qdrant page_version
   |
   v
If versions match:
   skip page
   |
   v
If versions differ:
   clean HTML
   split into chunks
   create embeddings
   save new chunks as active
   deactivate old chunks
   cleanup old inactive versions

Versioning Strategy

Each indexed chunk contains metadata:

{
  "source": "confluence",
  "page_id": "360450",
  "page_title": "Ditaly Pasta",
  "page_version": 7,
  "sync_run_id": "uuid",
  "chunk_index": 0,
  "is_active": true
}

The RAG search only uses chunks where:

{
  "is_active": true
}

When a new Confluence version is indexed:

new version   → is_active=true
old version   → is_active=false
older versions → cleaned up according to retention policy

Current retention policy:

Keep active version + one previous inactive version.

Scheduler

The scheduler runs automatically when FastAPI starts.

The interval is configured with:

CONFLUENCE_SYNC_INTERVAL_MINUTES=5

Example log:

[SCHEDULER] Running Confluence sync...
[SCHEDULER] Sync result: {
  "status": "sync_completed",
  "indexed_count": 1,
  "skipped_count": 2
}

RAG Behavior

The assistant follows a strict RAG prompt:

* It only answers using retrieved context.
* It does not invent missing information.
* It returns a fallback response when documentation does not contain enough information.
* It includes sources for auditability.

Fallback answer:

No está especificado en la documentación disponible.

Why This Project Matters

This project demonstrates a production-oriented AI backend pattern:

Business documentation
→ automated sync
→ vector search
→ grounded LLM answers
→ auditable sources

It is designed to show practical AI engineering skills beyond basic prompting, including:

* RAG architecture
* external knowledge ingestion
* vector database integration
* incremental sync
* document versioning
* scheduler automation
* LLM grounding
* source traceability
* Dockerized service design

Future Improvements

* Add /rag/query as the production endpoint.
* Add /confluence/sync/status.
* Add structured logs for sync history.
* Add webhook-based Confluence sync.
* Improve chunking by Confluence headings and sections.
* Add authentication for internal API access.
* Add test suite.
* Add frontend or admin dashboard.
* Add support for multiple collections by business domain.

Portfolio Summary

SBM AI Assistant is a RAG-based backend system that keeps business documentation synchronized from Confluence into a vector database and allows users to query it through an AI assistant with grounded, source-aware answers.

