import logging

from fastapi import APIRouter, HTTPException

from app.schemas.contexts import (
    ContextExportRequest,
    ContextExportResponse,
    ContextUpgradeResponse,
)
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


@router.post(
    "/export",
    response_model=ContextExportResponse,
)
def export_contexts_route(
    request: ContextExportRequest,
) -> ContextExportResponse:
    try:
        logger.info(
            "[CONTEXT_EXPORT] route start project=%s",
            request.project_name,
        )
        response = export_contexts(request)
        logger.info(
            "[CONTEXT_EXPORT] route return project=%s status=%s",
            response.project_name,
            response.status,
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
