"""Project CRUD."""
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..config import app_config
from ..database import DatabaseManager, get_db
from ..services.agent_effort_service import estimate_agent_effort
from ..services.change_history_service import change_history_service
from ..services.codebase_serialization_service import codebase_serialization_service
from ..services.context_pack_service import context_pack_service
from ..services.git_worktree_service import git_worktree_service
from ..services.jsonb_utils import jsonb_dumps
from ..services.preview_detection_service import preview_detection_service
from ..services.progress_service import progress_service
from ..services.project_metadata_service import project_metadata_service
from ..services.project_refresh_service import project_refresh_service
from ..services.repo_workspace_service import default_projects_parent, repo_workspace_service
from ..services.runtime_check_service import runtime_check_service
from ..services.schema_support import schema_support
from ..services.design_context_service import design_context_service
from ..services.task_execution_plan_service import (
    annotate_task_execution_fields,
    assign_milestones,
    build_execution_batches,
)
from ..services.token_usage_service import token_usage_service
from ..services.verification_service import verification_service

router = APIRouter()


async def _resolve_repo_and_preview(
    db: DatabaseManager,
    *,
    project_id: int,
    project_name: str,
    runtime_preferences: Dict[str, Any],
    persist: bool = False,
    force_detect: bool = False,
) -> tuple[str, Dict[str, Any], Optional[Dict[str, Any]]]:
    prefs = dict(runtime_preferences or {})
    prefs = preview_detection_service._clear_invalid_preview_prefs(prefs)
    repo_path = preview_detection_service.resolve_repo_path(
        runtime_preferences=prefs,
        project_name=project_name,
    )
    detection: Optional[Dict[str, Any]] = None
    if repo_path:
        prefs, detection = preview_detection_service.apply_to_runtime_preferences(
            prefs,
            repo_path=repo_path,
            force=force_detect or not bool(prefs.get("preview_command")),
            project_id=project_id,
        )
    if persist and repo_path and detection and detection.get("ok"):
        metadata = await project_metadata_service.get_project_metadata(db, project_id)
        await project_metadata_service.update_project_metadata(
            db,
            project_id=project_id,
            metadata=metadata.get("metadata") if isinstance(metadata.get("metadata"), dict) else None,
            repository_url=metadata.get("repository_url"),
            default_branch=metadata.get("default_branch"),
            runtime_preferences=prefs,
            updated_by="dashboard-preview",
        )
    return repo_path, prefs, detection


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


class AgentRole(BaseModel):
    role: str
    purpose: str
    model: Optional[str] = None
    max_iterations: int = 1
    sandbox_mode: str = "workspace-write"
    approval_mode: str = "never"


class AnalysisPlanBody(BaseModel):
    goal: str = Field(..., min_length=1)
    repo_path: Optional[str] = None
    repository_url: Optional[str] = None
    default_branch: Optional[str] = "main"
    preview_command: Optional[str] = None
    preview_url: Optional[str] = None
    acceptance_criteria: List[str] = Field(default_factory=list)
    team: List[AgentRole] = Field(default_factory=list)
    execution_parameters: Dict[str, Any] = Field(default_factory=dict)
    manual_edit_instructions: Optional[str] = None


def _default_agent_team() -> List[Dict[str, Any]]:
    return [
        {
            "role": "Planner",
            "purpose": "Analyze documents and convert requirements into ordered implementation tasks.",
            "model": "default",
            "max_iterations": 1,
            "sandbox_mode": "workspace-write",
            "approval_mode": "never",
        },
        {
            "role": "Implementer",
            "purpose": "Execute code changes inside the configured repo/worktree.",
            "model": "default",
            "max_iterations": 3,
            "sandbox_mode": "workspace-write",
            "approval_mode": "never",
        },
        {
            "role": "Reviewer",
            "purpose": "Check output against acceptance criteria and recommend refactors.",
            "model": "default",
            "max_iterations": 1,
            "sandbox_mode": "workspace-write",
            "approval_mode": "never",
        },
    ]


