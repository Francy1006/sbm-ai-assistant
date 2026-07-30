import logging

from fastapi import APIRouter, HTTPException

from app.schemas.documentation import (
    DocumentationExportRequest,
    DocumentationExportResponse,
    DocumentationUpgradeResponse,
)
from app.services.contexts.file_discovery_service import (
    ContextValidationError,
)
from app.services.documentation.documentation_export_service import (
    DocumentationExportInfrastructureError,
    export_documentation,
)
from app.services.documentation.documentation_upgrade_service import (
    DocumentationUpgradeOperationalError,
    upgrade_documentation,
)


router = APIRouter(
    prefix="/documentation",
    tags=["Documentation"],
)

logger = logging.getLogger(
    "uvicorn.error.documentation.route"
)
logger.setLevel(logging.INFO)


@router.post(
    "/export",
    response_model=DocumentationExportResponse,
)
def export_documentation_route(
    request: DocumentationExportRequest,
) -> DocumentationExportResponse:
    try:
        logger.info(
            "[DOCUMENTATION_EXPORT] route start project=%s",
            request.project_name,
        )
        response = export_documentation(request)
        logger.info(
            "[DOCUMENTATION_EXPORT] route return project=%s status=%s",
            response.project_name,
            response.status,
        )
        return response
    except ContextValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
    except DocumentationExportInfrastructureError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc


@router.post(
    "/upgrade",
    response_model=DocumentationUpgradeResponse,
)
def upgrade_documentation_route(
) -> DocumentationUpgradeResponse:
    try:
        logger.info(
            "[DOCUMENTATION_UPGRADE] route start"
        )
        response = upgrade_documentation()
        logger.info(
            "[DOCUMENTATION_UPGRADE] route return "
            "project=%s files=%d",
            response.project_name,
            len(response.updated_files),
        )
        return response
    except ContextValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
    except DocumentationUpgradeOperationalError as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc
