import re
from typing import Iterator, List, Tuple

from app.services.chunk_service import split_text_into_chunks
from app.services.documentation.models import DocumentationChunk


HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def _documentation_sections(
    text: str,
    default_section: str,
) -> Iterator[Tuple[str, str]]:
    current_section = default_section
    current_lines: List[str] = []

    for line in text.splitlines():
        heading = HEADING_PATTERN.match(line)

        if heading and current_lines:
            yield (
                current_section,
                "\n".join(current_lines).strip(),
            )
            current_lines = []

        if heading:
            current_section = heading.group(2).strip()

        current_lines.append(line)

    if current_lines:
        yield (
            current_section,
            "\n".join(current_lines).strip(),
        )


def split_documentation_markdown(
    text: str,
    default_section: str,
) -> List[DocumentationChunk]:
    chunks: List[DocumentationChunk] = []

    for section, section_text in _documentation_sections(
        text,
        default_section,
    ):
        for content in split_text_into_chunks(
            section_text
        ):
            chunks.append(
                DocumentationChunk(
                    content=content,
                    section=section,
                    chunk_index=len(chunks),
                )
            )

    return chunks
