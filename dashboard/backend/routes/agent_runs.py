from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..config import app_config
from ..database import DatabaseManager, get_db
from ..services.model_routing_service import model_catalog
from ..services.run_service import run_service
from ..services.runtime_check_service import runtime_check_service
from .figma_handlers import FigmaTokenBody, validate_figma_token_handler

router = APIRouter()


class ProjectQuickRunBody(BaseModel):
    user_prompt: str = Field(..., min_length=1)
    template_name: str = "quick_run_system_prompt"
    runtime_provider: str = app_config.midnight_default_runtime
    reviewer_provider: Optional[str] = None
    model: Optional[str] = None
    model_selection_mode: str = "optimized"
    include_change_history: bool = True
    include_document_versions: bool = True
    use_worktree: bool = True
    execute: bool = False
    dry_run: Optional[bool] = None
    created_by: str = "dashboard"
    output_schema_name: Optional[str] = None


@router.get("/settings/runtimes")
async def runtime_settings_check():
    return runtime_check_service.runtime_check()


@router.get("/settings/models")
async def model_settings():
    return model_catalog()


@router.post("/settings/figma/validate-token")
async def settings_validate_figma_token(body: FigmaTokenBody):
    """Validate a Figma personal access token (Settings UI)."""
    return await validate_figma_token_handler(body)


@router.get("/projects/{project_id}/runs")
async def list_project_runs(
    project_id: int,
    limit: int = Query(100, ge=1, le=500),
    db: DatabaseManager = Depends(get_db),
):
    return await run_service.list_runs(db, project_id=project_id, limit=limit)


@router.get("/projects/{project_id}/runs/{run_id}")
async def get_project_run(
    project_id: int,
    run_id: int,
    db: DatabaseManager = Depends(get_db),
):
    run = await run_service.get_run(db, run_id=run_id)
    if not run or int(run.get("project_id") or 0) != project_id:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.post("/projects/{project_id}/runs/start")
async def start_project_run(
    project_id: int,
    body: ProjectQuickRunBody,
    db: DatabaseManager = Depends(get_db),
):
    dry_run = body.dry_run if body.dry_run is not None else (not body.execute)
    result = await run_service.create_quick_run_plan(
        db,
        project_id=project_id,
        user_prompt=body.user_prompt,
        template_name=body.template_name,
        runtime_provider=body.runtime_provider,
        model=body.model,
        model_selection_mode=body.model_selection_mode,
        include_change_history=body.include_change_history,
        include_document_versions=body.include_document_versions,
        use_worktree=body.use_worktree,
        dry_run=dry_run,
        created_by=body.created_by,
        output_schema_name=body.output_schema_name,
        reviewer_provider=body.reviewer_provider,
    )
    if not result.get("ok") and result.get("errors") and not (result.get("run") or {}).get("agent_run_id"):
        raise HTTPException(status_code=400, detail=jsonable_encoder(result))
    return result


@router.post("/projects/{project_id}/quick-runs")
async def start_project_quick_run(
    project_id: int,
    body: ProjectQuickRunBody,
    db: DatabaseManager = Depends(get_db),
):
    return await start_project_run(project_id=project_id, body=body, db=db)


@router.post("/projects/{project_id}/runs/{run_id}/cancel")
async def cancel_project_run(
    project_id: int,
    run_id: int,
    db: DatabaseManager = Depends(get_db),
):
    result = await run_service.cancel_run(db, project_id=project_id, run_id=run_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error") or "Unable to cancel run")
    return result


@router.post("/projects/{project_id}/runs/{run_id}/reconcile")
async def reconcile_project_run(
    project_id: int,
    run_id: int,
    db: DatabaseManager = Depends(get_db),
):
    """Repair task/run rows when execution finished in events but DB finalization failed."""
    result = await run_service.reconcile_run(db, project_id=project_id, run_id=run_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error") or "Unable to reconcile run")
    return result


class RunCleanupBody(BaseModel):
    delete_record: bool = True


@router.post("/projects/{project_id}/runs/{run_id}/cleanup")
async def cleanup_project_run(
    project_id: int,
    run_id: int,
    body: RunCleanupBody = RunCleanupBody(),
    db: DatabaseManager = Depends(get_db),
):
    """Remove worktree/branch/run artifacts via git (no agent). Optionally delete the run record."""
    result = await run_service.cleanup_run(
        db,
        project_id=project_id,
        run_id=run_id,
        delete_record=body.delete_record,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "Cleanup failed")
    return result


@router.post("/projects/{project_id}/runs/{run_id}/retry")
async def retry_project_run(
    project_id: int,
    run_id: int,
    db: DatabaseManager = Depends(get_db),
):
    result = await run_service.retry_run(db, project_id=project_id, run_id=run_id)
    if not result.get("ok") and result.get("errors"):
        raise HTTPException(status_code=400, detail=jsonable_encoder(result))
    return result


@router.get("/projects/{project_id}/runs/{run_id}/events")
async def list_project_run_events(
    project_id: int,
    run_id: int,
    limit: int = Query(500, ge=1, le=2000),
    mode: str = Query("timeline", description="timeline preserves lifecycle events; full uses raw limit"),
    db: DatabaseManager = Depends(get_db),
):
    run = await run_service.get_run(db, run_id=run_id)
    if not run or int(run.get("project_id") or 0) != project_id:
        raise HTTPException(status_code=404, detail="Run not found")
    return await run_service.list_run_events(db, run_id=run_id, limit=limit, mode=mode)


@router.get("/projects/{project_id}/runs/{run_id}/events/stream")
async def stream_project_run_events(
    project_id: int,
    run_id: int,
    db: DatabaseManager = Depends(get_db),
):
    run = await run_service.get_run(db, run_id=run_id)
    if not run or int(run.get("project_id") or 0) != project_id:
        raise HTTPException(status_code=404, detail="Run not found")

    async def event_generator():
        async for payload in run_service.stream_events(db, run_id=run_id):
            yield payload

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/projects/{project_id}/runs/{run_id}/artifacts")
async def list_project_run_artifacts(
    project_id: int,
    run_id: int,
    limit: int = Query(200, ge=1, le=1000),
    db: DatabaseManager = Depends(get_db),
):
    run = await run_service.get_run(db, run_id=run_id)
    if not run or int(run.get("project_id") or 0) != project_id:
        raise HTTPException(status_code=404, detail="Run not found")
    return await run_service.list_run_artifacts(db, run_id=run_id, limit=limit)


@router.get("/projects/{project_id}/runs/{run_id}/changes")
async def list_project_run_git_changes(
    project_id: int,
    run_id: int,
    limit: int = Query(500, ge=1, le=2000),
    db: DatabaseManager = Depends(get_db),
):
    run = await run_service.get_run(db, run_id=run_id)
    if not run or int(run.get("project_id") or 0) != project_id:
        raise HTTPException(status_code=404, detail="Run not found")
    return await run_service.list_run_git_changes(db, run_id=run_id, limit=limit)
