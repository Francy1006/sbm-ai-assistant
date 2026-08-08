from __future__ import annotations

import hashlib
from collections.abc import Iterable

from qdrant_client.models import FieldCondition, Filter, MatchValue

from app.config.settings import DOCUMENTATION_EXPORT_TOP_K
from app.services.contexts.models import RetrievedContextChunk
from app.services.documentation.documentation_index_service import (
    DOCUMENTATION_COLLECTION_NAME,
)
from app.services.embedding_service import create_embedding
from app.services.qdrant_service import search_similar


GLOBAL_REPOSITORY = "SBM-SUITE"
DOCUMENTATION_WORKFLOW = "documentation-deploy"

_DOCUMENTATION_DOMAIN_HINTS: tuple[
    tuple[tuple[str, ...], str],
    ...,
] = (
    (
        (
            "readme.md",
            "project_context.md",
            "project-tree.txt",
            "project_tree",
        ),
        (
            "Project overview, current state, architecture, "
            "structure and roadmap"
        ),
    ),
    (
        (
            "qa_context.md",
            "qa-results.md",
            "coverage.xml",
            "sonar",
            "pytest",
            "test_",
            "/tests/",
        ),
        (
            "QA and Testing documentation, coverage, "
            "SonarQube, defects and validation evidence"
        ),
    ),
    (
        (
            "suite_context.md",
            "docker-compose",
            "settings.py",
            "urls.py",
            "views.py",
            "serializers.py",
        ),
        (
            "Architecture, applications, technologies, "
            "APIs, runtime and integrations"
        ),
    ),
    (
        (
            "business_context.md",
            "products/",
            "material/",
            "service/",
            "catalog/",
            "ticket/",
            "pricing/",
            "providers/",
            "branches/",
        ),
        (
            "Business capabilities, entities, brands, "
            "processes and operating rules"
        ),
    ),
    (
        (
            "security_context.md",
            "auth",
            "permission",
            "role",
            "token",
            "cors",
            "secret",
        ),
        (
            "Security and DevSecOps documentation, "
            "identity, authorization, isolation and secrets"
        ),
    ),
    (
        (
            "data_context.md",
            "models.py",
            "flyway",
            "dbml",
            "postgres",
            "migration",
        ),
        (
            "Data Architecture documentation, schemas, "
            "entities, relations, migrations and persistence"
        ),
    ),
    (
        (
            "decisions_context.md",
            "adr",
            "decision",
        ),
        (
            "Architecture and product decisions"
        ),
    ),
    (
        (
            "documentation/",
            "documentation_context",
            "documentation-deploy",
            "documentation-upgrade",
        ),
        (
            "Documentation workflow, governance, "
            "page structure and synchronization"
        ),
    ),
    (
        (
            "context/",
            "context-deploy",
            "context-upgrade",
            "sbm_contexts",
        ),
        (
            "Context workflow and its relationship "
            "with generated documentation"
        ),
    ),
    (
        (
            "embedding",
            "qdrant",
            "rag",
            "tool",
            "llm",
            "ai-assistant",
        ),
        (
            "AI Engineering documentation, RAG, "
            "collections, models and Tools"
        ),
    ),
    (
        (
            "deploy",
            "docker",
            "container",
            "network",
            "health",
            "environment",
        ),
        (
            "DevOps and deployment documentation"
        ),
    ),
)


def _normalized_changed_files(
    changed_files: Iterable[str],
) -> list[str]:
    return [
        file_path.strip()
        for file_path in changed_files
        if file_path and file_path.strip()
    ]


def _documentation_domain_hints(
    changed_files: list[str],
) -> list[str]:
    normalized = [
        file_path.lower()
        for file_path in changed_files
    ]
    hints: list[str] = []

    for patterns, description in _DOCUMENTATION_DOMAIN_HINTS:
        if any(
            pattern in file_path
            for file_path in normalized
            for pattern in patterns
        ):
            hints.append(description)

    return list(dict.fromkeys(hints))


