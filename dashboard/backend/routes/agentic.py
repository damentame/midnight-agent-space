"""Phase 0-4 agentic APIs (additive)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..config import app_config
from ..database import DatabaseManager, get_db
from ..services.change_history_service import change_history_service
from ..services.codex_cli_runner import codex_cli_runner
from ..services.document_version_service import document_version_service
from ..services.project_metadata_service import project_metadata_service
from ..services.prompt_template_service import prompt_template_service
from ..services.run_service import run_service
from ..services.runtime_check_service import runtime_check_service

router = APIRouter(prefix="/agentic", tags=["agentic"])


class ProjectMetadataUpdateBody(BaseModel):
    metadata: Optional[Dict[str, Any]] = None
    repository_url: Optional[str] = None
    default_branch: Optional[str] = None
    runtime_preferences: Optional[Dict[str, Any]] = None
    updated_by: Optional[str] = "dashboard"


class DocumentVersionCreateBody(BaseModel):
    version_label: Optional[str] = None
    source: Optional[str] = "manual"
    change_summary: Optional[str] = None
    raw_text_content: Optional[str] = None
    structured_json: Optional[Dict[str, Any]] = None
    content_hash: Optional[str] = None
    created_by: Optional[str] = "dashboard"


class QuickRunBody(BaseModel):
    project_id: int = Field(..., ge=1)
    user_prompt: str = Field(..., min_length=1)
    template_name: str = "quick_run_system_prompt"
    runtime_provider: str = app_config.midnight_default_runtime
    model: Optional[str] = None
    include_change_history: bool = True
    include_document_versions: bool = True
    use_worktree: bool = True
    dry_run: bool = True
    created_by: str = "dashboard"
    output_schema_name: Optional[str] = None


class ParseCodexEventBody(BaseModel):
    lines: List[str] = Field(default_factory=list)


@router.get("/runtime/check")
async def runtime_check():
    return runtime_check_service.runtime_check()


@router.get("/projects/{project_id}/metadata")
async def get_project_metadata(
    project_id: int,
    db: DatabaseManager = Depends(get_db),
):
    data = await project_metadata_service.get_project_metadata(db, project_id)
    if not data:
        raise HTTPException(status_code=404, detail="Project not found")
    return data


@router.put("/projects/{project_id}/metadata")
async def update_project_metadata(
    project_id: int,
    body: ProjectMetadataUpdateBody,
    db: DatabaseManager = Depends(get_db),
):
    data = await project_metadata_service.update_project_metadata(
        db,
        project_id=project_id,
        metadata=body.metadata,
        repository_url=body.repository_url,
        default_branch=body.default_branch,
        runtime_preferences=body.runtime_preferences,
        updated_by=body.updated_by or "dashboard",
    )
    if not data:
        raise HTTPException(status_code=404, detail="Project not found")
    return data


@router.get("/projects/{project_id}/documents/{document_id}/versions")
async def list_document_versions(
    project_id: int,
    document_id: int,
    limit: int = Query(50, ge=1, le=500),
    db: DatabaseManager = Depends(get_db),
):
    project = await db.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return await document_version_service.list_versions(db, project_id, document_id, limit=limit)


@router.post("/projects/{project_id}/documents/{document_id}/versions")
async def create_document_version(
    project_id: int,
    document_id: int,
    body: DocumentVersionCreateBody,
    db: DatabaseManager = Depends(get_db),
):
    project = await db.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    created = await document_version_service.create_version(
        db,
        project_id=project_id,
        document_id=document_id,
        version_label=body.version_label,
        source=body.source,
        change_summary=body.change_summary,
        raw_text_content=body.raw_text_content,
        structured_json=body.structured_json,
        content_hash=body.content_hash,
        created_by=body.created_by or "dashboard",
    )
    if not created:
        raise HTTPException(
            status_code=400,
            detail="document_version table unavailable; apply Phase 0-4 migration first",
        )
    return created


@router.get("/projects/{project_id}/change-history")
async def list_change_history(
    project_id: int,
    limit: int = Query(100, ge=1, le=1000),
    db: DatabaseManager = Depends(get_db),
):
    project = await db.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return await change_history_service.list_changes(db, project_id=project_id, limit=limit)


@router.get("/runs")
async def list_runs(
    project_id: Optional[int] = Query(default=None, ge=1),
    limit: int = Query(default=100, ge=1, le=500),
    db: DatabaseManager = Depends(get_db),
):
    return await run_service.list_runs(db, project_id=project_id, limit=limit)


@router.get("/runs/{run_id}")
async def get_run(
    run_id: int,
    db: DatabaseManager = Depends(get_db),
):
    row = await run_service.get_run(db, run_id=run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")
    return row


@router.get("/runs/{run_id}/events")
async def get_run_events(
    run_id: int,
    limit: int = Query(default=500, ge=1, le=2000),
    db: DatabaseManager = Depends(get_db),
):
    return await run_service.list_run_events(db, run_id=run_id, limit=limit)


@router.get("/runs/{run_id}/events/stream")
async def stream_run_events(
    run_id: int,
    db: DatabaseManager = Depends(get_db),
):
    async def event_generator():
        async for payload in run_service.stream_events(db, run_id=run_id):
            yield payload

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/runs/{run_id}/artifacts")
async def get_run_artifacts(
    run_id: int,
    limit: int = Query(default=200, ge=1, le=1000),
    db: DatabaseManager = Depends(get_db),
):
    return await run_service.list_run_artifacts(db, run_id=run_id, limit=limit)


@router.get("/runs/{run_id}/changes")
async def get_run_changes(
    run_id: int,
    limit: int = Query(default=500, ge=1, le=2000),
    db: DatabaseManager = Depends(get_db),
):
    return await run_service.list_run_git_changes(db, run_id=run_id, limit=limit)


@router.post("/runs/{run_id}/cancel")
async def cancel_run(
    run_id: int,
    db: DatabaseManager = Depends(get_db),
):
    run = await run_service.get_run(db, run_id=run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    project_id = int(run.get("project_id") or 0)
    result = await run_service.cancel_run(db, project_id=project_id, run_id=run_id)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=jsonable_encoder(result))
    return result


@router.post("/runs/{run_id}/retry")
async def retry_run(
    run_id: int,
    db: DatabaseManager = Depends(get_db),
):
    run = await run_service.get_run(db, run_id=run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    project_id = int(run.get("project_id") or 0)
    result = await run_service.retry_run(db, project_id=project_id, run_id=run_id)
    if not result.get("ok") and result.get("errors"):
        raise HTTPException(status_code=400, detail=jsonable_encoder(result))
    return result


@router.post("/quick-runs")
async def create_quick_run(
    body: QuickRunBody,
    db: DatabaseManager = Depends(get_db),
):
    result = await run_service.create_quick_run_plan(
        db,
        project_id=body.project_id,
        user_prompt=body.user_prompt,
        template_name=body.template_name,
        runtime_provider=body.runtime_provider,
        model=body.model,
        include_change_history=body.include_change_history,
        include_document_versions=body.include_document_versions,
        use_worktree=body.use_worktree,
        dry_run=body.dry_run,
        created_by=body.created_by,
        output_schema_name=body.output_schema_name,
    )
    if not result.get("ok") and result.get("errors"):
        raise HTTPException(status_code=400, detail=jsonable_encoder(result))
    return result


@router.get("/prompt-templates")
async def list_prompt_templates():
    return {
        "templates": prompt_template_service.list_prompt_templates(),
        "schemas": prompt_template_service.list_json_schemas(),
    }


@router.get("/prompt-templates/{template_name}")
async def get_prompt_template(template_name: str):
    try:
        return {
            "template_name": template_name,
            "content": prompt_template_service.load_prompt_template(template_name),
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/json-schemas/{schema_name}")
async def get_json_schema(schema_name: str):
    try:
        return prompt_template_service.load_json_schema(schema_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/codex/parse-events")
async def parse_codex_events(body: ParseCodexEventBody):
    return {"events": codex_cli_runner.parse_event_stream(body.lines)}
