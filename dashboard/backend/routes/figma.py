"""Legacy Figma router paths (kept for compatibility)."""
from fastapi import APIRouter, Depends

from ..database import DatabaseManager, get_db
from .figma_handlers import (
    FigmaImportBody,
    FigmaTokenBody,
    import_figma_design_handler,
    reimport_figma_for_project,
    validate_figma_token_handler,
)

router = APIRouter()


@router.post("/figma/validate-token")
async def validate_figma_token(body: FigmaTokenBody):
    return await validate_figma_token_handler(body)


@router.post("/projects/{project_id}/figma/import")
async def import_figma_design(
    project_id: int,
    body: FigmaImportBody,
    db: DatabaseManager = Depends(get_db),
):
    return await import_figma_design_handler(project_id, body, db)


@router.post("/projects/{project_id}/figma/reimport")
async def reimport_figma_design(
    project_id: int,
    body: FigmaImportBody,
    db: DatabaseManager = Depends(get_db),
):
    try:
        return await reimport_figma_for_project(
            db,
            project_id=project_id,
            url=body.url,
            token=body.token,
            notes=body.notes,
        )
    except ValueError as e:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail=str(e)) from e
