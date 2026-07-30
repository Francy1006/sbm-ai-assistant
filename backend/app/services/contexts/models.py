from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ContextSource:
    source_path: Path
    archive_path: str
    context_type: str
    repository: str
    legacy_source_path: str | None = None


@dataclass(frozen=True)
class MarkdownChunk:
    content: str
    section: str
    chunk_index: int


@dataclass(frozen=True)
class RetrievedContextChunk:
    point_id: str
    source_path: str
    archive_path: str
    section: str
    score: float
    content: str


@dataclass(frozen=True)
class FullContextFile:
    source_path: Path
    archive_path: str
    content: str
