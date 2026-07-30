from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class DocumentationSource:
    source_path: Path
    archive_path: str
    documentation_type: str
    repository: str
    legacy_source_path: Optional[str] = None


@dataclass(frozen=True)
class DocumentationChunk:
    content: str
    section: str
    chunk_index: int


@dataclass(frozen=True)
class DocumentationFile:
    source_path: Path
    archive_path: str
    content: str