def _planned_tasks(
    goal: str,
    document_count: int,
    asset_count: int,
    *,
    has_figma_import: bool = False,
    design_sections: Optional[List[Dict[str, Any]]] = None,
    execution_mode: str = "standard",
) -> List[Dict[str, Any]]:
    sections = design_sections or []
    design_clause = (
        " Match Figma v2 staged in `.midnight/design/` — use sections/, assets/, tokens.css only."
        if has_figma_import
        else ""
    )
    drafts: List[Dict[str, Any]] = [
        {
            "task_name": "Analyze design context" if has_figma_import else "Analyze uploaded context",
            "task_type": "analysis",
            "description": (
                f"Read {document_count} project documents and {asset_count} design assets for: {goal}."
                + (
                    " Read DESIGN_MANIFEST.md, tokens.css, ASSET_MANIFEST.json, and all section specs."
                    if has_figma_import
                    else ""
                )
            ),
            "priority": 10,
        },
        {
            "task_name": "Plan section implementation" if has_figma_import else "Create implementation plan",
            "task_type": "planning",
            "description": (
                "Produce an ordered task plan with dependencies, acceptance criteria, and runtime parameters."
                + (
                    f" Plan {len(sections)} Figma sections with per-section acceptance criteria."
                    if has_figma_import and sections
                    else (" Include design-fidelity acceptance criteria." if has_figma_import else "")
                )
            ),
            "priority": 20,
        },
    ]

    if execution_mode == "milestones":
        drafts.append(
            {
                "task_name": "Scaffold project skeleton",
                "task_type": "scaffold",
                "description": (
                    "Create the full file/folder structure, navigation shell, routing, and "
                    "placeholder sections/components for every planned page/section so each "
                    "milestone has a runnable preview. Use design tokens/skeleton CSS where "
                    "available; content can be placeholder."
                    + design_clause
                ),
                "priority": 25,
            }
        )

    if has_figma_import and len(sections) > 1:
        ordered = sorted(
            sections,
            key=lambda s: (
                int(s.get("order") or 999),
                float((s.get("box") or {}).get("y") or 0) if isinstance(s.get("box"), dict) else 0,
            ),
        )
        for idx, sec in enumerate(ordered):
            slug = str(sec.get("slug") or f"section-{idx + 1}")
            name = str(sec.get("name") or slug)
            role = str(sec.get("section_role") or "content_section")
            order = sec.get("order") or idx + 1
            drafts.append(
                {
                    "task_name": f"Implement section {order}: {slug}",
                    "task_type": "implementation",
                    "description": (
                        f"Implement section '{name}' (order {order}, inferred role: {role}) using "
                        f"sections/{slug}.json semantic_elements[].box, sections/{slug}.layout.css, "
                        f"and assets from ASSET_MANIFEST.json (match by node_id). "
                        f"Write partials/sections/{slug}.html and css/sections/{slug}.css. "
                        f"Use sections/{slug}.png for verification only. Add data-section=\"{slug}\"."
                        + design_clause
                    ),
                    "priority": 30,
                    "task_data": {
                        "design_section_slug": slug,
                        "design_section_order": order,
                        "goal": goal,
                        "parallel_group": "sections",
                        "parallel_safe": True,
                    },
                }
            )
        drafts.append(
            {
                "task_name": "Integrate sections and assets",
                "task_type": "implementation",
                "description": (
                    "Merge partials/sections/*.html into index.html, import css/sections/*.css, "
                    "wire global CSS tokens.css, copy assets to public/, ensure all section landmarks exist."
                    + design_clause
                ),
                "priority": 40,
            }
        )
    else:
        drafts.append(
            {
                "task_name": "Execute repo changes",
                "task_type": "implementation",
                "description": "Apply code edits in the configured repo/worktree using the approved agent team."
                + design_clause,
                "priority": 30,
            }
        )

    drafts.append(
        {
            "task_name": "Review, refactor, and preview",
            "task_type": "review",
            "description": (
                "Run design fidelity review, refactor if needed, launch preview."
                + design_clause
            ),
            "priority": 50,
        }
    )
    tasks: List[Dict[str, Any]] = []
    for draft in drafts:
        effort = estimate_agent_effort(
            task_name=draft["task_name"],
            task_type=draft["task_type"],
            description=draft["description"],
        )
        tasks.append({**draft, "agent_effort": effort})
    return tasks


async def _serialize_project_documents(
    db: DatabaseManager,
    project_id: int,
) -> Dict[str, Any]:
    rows = await db.fetch_many(
        """
        SELECT document_id, document_name, document_type, raw_text_content, file_extension,
               file_mime_type, file_size_bytes, serialization_status
        FROM main.project_document
        WHERE project_id = $1
        ORDER BY document_id
        """,
        project_id,
    )
    serialized = []
    for row in rows:
        doc = dict(row)
        doc_type = str(doc.get("document_type") or "")
        if doc_type in {"figma_import", "figma_export_image"}:
            serialized.append(
                {
                    "document_id": doc.get("document_id"),
                    "document_name": doc.get("document_name"),
                    "content_kind": doc_type,
                    "serialization_status": doc.get("serialization_status") or "RAG_READY",
                    "embedding_status": doc.get("embedding_status") or "READY_FOR_EMBEDDING",
                    "skipped": True,
                }
            )
            continue
        ext = str(doc.get("file_extension") or "")
        mime = str(doc.get("file_mime_type") or "")
        text = doc.get("raw_text_content")
        is_image = mime.startswith("image/") or ext in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
        is_design = ext in {".fig", ".figma", ".sketch"} or "figma" in mime.lower()
        content_kind = "image" if is_image else "figma_design" if is_design else "text" if text else "document_asset"
        descriptor = {
            "rag_ready": True,
            "content_kind": content_kind,
            "source_file": {
                "name": doc.get("document_name"),
                "extension": ext or None,
                "mime_type": mime or None,
                "size_bytes": doc.get("file_size_bytes"),
            },
            "agent_context": {
                "summary": f"{doc.get('document_name')} serialized for project-scope analysis.",
                "text_preview": str(text)[:1600] if text else None,
                "extraction_status": "text_ready" if text else "metadata_ready",
                "usage": (
                    "Use as direct text/project requirement context."
                    if text
                    else "Use as runtime visual/design asset metadata; inspect the source asset when visual fidelity matters."
                ),
            },
            "retrieval": {
                "namespace": "project_document",
                "modalities": ["text"] if text else ["metadata", "visual_reference"],
                "keywords": [str(doc.get("document_name") or ""), content_kind, ext.lstrip(".")],
            },
        }
        await db.execute(
            """
            UPDATE main.project_document
            SET structured_json = $1::jsonb,
                serialized_payload = $1::jsonb,
                serialization_status = 'RAG_READY',
                embedding_status = 'READY_FOR_EMBEDDING',
                chunk_count = CASE WHEN $2::boolean THEN GREATEST(1, CEIL(LENGTH(COALESCE(raw_text_content, '')) / 1200.0)::integer) ELSE 0 END,
                updated_at = NOW()
            WHERE project_id = $3 AND document_id = $4
            """,
            jsonb_dumps(descriptor),
            bool(text),
            project_id,
            int(doc["document_id"]),
        )
        serialized.append(
            {
                "document_id": doc.get("document_id"),
                "document_name": doc.get("document_name"),
                "content_kind": content_kind,
                "serialization_status": "RAG_READY",
                "embedding_status": "READY_FOR_EMBEDDING",
            }
        )
    return {"count": len(serialized), "documents": serialized}


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


