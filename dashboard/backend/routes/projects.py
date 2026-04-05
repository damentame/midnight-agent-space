"""Project CRUD."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..database import DatabaseManager, get_db

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


@router.get("/projects", response_model=List[ProjectResponse])
async def list_projects(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: DatabaseManager = Depends(get_db),
):
    projects = await db.get_projects(limit=limit, offset=offset)
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


@router.put("/projects/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: int,
    body: ProjectUpdate,
    db: DatabaseManager = Depends(get_db),
):
    existing = await db.get_project_by_id(project_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")

    data = body.model_dump(exclude_unset=True)
    if not data:
        return ProjectResponse(**existing)

    fields = []
    values: List = []
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
