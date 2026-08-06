import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.schemas.contexts import (
    ContextExportRequest,
    ContextExportResponse,
    ContextContractResponse,
    ContextUpgradeResponse,
)
from app.config.settings import CONTEXT_UPGRADE_SUITE_CONTEXT_ROOT
from app.services.contexts.contract_registry import contract_descriptor
from app.services.contexts.context_export_service import (
    ContextExportInfrastructureError,
    export_contexts,
)
from app.services.contexts.file_discovery_service import (
    ContextValidationError,
)
from app.services.contexts.context_upgrade_service import (
    ContextUpgradeOperationalError,
    upgrade_contexts,
)


router = APIRouter(
    prefix="/contexts",
    tags=["Contexts"],
)
logger = logging.getLogger("uvicorn.error.context_export.route")
logger.setLevel(logging.INFO)


def _runtime_contract() -> dict:
    format_path = (
        Path(CONTEXT_UPGRADE_SUITE_CONTEXT_ROOT) / "FORMAT_CONTEXT.md"
    )
    try:
        format_markdown = format_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ContextValidationError(
            f"Unable to read runtime FORMAT_CONTEXT.md: {format_path}"
        ) from exc
    return contract_descriptor(format_markdown)


try:
    logger.info(
        "[CONTEXT_CONTRACT] runtime contract_version=%s",
        _runtime_contract()["contract_version"],
    )
except ContextValidationError:
    logger.exception("[CONTEXT_CONTRACT] runtime contract unavailable")


@router.get(
    "/contract",
    response_model=ContextContractResponse,
)
def context_contract_route() -> ContextContractResponse:
    try:
        return ContextContractResponse(**_runtime_contract())
    except ContextValidationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post(
    "/export",
    response_model=ContextExportResponse,
)
def export_contexts_route(
    request: ContextExportRequest,
) -> ContextExportResponse:
    try:
        logger.info(
            "[CONTEXT_EXPORT] route start project=%s phase=%s objective=%s",
            request.project_name,
            request.lifecycle_phase,
            request.objective_id,
        )
        response = export_contexts(request)
        logger.info(
            "[CONTEXT_EXPORT] route return project=%s status=%s "
            "phase=%s objective=%s",
            response.project_name,
            response.status,
            response.lifecycle_phase,
            response.objective_id,
        )
        return response
    except ContextValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ContextExportInfrastructureError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post(
    "/upgrade",
    response_model=ContextUpgradeResponse,
)
def upgrade_contexts_route() -> ContextUpgradeResponse:
    try:
        logger.info("[CONTEXT_UPGRADE] route start")
        response = upgrade_contexts()
        logger.info(
            "[CONTEXT_UPGRADE] route return project=%s files=%d",
            response.project_name,
            len(response.updated_files),
        )
        return response
    except ContextValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ContextUpgradeOperationalError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