@router.get("/projects/batch-summaries")
async def batch_project_summaries(
    limit: int = Query(12, ge=1, le=50),
    db: DatabaseManager = Depends(get_db),
) -> Dict[str, Any]:
    """Return recent projects with counts and latest run in fewer round-trips."""
    projects = await db.fetch_many(
        """
        SELECT project_id, project_name, project_type, description, status, created_at, updated_at
        FROM main.project
        WHERE COALESCE(status, 'ACTIVE') <> 'ARCHIVED'
        ORDER BY updated_at DESC NULLS LAST, project_id DESC
        LIMIT $1
        """,
        limit,
    )
    summaries: List[Dict[str, Any]] = []
    for project in projects:
        pid = int(project["project_id"])
        doc_count = int(
            await db.fetch_val("SELECT COUNT(*) FROM main.project_document WHERE project_id = $1", pid) or 0
        )
        task_count = int(
            await db.fetch_val(
                "SELECT COUNT(*) FROM main.task WHERE project_id = $1 AND COALESCE(status,'') <> 'SUPERSEDED'",
                pid,
            )
            or 0
        )
        latest_run = None
        run_count = 0
        if await schema_support.table_exists(db, "agent_run"):
            run_count = int(
                await db.fetch_val("SELECT COUNT(*) FROM main.agent_run WHERE project_id = $1", pid) or 0
            )
            latest = await db.fetch_one(
                """
                SELECT agent_run_id, status, runtime_provider, created_at, updated_at
                FROM main.agent_run WHERE project_id = $1
                ORDER BY agent_run_id DESC LIMIT 1
                """,
                pid,
            )
            latest_run = dict(latest) if latest else None
            if latest_run and await schema_support.table_exists(db, "agent_run"):
                full = await db.fetch_one(
                    "SELECT result_payload FROM main.agent_run WHERE agent_run_id = $1",
                    int(latest["agent_run_id"]),
                )
                payload = (full or {}).get("result_payload")
                if isinstance(payload, str):
                    import json as _json

                    try:
                        payload = _json.loads(payload)
                    except _json.JSONDecodeError:
                        payload = {}
                usage = token_usage_service.run_usage_from_payload(payload if isinstance(payload, dict) else {})
                if usage:
                    latest_run["token_usage"] = {
                        "totals": usage.get("totals"),
                        "efficiency": usage.get("efficiency"),
                        "by_model": (usage.get("by_model") or [])[:3],
                    }
        summaries.append(
            {
                "project": dict(project),
                "counts": {"documents": doc_count, "tasks": task_count, "runs": run_count},
                "latest_run": latest_run,
            }
        )
    return {"ok": True, "summaries": summaries}


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


class ProjectRefreshBody(BaseModel):
    reason: str = Field(
        default="Refresh project for a clean re-run",
        min_length=3,
        max_length=2000,
    )
    created_by: str = "dashboard"


@router.get("/projects/{project_id}/version-history")
async def project_version_history(project_id: int, db: DatabaseManager = Depends(get_db)):
    project = await db.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return await project_refresh_service.list_version_history(db, project_id=project_id)


@router.post("/projects/{project_id}/refresh")
async def refresh_project(
    project_id: int,
    body: ProjectRefreshBody,
    db: DatabaseManager = Depends(get_db),
):
    project = await db.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    result = await project_refresh_service.refresh_project(
        db,
        project_id=project_id,
        reason=body.reason,
        created_by=body.created_by,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "Refresh failed")
    return result


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


