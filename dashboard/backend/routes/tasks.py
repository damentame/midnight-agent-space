"""Read-only task listing."""
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from ..database import DatabaseManager, get_db

router = APIRouter()


@router.get("/projects/{project_id}/tasks")
async def list_tasks(project_id: int, db: DatabaseManager = Depends(get_db)):
    p = await db.get_project_by_id(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return await db.get_tasks_by_project(project_id)


@router.get("/tasks/{task_id}")
async def get_task(task_id: int, db: DatabaseManager = Depends(get_db)):
    row = await db.fetch_one(
        """
        SELECT task_id, project_id, agent_id, document_id, task_name, task_type,
               description, parameters, status, priority, task_notes, task_data,
               created_at, updated_at
        FROM main.task WHERE task_id = $1
        """,
        task_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    return dict(row)
