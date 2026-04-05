"""Temporal: list executions, snapshot history, resolve DB workflow_run → Temporal id."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..database import DatabaseManager, get_db
from ..temporal_service import fetch_workflow_snapshot, list_recent_workflows

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/temporal", tags=["temporal"])


def _guess_temporal_workflow_id(row: Dict[str, Any]) -> tuple[Optional[str], str]:
    inp = row.get("input_data") or {}
    if isinstance(inp, str):
        try:
            inp = json.loads(inp)
        except Exception:
            inp = {}
    if not isinstance(inp, dict):
        inp = {}
    pid = row.get("project_id") if row.get("project_id") is not None else inp.get("project_id")
    aid = inp.get("agent_id")
    wname = (row.get("workflow_name") or "").strip()

    if wname == "DocumentSerializationWorkflow" and pid is not None and aid is not None:
        return f"document-serialization-{pid}-{aid}", ""
    if wname == "TaskExecutionWorkflow" and pid is not None and aid is not None:
        return f"task-execution-{pid}-{aid}", ""
    return (
        None,
        "Could not derive a Temporal workflow id from this row (child workflows use ids like "
        "task-exec-{project_id}-{parent_run_id}). Paste a workflow id from Temporal UI.",
    )


@router.get("/executions")
async def temporal_list_executions(
    page_size: int = Query(50, ge=1, le=200),
):
    try:
        return await list_recent_workflows(page_size=page_size)
    except Exception as e:
        logger.exception("temporal list failed")
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/executions/{workflow_id}/snapshot")
async def temporal_snapshot(
    workflow_id: str,
    run_id: Optional[str] = Query(None),
):
    try:
        return await fetch_workflow_snapshot(workflow_id, run_id=run_id)
    except Exception as e:
        logger.exception("snapshot failed")
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/workflow-runs/{workflow_run_id}/target")
async def temporal_target_from_db_row(
    workflow_run_id: int,
    db: DatabaseManager = Depends(get_db),
):
    row = await db.get_workflow_run_by_id(workflow_run_id)
    if not row:
        raise HTTPException(status_code=404, detail="workflow_run not found")
    wid, note = _guess_temporal_workflow_id(row)
    return {
        "workflow_run_id": workflow_run_id,
        "workflow_name": row.get("workflow_name"),
        "project_id": row.get("project_id"),
        "derived_workflow_id": wid,
        "hint": note,
        "input_data": row.get("input_data"),
    }