@router.get("/projects/{project_id}/design-readiness")
async def project_design_readiness(project_id: int, db: DatabaseManager = Depends(get_db)) -> Dict[str, Any]:
    project = await db.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    validation = await design_context_service.validate_design_context(db, project_id)
    active = await db.get_active_figma_import(project_id)
    ac = {}
    if active and active.get("structured_json"):
        ac = (active["structured_json"].get("agent_context") or {})
    return {
        "ok": validation.get("ok", True),
        "required": validation.get("required", False),
        "structural_ready": validation.get("structural_ready", True),
        "gaps": validation.get("gaps") or [],
        "sections": validation.get("sections") or [],
        "assets": validation.get("assets") or [],
        "export_count": validation.get("export_count", 0),
        "asset_count": validation.get("asset_count", 0),
        "extraction_version": ac.get("extraction_version"),
        "active_document_id": active.get("document_id") if active else None,
    }


@router.get("/projects/{project_id}/context-pack/compact")
async def project_context_pack_compact(project_id: int, db: DatabaseManager = Depends(get_db)) -> Dict[str, Any]:
    project = await db.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    context_pack = await context_pack_service.build_context_pack(
        db,
        project_id=project_id,
        include_change_history=False,
        include_versions=True,
        limit=50,
    )
    compact = context_pack_service.compact_for_prompt(context_pack)
    figma_docs = [
        doc
        for doc in compact.get("context_documents") or []
        if str(doc.get("content_kind") or "").lower() == "figma_import"
    ]
    readiness = await design_context_service.validate_design_context(db, project_id)
    return {
        "ok": True,
        "project_id": project_id,
        "compact": compact,
        "figma_import_count": len(figma_docs),
        "has_figma_excerpt": any(doc.get("text_preview") for doc in figma_docs),
        "design_context_required": bool(compact.get("design_context_required")),
        "design_sections": compact.get("design_sections") or [],
        "asset_count": readiness.get("asset_count", 0),
        "structural_ready": readiness.get("structural_ready", True),
        "design_gaps": readiness.get("gaps") or [],
    }


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


@router.get("/projects/{project_id}/health")
async def project_health(project_id: int, db: DatabaseManager = Depends(get_db)) -> Dict[str, Any]:
    project = await db.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    metadata = await project_metadata_service.get_project_metadata(db, project_id)
    runtime_preferences = metadata.get("runtime_preferences") or {}
    if not isinstance(runtime_preferences, dict):
        runtime_preferences = {}
    project_name = str(project.get("project_name") or f"project-{project_id}")
    repo_path = preview_detection_service.resolve_repo_path(
        runtime_preferences=runtime_preferences,
        project_name=project_name,
    )
    preview_status = await preview_detection_service.preview_status(runtime_preferences)
    runnable = verification_service.verify_project_runnable(
        repo_path=repo_path,
        preview_command=str(runtime_preferences.get("preview_command") or ""),
        preview_url=str(runtime_preferences.get("preview_url") or ""),
    )

    tasks = await db.fetch_many(
        """
        SELECT status, COUNT(*) AS count
        FROM main.task
        WHERE project_id = $1 AND COALESCE(status, '') <> 'SUPERSEDED'
        GROUP BY status
        """,
        project_id,
    )
    task_board = {str(row["status"]): int(row["count"]) for row in tasks}

    latest_run = None
    if await schema_support.table_exists(db, "agent_run"):
        latest = await db.fetch_one(
            """
            SELECT agent_run_id, status, runtime_provider, started_at, finished_at
            FROM main.agent_run WHERE project_id = $1
            ORDER BY agent_run_id DESC LIMIT 1
            """,
            project_id,
        )
        latest_run = dict(latest) if latest else None

    runtime = runtime_check_service.runtime_check()
    cli_ok = any(r.get("found") for r in runtime.get("cli_runtimes") or [])

    meta_blob = metadata.get("metadata") if isinstance(metadata.get("metadata"), dict) else {}
    return {
        "ok": True,
        "project_id": project_id,
        "repo_path": repo_path or None,
        "metadata": meta_blob,
        "task_board": task_board,
        "latest_run": latest_run,
        "preview": preview_status,
        "runnable_check": {
            "ok": runnable.ok,
            "errors": runnable.errors,
            "warnings": runnable.warnings,
        },
        "runtime_available": cli_ok,
    }


