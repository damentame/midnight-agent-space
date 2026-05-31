"""Project CRUD."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..database import DatabaseManager, get_db
from ..services.change_history_service import change_history_service
from ..services.schema_support import schema_support

router = APIRouter()


class ProjectResponse(BaseModel):
    project_id: int
    project_name: Optional[str] = None
    project_type: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ProjectCreate(BaseModel):
    project_name: str = Field(..., min_length=1, max_length=255)
    project_type: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = "ACTIVE"


class ProjectUpdate(BaseModel):
    project_name: Optional[str] = None
    project_type: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


class ProjectPatchById(ProjectUpdate):
    project_id: int = Field(..., ge=1)


@router.get("/projects", response_model=List[ProjectResponse])
async def list_projects(
    q: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: DatabaseManager = Depends(get_db),
):
    projects = await db.get_projects(limit=limit, offset=offset)
    if status:
        projects = [p for p in projects if str(p.get("status") or "").upper() == status.upper()]
    if q:
        q_lower = q.lower()
        projects = [
            p
            for p in projects
            if q_lower in str(p.get("project_name") or "").lower()
            or q_lower in str(p.get("description") or "").lower()
            or q_lower in str(p.get("project_type") or "").lower()
        ]
    return [ProjectResponse(**p) for p in projects]


@router.post("/projects", response_model=ProjectResponse)
async def create_project(body: ProjectCreate, db: DatabaseManager = Depends(get_db)):
    row = await db.insert_project(
        project_name=body.project_name,
        project_type=body.project_type,
        description=body.description,
        status=body.status or "ACTIVE",
    )
    return ProjectResponse(**row)


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: int, db: DatabaseManager = Depends(get_db)):
    project = await db.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectResponse(**project)


async def _update_project_row(
    project_id: int,
    body: ProjectUpdate,
    db: DatabaseManager,
) -> ProjectResponse:
    existing = await db.get_project_by_id(project_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")

    data = body.model_dump(exclude_unset=True)
    if not data:
        return ProjectResponse(**existing)

    fields = []
    values: List[Any] = []
    i = 1
    for key, val in data.items():
        if val is not None:
            fields.append(f"{key} = ${i}")
            values.append(val)
            i += 1
    fields.append("updated_at = NOW()")
    values.append(project_id)

    query = f"""
    UPDATE main.project
    SET {", ".join(fields)}
    WHERE project_id = ${i}
    RETURNING project_id, project_name, project_type, description, status, created_at, updated_at
    """
    row = await db.fetch_one(query, *values)
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectResponse(**dict(row))


@router.put("/projects/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: int,
    body: ProjectUpdate,
    db: DatabaseManager = Depends(get_db),
):
    return await _update_project_row(project_id=project_id, body=body, db=db)


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
async def patch_project(
    project_id: int,
    body: ProjectUpdate,
    db: DatabaseManager = Depends(get_db),
):
    return await _update_project_row(project_id=project_id, body=body, db=db)


@router.patch("/projects", response_model=ProjectResponse)
async def patch_project_by_body(
    body: ProjectPatchById,
    db: DatabaseManager = Depends(get_db),
):
    payload = ProjectUpdate(**body.model_dump(exclude={"project_id"}))
    return await _update_project_row(project_id=body.project_id, body=payload, db=db)


@router.post("/projects/{project_id}/archive", response_model=ProjectResponse)
async def archive_project(project_id: int, db: DatabaseManager = Depends(get_db)):
    return await _update_project_row(
        project_id=project_id,
        body=ProjectUpdate(status="ARCHIVED"),
        db=db,
    )


@router.get("/projects/{project_id}/change-history")
async def project_change_history(
    project_id: int,
    limit: int = Query(100, ge=1, le=1000),
    entity_type: Optional[str] = Query(default=None, alias="entityType"),
    entity_id: Optional[int] = Query(default=None, ge=1, alias="entityId"),
    db: DatabaseManager = Depends(get_db),
):
    project = await db.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    normalized_entity_type = entity_type.strip() if entity_type else None
    return await change_history_service.list_changes(
        db,
        project_id=project_id,
        limit=limit,
        entity_type=normalized_entity_type,
        entity_id=entity_id,
    )


@router.get("/projects/{project_id}/summary")
async def project_summary(project_id: int, db: DatabaseManager = Depends(get_db)) -> Dict[str, Any]:
    project = await db.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    doc_count = int(
        await db.fetch_val("SELECT COUNT(*) FROM main.project_document WHERE project_id = $1", project_id) or 0
    )
    task_count = int(await db.fetch_val("SELECT COUNT(*) FROM main.task WHERE project_id = $1", project_id) or 0)
    run_count = 0
    latest_run: Optional[Dict[str, Any]] = None
    if await schema_support.table_exists(db, "agent_run"):
        run_count = int(await db.fetch_val("SELECT COUNT(*) FROM main.agent_run WHERE project_id = $1", project_id) or 0)
        latest = await db.fetch_one(
            """
            SELECT agent_run_id, status, runtime_provider, created_at, updated_at
            FROM main.agent_run
            WHERE project_id = $1
            ORDER BY agent_run_id DESC
            LIMIT 1
            """,
            project_id,
        )
        latest_run = dict(latest) if latest else None

    return {
        "project": project,
        "counts": {
            "documents": doc_count,
            "tasks": task_count,
            "runs": run_count,
        },
        "latest_run": latest_run,
    }
