"""Workflow runs and optional Temporal start (MVP)."""
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..database import DatabaseManager, get_db

router = APIRouter()


@router.get("/workflows/runs")
async def list_workflow_runs(
    project_id: Optional[int] = None,
    limit: int = 100,
    db: DatabaseManager = Depends(get_db),
):
    return await db.get_workflow_runs(project_id=project_id, limit=limit)


class StartWorkflowBody(BaseModel):
    agent_id: int = Field(..., ge=1)
    project_id: int = Field(..., ge=1)
    agent_provider: str = "cursor"
    execute_mode: str = "fast"
    concurrent_tasks: bool = False
    batch_tasks: bool = False
    require_human_review: bool = False


@router.post("/workflows/start")
async def start_workflow(body: StartWorkflowBody) -> Dict[str, Any]:
    if body.agent_provider not in ("cursor", "codex", "claude-code"):
        raise HTTPException(status_code=400, detail="invalid agent_provider")
    if body.execute_mode not in ("fast", "complex"):
        raise HTTPException(status_code=400, detail="invalid execute_mode")
    if body.concurrent_tasks and body.batch_tasks:
        raise HTTPException(
            status_code=400,
            detail="concurrent_tasks and batch_tasks cannot both be true",
        )
    root = Path(__file__).resolve().parent.parent.parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        from temporal.client import start_document_serialization
    except ImportError as e:
        raise HTTPException(
            status_code=501,
            detail=f"Temporal client not available: {e}",
        ) from e

    import asyncio

    try:
        wid = await start_document_serialization(
            agent_id=body.agent_id,
            project_id=body.project_id,
            agent_provider=body.agent_provider,
            require_human_review=body.require_human_review,
            concurrent_tasks=body.concurrent_tasks,
            execute_mode=body.execute_mode,
            batch_tasks=body.batch_tasks,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    return {"workflow_id": wid, "message": "Document serialization workflow started"}