def build_documentation_query(
    project_name: str,
    change_summary: str | None,
    changed_files: list[str],
    git_diff: str,
    qa_results: str,
    documentation_files: list[str] | None = None,
    project_tree: str = "",
) -> str:
    normalized_project_name = project_name.strip()

    if not normalized_project_name:
        raise ValueError(
            "project_name must not be empty"
        )

    normalized_files = _normalized_changed_files(
        changed_files
    )
    normalized_documentation_files = (
        _normalized_changed_files(
            documentation_files or []
        )
    )

    sections = [
        f"Project: {normalized_project_name}",
        (
            "Retrieve documentation relevant to the current "
            "change. Prioritize current state, architecture, "
            "business behavior, APIs, QA, security, data, "
            "deployment, AI engineering, roadmap, related "
            "pages and documentation workflow."
        ),
    ]

    if change_summary and change_summary.strip():
        sections.append(
            "Change summary:\n"
            f"{change_summary.strip()}"
        )

    if normalized_files:
        sections.append(
            "Changed files:\n"
            + "\n".join(normalized_files)
        )

        domain_hints = _documentation_domain_hints(
            normalized_files
        )
        if domain_hints:
            sections.append(
                "Documentation domains probably affected:\n"
                + "\n".join(
                    f"- {hint}"
                    for hint in domain_hints
                )
            )

    if normalized_documentation_files:
        sections.append(
            "Existing authorized documentation files:\n"
            + "\n".join(
                normalized_documentation_files
            )
        )

    if git_diff.strip():
        sections.append(
            f"Git diff:\n{git_diff.strip()}"
        )

    if qa_results.strip():
        sections.append(
            "QA results:\n"
            f"{qa_results.strip()}"
        )

    if project_tree.strip():
        sections.append(
            "Current project structure:\n"
            f"{project_tree.strip()}"
        )

    if len(sections) == 2:
        sections.append(
            "Current change has no additional details."
        )

    return "\n\n".join(sections)


def _scope_filter(
    project_name: str,
    global_scope: bool,
    archive_path: str | None = None,
) -> Filter:
    repository_condition = FieldCondition(
        key="repository",
        match=MatchValue(
            value=GLOBAL_REPOSITORY
        ),
    )
    must = [
        FieldCondition(
            key="project_name",
            match=MatchValue(
                value=project_name
            ),
        ),
        FieldCondition(
            key="workflow",
            match=MatchValue(
                value=DOCUMENTATION_WORKFLOW
            ),
        ),
        FieldCondition(
            key="is_active",
            match=MatchValue(value=True),
        ),
    ]

    if archive_path:
        must.append(
            FieldCondition(
                key="archive_path",
                match=MatchValue(
                    value=archive_path
                ),
            )
        )

    if global_scope:
        must.append(repository_condition)
        return Filter(must=must)

    return Filter(
        must=must,
        must_not=[repository_condition],
    )


def _deduplication_key(
    point,
) -> tuple[str, str, str]:
    payload = point.payload or {}
    text = payload.get("text", "")
    text_hash = hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()

    return (
        payload.get("archive_path", ""),
        payload.get("section", ""),
        text_hash,
    )


