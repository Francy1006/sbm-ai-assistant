from __future__ import annotations

import hashlib
from collections.abc import Iterable

from qdrant_client.models import FieldCondition, Filter, MatchValue

from app.config.settings import CONTEXT_EXPORT_TOP_K
from app.services.contexts.context_index_service import (
    CONTEXT_COLLECTION_NAME,
)
from app.services.contexts.models import RetrievedContextChunk
from app.services.embedding_service import create_embedding
from app.services.qdrant_service import search_similar


GLOBAL_REPOSITORY = "SBM-SUITE"
CONTEXT_WORKFLOW = "context-deploy"

_CONTEXT_DOMAIN_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        (
            "project_context.md",
            "readme.md",
            "project-tree.txt",
            "project_tree",
        ),
        "Estado del proyecto, objetivos, arquitectura, estructura y trabajo pendiente",
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
        "QA, pruebas, cobertura, SonarQube, defectos, riesgos y evidencia",
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
        "Arquitectura de la suite, aplicaciones, tecnologías, APIs e integraciones",
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
        "Marcas, capacidades, entidades y reglas de negocio",
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
        "Seguridad, identidad, autorización, aislamiento y secretos",
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
        "Datos, esquemas, entidades, relaciones, migraciones y persistencia",
    ),
    (
        (
            "decisions_context.md",
            "adr",
            "decision",
        ),
        "Decisiones de arquitectura y producto",
    ),
    (
        (
            "documentation/",
            "documentation_context",
        ),
        "Relación entre contextos y documentación",
    ),
)


def _normalized_changed_files(changed_files: Iterable[str]) -> list[str]:
    return [
        file_path.strip()
        for file_path in changed_files
        if file_path and file_path.strip()
    ]


def _change_domain_hints(changed_files: list[str]) -> list[str]:
    normalized = [file_path.lower() for file_path in changed_files]
    hints: list[str] = []

    for patterns, description in _CONTEXT_DOMAIN_HINTS:
        if any(
            pattern in file_path
            for file_path in normalized
            for pattern in patterns
        ):
            hints.append(description)

    return list(dict.fromkeys(hints))


def build_context_query(
    project_name: str,
    change_summary: str | None,
    changed_files: list[str],
    git_diff: str,
    qa_results: str,
    project_tree: str = "",
) -> str:
    normalized_project_name = project_name.strip()

    if not normalized_project_name:
        raise ValueError("project_name must not be empty")

    normalized_files = _normalized_changed_files(changed_files)
    sections = [
        f"Proyecto: {normalized_project_name}",
        (
            "Recuperar contexto global y específico del proyecto. "
            "Priorizar estado actual, objetivos activos, arquitectura, APIs, "
            "reglas de negocio, QA, seguridad, datos, decisiones y "
            "sincronización transversal afectados por el cambio."
        ),
    ]

    if change_summary and change_summary.strip():
        sections.append(
            f"Resumen del cambio:\n{change_summary.strip()}"
        )

    if normalized_files:
        sections.append(
            "Archivos modificados:\n" + "\n".join(normalized_files)
        )

        domain_hints = _change_domain_hints(normalized_files)
        if domain_hints:
            sections.append(
                "Dominios de contexto probablemente afectados:\n"
                + "\n".join(f"- {hint}" for hint in domain_hints)
            )

    if git_diff.strip():
        sections.append(f"Diff Git:\n{git_diff.strip()}")

    if qa_results.strip():
        sections.append(
            f"Resultados QA:\n{qa_results.strip()}"
        )

    if project_tree.strip():
        sections.append(
            "Estructura actual del proyecto:\n"
            f"{project_tree.strip()}"
        )

    if len(sections) == 2:
        sections.append("Cambio actual sin detalles adicionales.")

    return "\n\n".join(sections)


def _scope_filter(
    project_name: str,
    global_scope: bool,
) -> Filter:
    repository_condition = FieldCondition(
        key="repository",
        match=MatchValue(value=GLOBAL_REPOSITORY),
    )
    must = [
        FieldCondition(
            key="project_name",
            match=MatchValue(value=project_name),
        ),
        FieldCondition(
            key="workflow",
            match=MatchValue(value=CONTEXT_WORKFLOW),
        ),
        FieldCondition(
            key="is_active",
            match=MatchValue(value=True),
        ),
    ]

    if global_scope:
        must.append(repository_condition)
        return Filter(must=must)

    return Filter(
        must=must,
        must_not=[repository_condition],
    )


def _deduplication_key(point) -> tuple[str, str, str]:
    payload = point.payload or {}
    text = payload.get("text", "")
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return (
        payload.get("archive_path", ""),
        payload.get("section", ""),
        text_hash,
    )


def retrieve_relevant_context_chunks(
    project_name: str,
    query: str,
    top_k: int = CONTEXT_EXPORT_TOP_K,
) -> list[RetrievedContextChunk]:
    normalized_project_name = project_name.strip()
    normalized_query = query.strip()

    if not normalized_project_name:
        raise ValueError("project_name must not be empty")

    if not normalized_query:
        raise ValueError("query must not be empty")

    if top_k < 1:
        raise ValueError("top_k must be greater than zero")

    vector = create_embedding(normalized_query)
    candidates = []

    for global_scope in (True, False):
        candidates.extend(
            search_similar(
                vector=vector,
                limit=top_k,
                collection_name=CONTEXT_COLLECTION_NAME,
                query_filter=_scope_filter(
                    project_name=normalized_project_name,
                    global_scope=global_scope,
                ),
            )
        )

    candidates.sort(key=lambda point: point.score, reverse=True)
    unique_chunks: list[RetrievedContextChunk] = []
    seen: set[tuple[str, str, str]] = set()

    for point in candidates:
        key = _deduplication_key(point)

        if key in seen:
            continue

        seen.add(key)
        payload = point.payload or {}
        unique_chunks.append(
            RetrievedContextChunk(
                point_id=str(point.id),
                source_path=payload.get("source_path", ""),
                archive_path=payload.get("archive_path", ""),
                section=payload.get("section", ""),
                score=float(point.score),
                content=payload.get("text", ""),
            )
        )

        if len(unique_chunks) >= top_k:
            break

    return unique_chunks