@router.post("/projects/{project_id}/analysis-plan")
async def create_analysis_plan(
    project_id: int,
    body: AnalysisPlanBody,
    db: DatabaseManager = Depends(get_db),
):
    project = await db.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    serialization = await _serialize_project_documents(db, project_id)
    context_pack = await context_pack_service.build_context_pack(
        db,
        project_id=project_id,
        include_change_history=True,
        include_versions=True,
        limit=100,
    )
    rag_context = context_pack.get("rag_ready_context") or {}
    rag_documents = rag_context.get("documents") or []
    design_assets = rag_context.get("design_assets") or []
    team = [role.model_dump() for role in body.team] if body.team else _default_agent_team()
    has_figma_import = any(
        str(doc.get("content_kind") or doc.get("document_type") or "").lower() == "figma_import"
        for doc in rag_documents
    )
    design_sections: List[Dict[str, Any]] = []
    for doc in rag_documents:
        if str(doc.get("content_kind") or "").lower() == "figma_import":
            secs = list(doc.get("design_sections") or [])
            secs.sort(
                key=lambda s: (
                    int(s.get("order") or 999),
                    float((s.get("box") or {}).get("y") or 0) if isinstance(s.get("box"), dict) else 0,
                )
            )
            design_sections.extend(secs)
    existing_meta = await project_metadata_service.get_project_metadata(db, project_id)
    runtime_preferences = existing_meta.get("runtime_preferences") or {}
    if not isinstance(runtime_preferences, dict):
        runtime_preferences = {}
    execution_mode = str(
        (body.execution_parameters or {}).get("execution_mode")
        or runtime_preferences.get("execution_mode")
        or "standard"
    )
    if execution_mode == "milestones":
        runtime_preferences["execution_mode"] = execution_mode

    tasks = _planned_tasks(
        body.goal,
        len(rag_documents),
        len(design_assets),
        has_figma_import=has_figma_import,
        design_sections=design_sections,
        execution_mode=execution_mode,
    )
    milestones: List[Dict[str, Any]] = []
    if execution_mode == "milestones":
        tasks, milestones = assign_milestones(tasks, has_figma_import=has_figma_import)

    repo_path = str(body.repo_path or runtime_preferences.get("repo_path") or "").strip()
    if repo_path:
        runtime_preferences["repo_path"] = repo_path
        runtime_preferences, _ = preview_detection_service.apply_to_runtime_preferences(
            runtime_preferences,
            repo_path=repo_path,
            force=not bool(body.preview_command),
            project_id=project_id,
        )
    if body.preview_command:
        runtime_preferences["preview_command"] = body.preview_command
    if body.preview_url:
        runtime_preferences["preview_url"] = body.preview_url
    section_parallel = (
        min(len(design_sections), app_config.section_task_max_parallel)
        if has_figma_import and len(design_sections) > 1
        else 1
    )
    execution_batches = build_execution_batches(
        tasks,
        section_max_concurrency=section_parallel,
    )
    runtime_preferences.update(
        {
            "repo_path": repo_path or runtime_preferences.get("repo_path"),
            "agent_team": team,
            "execution_parameters": {
                "max_concurrency": section_parallel,
                "section_task_parallelism": section_parallel,
                "execution_batches": execution_batches,
                "parallel_cli_stagger_seconds": app_config.parallel_cli_stagger_seconds,
                "runtime": runtime_preferences.get("provider")
                or runtime_preferences.get("runtime")
                or "codex-cli",
                "use_worktree": True,
                **(body.execution_parameters or {}),
                "execution_mode": execution_mode,
                "milestones": milestones,
            },
            "manual_edit_instructions": body.manual_edit_instructions,
            "acceptance_criteria": body.acceptance_criteria,
        }
    )
    metadata = existing_meta.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    metadata.update(
        {
            "analysis_goal": body.goal,
            "rag_ready_document_count": len(rag_documents),
            "design_asset_count": len(design_assets),
            "last_analysis_plan": {
                "tasks": tasks,
                "team": team,
                "acceptance_criteria": body.acceptance_criteria,
                "execution_batches": execution_batches,
                "milestones": milestones,
            },
        }
    )

    await project_metadata_service.update_project_metadata(
        db,
        project_id=project_id,
        metadata=metadata,
        repository_url=body.repository_url,
        default_branch=body.default_branch,
        runtime_preferences=runtime_preferences,
        updated_by="dashboard-analysis",
    )

    await db.execute(
        """
        UPDATE main.task
        SET status = 'SUPERSEDED',
            updated_at = NOW()
        WHERE project_id = $1
          AND COALESCE(status, '') NOT IN ('COMPLETED', 'RUNNING', 'SUPERSEDED')
        """,
        project_id,
    )

    created_tasks = []
    for sequence_index, task in enumerate(tasks):
        planned_task_data = annotate_task_execution_fields(
            task,
            sequence_index=sequence_index,
            execution_batches=execution_batches,
        )
        persisted_task_data = {
            "rag_ready_context": rag_context,
            "execution_parameters": runtime_preferences.get("execution_parameters"),
            "agent_effort": task.get("agent_effort"),
            "execution_complexity": (task.get("agent_effort") or {}).get("execution_complexity"),
            **planned_task_data,
        }
        row = await db.fetch_one(
            """
            INSERT INTO main.task (
                project_id,
                task_name,
                task_type,
                description,
                parameters,
                status,
                priority,
                task_notes,
                task_data,
                created_by
            )
            VALUES ($1, $2, $3, $4, $5::jsonb, 'READY_FOR_AGENT', $6, $7, $8::jsonb, 'dashboard-analysis')
            RETURNING task_id, project_id, task_name, task_type, description, parameters, status, priority, task_data
            """,
            project_id,
            task["task_name"],
            task["task_type"],
            task["description"],
            jsonb_dumps(
                {
                    "goal": body.goal,
                    "acceptance_criteria": body.acceptance_criteria,
                    "agent_team": team,
                }
            ),
            task["priority"],
            body.manual_edit_instructions,
            jsonb_dumps(persisted_task_data),
        )
        if row:
            created_tasks.append(dict(row))

    await change_history_service.record_change(
        db,
        project_id=project_id,
        entity_type="project",
        entity_id=project_id,
        source="projects.analysis_plan",
        change_type="ANALYSIS_PLAN_CREATED",
        title="Analysis and task plan created",
        summary=f"Created {len(created_tasks)} tasks from {len(rag_documents)} RAG-ready documents.",
        payload={
            "goal": body.goal,
            "tasks": tasks,
            "team": team,
            "serialization": serialization,
            "rag_ready_document_count": len(rag_documents),
            "design_asset_count": len(design_assets),
        },
        created_by="dashboard-analysis",
    )

    return {
        "ok": True,
        "goal": body.goal,
        "team": team,
        "tasks": created_tasks,
        "serialization": serialization,
        "rag_ready_context": rag_context,
        "execution_parameters": runtime_preferences.get("execution_parameters"),
        "execution_batches": execution_batches,
        "execution_mode": execution_mode,
        "milestones": milestones,
        "review_required": True,
    }