def retrieve_relevant_documentation_chunks(
    project_name: str,
    query: str,
    top_k: int = DOCUMENTATION_EXPORT_TOP_K,
    allowed_archive_paths: list[str] | None = None,
    required_archive_paths: list[str] | None = None,
) -> list[RetrievedContextChunk]:
    normalized_project_name = project_name.strip()
    normalized_query = query.strip()

    if not normalized_project_name:
        raise ValueError(
            "project_name must not be empty"
        )

    if not normalized_query:
        raise ValueError(
            "query must not be empty"
        )

    if top_k < 1:
        raise ValueError(
            "top_k must be greater than zero"
        )

    allowed_paths = {
        path.strip()
        for path in (allowed_archive_paths or [])
        if path and path.strip()
    }
    required_paths = {
        path.strip()
        for path in (required_archive_paths or [])
        if path and path.strip()
    }

    if required_paths and not allowed_paths:
        raise ValueError(
            "required_archive_paths require allowed_archive_paths"
        )

    if not required_paths.issubset(allowed_paths):
        raise ValueError(
            "required_archive_paths must be a subset of "
            "allowed_archive_paths"
        )

    if len(required_paths) > top_k:
        raise ValueError(
            "required_archive_paths cannot exceed top_k"
        )

    vector = create_embedding(
        normalized_query
    )
    candidates = []
    search_limit = top_k if not allowed_paths else max(top_k * 4, top_k)

    for global_scope in (True, False):
        candidates.extend(
            search_similar(
                vector=vector,
                limit=search_limit,
                collection_name=(
                    DOCUMENTATION_COLLECTION_NAME
                ),
                query_filter=_scope_filter(
                    project_name=(
                        normalized_project_name
                    ),
                    global_scope=global_scope,
                ),
            )
        )

    candidates.sort(
        key=lambda point: point.score,
        reverse=True,
    )

    unique_chunks: list[
        RetrievedContextChunk
    ] = []
    seen: set[
        tuple[str, str, str]
    ] = set()

    for point in candidates:
        key = _deduplication_key(point)

        if key in seen:
            continue

        payload = point.payload or {}
        archive_path = payload.get(
            "archive_path",
            "",
        )

        if allowed_paths and archive_path not in allowed_paths:
            continue

        seen.add(key)

        unique_chunks.append(
            RetrievedContextChunk(
                point_id=str(point.id),
                source_path=payload.get(
                    "source_path",
                    "",
                ),
                archive_path=payload.get(
                    "archive_path",
                    "",
                ),
                section=payload.get(
                    "section",
                    "",
                ),
                score=float(point.score),
                content=payload.get(
                    "text",
                    "",
                ),
            )
        )

        if len(unique_chunks) >= top_k:
            break

    represented_paths = {
        chunk.archive_path
        for chunk in unique_chunks
    }

    for required_path in sorted(
        required_paths - represented_paths
    ):
        targeted_candidates = []

        for global_scope in (True, False):
            targeted_candidates.extend(
                search_similar(
                    vector=vector,
                    limit=1,
                    collection_name=(
                        DOCUMENTATION_COLLECTION_NAME
                    ),
                    query_filter=_scope_filter(
                        project_name=(
                            normalized_project_name
                        ),
                        global_scope=global_scope,
                        archive_path=required_path,
                    ),
                )
            )

        targeted_candidates.sort(
            key=lambda point: point.score,
            reverse=True,
        )

        selected = None

        for point in targeted_candidates:
            payload = point.payload or {}

            if (
                payload.get("archive_path", "")
                != required_path
            ):
                continue

            key = _deduplication_key(point)

            if key in seen:
                continue

            selected = RetrievedContextChunk(
                point_id=str(point.id),
                source_path=payload.get(
                    "source_path",
                    "",
                ),
                archive_path=payload.get(
                    "archive_path",
                    "",
                ),
                section=payload.get(
                    "section",
                    "",
                ),
                score=float(point.score),
                content=payload.get(
                    "text",
                    "",
                ),
            )
            seen.add(key)
            break

        if selected is None:
            raise ValueError(
                "Required documentation target was not retrieved: "
                f"{required_path}"
            )

        if len(unique_chunks) >= top_k:
            removable_index = next(
                (
                    index
                    for index in range(
                        len(unique_chunks) - 1,
                        -1,
                        -1,
                    )
                    if (
                        unique_chunks[index].archive_path
                        not in required_paths
                    )
                ),
                None,
            )

            if removable_index is None:
                raise ValueError(
                    "Unable to reserve retrieval slot for required "
                    "documentation target: "
                    f"{required_path}"
                )

            unique_chunks.pop(removable_index)

        unique_chunks.append(selected)
        represented_paths.add(required_path)

    unique_chunks.sort(
        key=lambda chunk: chunk.score,
        reverse=True,
    )

    return unique_chunks
