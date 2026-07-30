import re

from app.services.chunk_service import split_text_into_chunks
from app.services.contexts.models import MarkdownChunk


HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def _markdown_sections(text: str, default_section: str):
    current_section = default_section
    current_lines: list[str] = []

    for line in text.splitlines():
        heading = HEADING_PATTERN.match(line)

        if heading and current_lines:
            yield current_section, "\n".join(current_lines).strip()
            current_lines = []

        if heading:
            current_section = heading.group(2).strip()

        current_lines.append(line)

    if current_lines:
        yield current_section, "\n".join(current_lines).strip()


def split_markdown_into_chunks(
    text: str,
    default_section: str,
) -> list[MarkdownChunk]:
    chunks: list[MarkdownChunk] = []

    for section, section_text in _markdown_sections(text, default_section):
        for content in split_text_into_chunks(section_text):
            chunks.append(
                MarkdownChunk(
                    content=content,
                    section=section,
                    chunk_index=len(chunks),
                )
            )

    return chunks