@router.get("/projects/{project_id}/progress")
async def project_progress(project_id: int, db: DatabaseManager = Depends(get_db)):
    project = await db.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    progress = await progress_service.compute_progress(db, project_id)
    return {"ok": True, "project_id": project_id, **progress}


@router.post("/projects/{project_id}/promote-to-main")
async def promote_project_to_main(project_id: int, db: DatabaseManager = Depends(get_db)):
    """Explicit user approval: fast-forward the default branch to the latest preview milestone."""
    project = await db.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    metadata = await project_metadata_service.get_project_metadata(db, project_id)
    runtime_preferences = metadata.get("runtime_preferences") or {}
    if not isinstance(runtime_preferences, dict):
        runtime_preferences = {}
    repo_path = str(runtime_preferences.get("repo_path") or "").strip()
    if not repo_path:
        raise HTTPException(status_code=400, detail="project repository path is not configured")
    default_branch = str(metadata.get("default_branch") or "main")
    result = await git_worktree_service.promote_branch(
        repo_path,
        from_branch="mas/preview",
        to_branch=default_branch,
        worktree_base_path=app_config.midnight_worktree_base_path or None,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "promotion failed")
    await change_history_service.record_change(
        db,
        project_id=project_id,
        entity_type="project",
        entity_id=project_id,
        source="projects.promote_to_main",
        change_type="MILESTONE_PROMOTED_TO_MAIN",
        title=f"Promoted preview to {default_branch}",
        summary=f"{default_branch} fast-forwarded to mas/preview ({result.get('commit_hash')})",
        payload=result,
        created_by="dashboard-promote",
    )
    return {"ok": True, "project_id": project_id, **result}


@router.get("/projects/{project_id}/preview/status")
async def project_preview_status(project_id: int, db: DatabaseManager = Depends(get_db)):
    project = await db.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    metadata = await project_metadata_service.get_project_metadata(db, project_id)
    runtime_preferences = metadata.get("runtime_preferences") or {}
    if not isinstance(runtime_preferences, dict):
        runtime_preferences = {}
    status = await preview_detection_service.preview_status(runtime_preferences)
    return {"ok": True, "project_id": project_id, **status}


@router.get("/projects/{project_id}/preview/detect")
async def detect_project_preview(project_id: int, db: DatabaseManager = Depends(get_db)):
    project = await db.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    metadata = await project_metadata_service.get_project_metadata(db, project_id)
    runtime_preferences = metadata.get("runtime_preferences") or {}
    if not isinstance(runtime_preferences, dict):
        runtime_preferences = {}
    project_name = str(project.get("project_name") or f"project-{project_id}")
    repo_path, prefs, detection = await _resolve_repo_and_preview(
        db,
        project_id=project_id,
        project_name=project_name,
        runtime_preferences=runtime_preferences,
        persist=True,
        force_detect=True,
    )
    if not repo_path:
        return {
            "ok": False,
            "error": "Set a workspace repo path first (Serialize tab).",
            "preview_url": None,
        }
    if not detection or not detection.get("ok"):
        return {
            "ok": False,
            "repo_path": repo_path,
            "error": (detection or {}).get("error") or "Could not detect a dev preview for this workspace.",
            "preview_url": prefs.get("preview_url"),
            "searched_paths": (detection or {}).get("searched_paths"),
        }
    return {
        "ok": True,
        "repo_path": repo_path,
        "preview_command": prefs.get("preview_command"),
        "preview_url": prefs.get("preview_url"),
        "allocated_port": detection.get("allocated_port"),
        "port_note": detection.get("port_note"),
        "framework": detection.get("framework"),
        "working_directory": detection.get("working_directory"),
        "detected_from": detection.get("source"),
        "search_root": detection.get("search_root"),
    }


@router.post("/projects/{project_id}/preview")
async def start_project_preview(project_id: int, db: DatabaseManager = Depends(get_db)):
    project = await db.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    metadata = await project_metadata_service.get_project_metadata(db, project_id)
    runtime_preferences = metadata.get("runtime_preferences") or {}
    if not isinstance(runtime_preferences, dict):
        runtime_preferences = {}
    project_name = str(project.get("project_name") or f"project-{project_id}")
    repo_path, runtime_preferences, detection = await _resolve_repo_and_preview(
        db,
        project_id=project_id,
        project_name=project_name,
        runtime_preferences=runtime_preferences,
        persist=True,
        force_detect=True,
    )
    preview_command = str(runtime_preferences.get("preview_command") or "").strip()
    preview_url = str(runtime_preferences.get("preview_url") or "").strip()
    if not repo_path:
        return {
            "ok": False,
            "preview_url": None,
            "error": "Set a workspace path on the Serialize tab before launching preview.",
        }
    if not preview_command or not preview_url:
        detail = (detection or {}).get("error") or "Could not detect a dev preview command for this project."
        return {
            "ok": False,
            "preview_url": preview_url or None,
            "error": detail,
            "repo_path": repo_path,
            "searched_paths": (detection or {}).get("searched_paths"),
        }
    cwd = preview_detection_service.resolve_preview_workspace(repo_path, project_id)
    if not cwd.exists() or not cwd.is_dir():
        return {"ok": False, "preview_url": preview_url, "error": f"Preview workspace does not exist: {cwd}"}

    framework = str(runtime_preferences.get("preview_framework") or (detection or {}).get("framework") or "vite")
    saved_port = runtime_preferences.get("preview_allocated_port")
    preferred_port = int(saved_port) if saved_port is not None else None
    allocated = preview_detection_service.allocate_preview_launch(
        preview_command=preview_command,
        package_root=cwd,
        framework=framework,
        script_name="dev",
        preferred_port=preferred_port,
    )
    preview_command = str(allocated["preview_command"])
    preview_url = str(allocated["preview_url"])
    allocated_port = int(allocated["allocated_port"])
    port_note = str(allocated.get("port_note") or "")

    steps: List[Dict[str, Any]] = [
        {
            "id": "workspace",
            "label": "Workspace resolved",
            "status": "done",
            "detail": str(cwd),
        },
        {
            "id": "detect",
            "label": "App entrypoint detected",
            "status": "done",
            "detail": str((detection or {}).get("source") or preview_command),
        },
        {
            "id": "port",
            "label": "Port allocated",
            "status": "done",
            "detail": port_note,
        },
    ]

    spawn = preview_detection_service.spawn_preview_process(
        preview_command=preview_command,
        working_directory=cwd,
    )
    if not spawn.get("ok"):
        err = str(spawn.get("error") or "Failed to start dev server")
        steps.append(
            {
                "id": "spawn",
                "label": "Failed to start dev server",
                "status": "error",
                "detail": err,
            }
        )
        return {"ok": False, "preview_url": preview_url, "error": err, "steps": steps, "code": "preview_spawn_failed"}

    steps.append(
        {
            "id": "spawn",
            "label": "Dev server process started",
            "status": "done",
            "detail": f"pid={spawn.get('pid')} · {preview_command}",
        }
    )

    runtime_preferences["preview_command"] = preview_command
    runtime_preferences["preview_url"] = preview_url
    runtime_preferences["preview_working_directory"] = str(cwd)
    runtime_preferences["preview_allocated_port"] = allocated_port
    runtime_preferences["preview_session"] = preview_detection_service.build_preview_session(
        preview_url=preview_url,
        preview_command=preview_command,
        working_directory=str(cwd),
        repo_path=repo_path,
        pid=int(spawn["pid"]) if spawn.get("pid") else None,
    )
    await project_metadata_service.update_project_metadata(
        db,
        project_id=project_id,
        metadata=metadata.get("metadata") if isinstance(metadata.get("metadata"), dict) else None,
        repository_url=metadata.get("repository_url"),
        default_branch=metadata.get("default_branch"),
        runtime_preferences=runtime_preferences,
        updated_by="dashboard-preview",
    )
    probe = await preview_detection_service.probe_preview_url(preview_url)
    launch_phase = "ready" if probe.get("reachable") else "launched"
    steps.append(
        {
            "id": "health",
            "label": "Waiting for app to respond"
            if launch_phase != "ready"
            else "App is responding",
            "status": "done" if launch_phase == "ready" else "active",
            "detail": preview_url
            if launch_phase == "ready"
            else f"Polling {preview_url} until the dev server is ready…",
        }
    )

    await change_history_service.record_change(
        db,
        project_id=project_id,
        entity_type="project",
        entity_id=project_id,
        source="projects.preview",
        change_type="PREVIEW_STARTED",
        title="Preview started",
        summary=str(preview_command),
        payload={"repo_path": str(cwd), "preview_url": preview_url, "allocated_port": allocated_port},
        created_by="dashboard",
    )
    return {
        "ok": True,
        "preview_url": preview_url,
        "open_url": probe.get("final_url") or preview_url,
        "command": preview_command,
        "repo_path": str(cwd),
        "working_directory": str(cwd),
        "allocated_port": allocated_port,
        "port_note": port_note,
        "auto_detected": bool(detection and detection.get("ok")),
        "phase": launch_phase,
        "reachable": bool(probe.get("reachable")),
        "status_code": probe.get("status_code"),
        "steps": steps,
        "message": "Your app is running and ready to open."
        if probe.get("reachable")
        else f"Dev server started on port {allocated_port}. Waiting for it to finish booting…",
    }


class WorkspacePrepareBody(BaseModel):
    parent_path: Optional[str] = None
    existing_path: Optional[str] = None
    mode: str = Field(
        default="create",
        description="create | init_here | use_existing",
    )
    save_to_project: bool = True


class CodebaseSerializeBody(BaseModel):
    repo_path: Optional[str] = None
    max_files: int = Field(default=400, ge=1, le=2000)


@router.get("/projects/workspace/default-parent")
async def default_workspace_parent():
    parent = default_projects_parent()
    return {"parent_path": str(parent), "exists": parent.exists()}


@router.post("/projects/{project_id}/workspace/prepare")
async def prepare_project_workspace(
    project_id: int,
    body: WorkspacePrepareBody,
    db: DatabaseManager = Depends(get_db),
):
    project = await db.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project_name = str(project.get("project_name") or f"project-{project_id}")
    result = await repo_workspace_service.prepare_workspace(
        parent_path=body.parent_path,
        project_name=project_name,
        mode=body.mode,
        existing_path=body.existing_path,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "Workspace preparation failed")

    repo_path = str(result.get("repo_path") or "")
    if body.save_to_project and repo_path:
        metadata = await project_metadata_service.get_project_metadata(db, project_id)
        runtime_preferences = metadata.get("runtime_preferences") or {}
        if not isinstance(runtime_preferences, dict):
            runtime_preferences = {}
        runtime_preferences["repo_path"] = repo_path
        if body.mode == "create":
            runtime_preferences.pop("workspace_parent_path", None)
        runtime_preferences, _ = preview_detection_service.apply_to_runtime_preferences(
            runtime_preferences,
            repo_path=repo_path,
            force=True,
        )
        project_metadata = metadata.get("metadata") or {}
        if not isinstance(project_metadata, dict):
            project_metadata = {}
        project_metadata["workspace_prepared_at"] = project_metadata.get("workspace_prepared_at") or "now"
        await project_metadata_service.update_project_metadata(
            db,
            project_id=project_id,
            metadata=project_metadata,
            repository_url=metadata.get("repository_url"),
            default_branch=metadata.get("default_branch"),
            runtime_preferences=runtime_preferences,
            updated_by="dashboard-workspace",
        )

    return {**result, "project_id": project_id, "saved_to_project": body.save_to_project}


@router.post("/projects/{project_id}/codebase/serialize")
async def start_codebase_serialization(
    project_id: int,
    body: CodebaseSerializeBody,
    db: DatabaseManager = Depends(get_db),
):
    project = await db.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    repo_path = (body.repo_path or "").strip()
    if not repo_path:
        metadata = await project_metadata_service.get_project_metadata(db, project_id)
        runtime_preferences = metadata.get("runtime_preferences") or {}
        if isinstance(runtime_preferences, dict):
            repo_path = str(runtime_preferences.get("repo_path") or "").strip()
            if not repo_path:
                parent = str(runtime_preferences.get("workspace_parent_path") or "").strip()
                if parent:
                    project = await db.get_project_by_id(project_id)
                    project_name = str((project or {}).get("project_name") or f"project-{project_id}")
                    created = await repo_workspace_service.create_project_workspace(
                        parent_path=parent,
                        project_name=project_name,
                    )
                    if created.get("ok"):
                        repo_path = str(created.get("repo_path") or "").strip()
                        runtime_preferences["repo_path"] = repo_path
                        runtime_preferences.pop("workspace_parent_path", None)
                        await project_metadata_service.update_project_metadata(
                            db,
                            project_id=project_id,
                            metadata=metadata.get("metadata") if isinstance(metadata.get("metadata"), dict) else None,
                            repository_url=metadata.get("repository_url"),
                            default_branch=metadata.get("default_branch"),
                            runtime_preferences=runtime_preferences,
                            updated_by="dashboard-codebase",
                        )
    if not repo_path:
        raise HTTPException(
            status_code=400,
            detail="Repository path is required. Set a workspace path or pass repo_path.",
        )

    return await codebase_serialization_service.start(
        db,
        project_id=project_id,
        repo_path=repo_path,
        max_files=body.max_files,
    )


@router.get("/projects/{project_id}/codebase/serialize/status")
async def codebase_serialization_status(project_id: int):
    return codebase_serialization_service.status_payload(project_id)
