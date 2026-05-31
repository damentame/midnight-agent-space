"""Project document upload and listing."""
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from ..config import app_config
from ..database import DatabaseManager, get_db
from ..services.change_history_service import change_history_service
from ..services.document_version_service import document_version_service
from ..services.jsonb_utils import decode_jsonb_fields

router = APIRouter()
logger = logging.getLogger(__name__)


class DocumentCreateBody(BaseModel):
    document_name: str = Field(..., min_length=1, max_length=255)
    document_type: Optional[str] = "manual"
    raw_text_content: Optional[str] = ""
    file_extension: Optional[str] = ".md"
    file_mime_type: Optional[str] = "text/plain"


class DocumentPatchBody(BaseModel):
    document_name: Optional[str] = None
    document_type: Optional[str] = None
    raw_text_content: Optional[str] = None
    serialization_status: Optional[str] = None
    create_new_version: bool = True
    version_label: Optional[str] = None
    source: Optional[str] = "editor"
    change_summary: Optional[str] = "Edited in dashboard"


class DocumentVersionCreateBody(BaseModel):
    version_label: Optional[str] = None
    source: Optional[str] = "manual"
    change_summary: Optional[str] = None
    raw_text_content: Optional[str] = None
    structured_json: Optional[dict] = None
    content_hash: Optional[str] = None
    created_by: Optional[str] = "dashboard"


@router.get("/projects/{project_id}/documents")
async def list_documents(project_id: int, db: DatabaseManager = Depends(get_db)):
    p = await db.get_project_by_id(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return await db.get_documents_by_project(project_id)


@router.post("/projects/{project_id}/documents")
async def create_document(
    project_id: int,
    body: DocumentCreateBody = Body(...),
    db: DatabaseManager = Depends(get_db),
):
    p = await db.get_project_by_id(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    text = body.raw_text_content or ""
    row = await db.insert_document_upload(
        project_id=project_id,
        document_name=body.document_name,
        document_type=body.document_type or "manual",
        raw_text=text,
        ext=body.file_extension or ".md",
        mime=body.file_mime_type or "text/plain",
        size=len(text.encode("utf-8")),
        file_bytes=None,
    )
    document_id = int(row.get("document_id") or 0)
    if document_id > 0:
        await document_version_service.create_version(
            db,
            project_id=project_id,
            document_id=document_id,
            version_label="v1",
            source="manual",
            change_summary="Document created",
            raw_text_content=text,
            structured_json=None,
            content_hash=None,
            created_by="dashboard",
        )
    return row


@router.get("/projects/{project_id}/documents/{document_id}")
async def get_document(project_id: int, document_id: int, db: DatabaseManager = Depends(get_db)):
    row = await db.fetch_one(
        """
        SELECT *
        FROM main.project_document
        WHERE project_id = $1 AND document_id = $2
        """,
        project_id,
        document_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    return decode_jsonb_fields(dict(row), ("structured_json",))


@router.patch("/projects/{project_id}/documents/{document_id}")
async def patch_document(
    project_id: int,
    document_id: int,
    body: DocumentPatchBody,
    db: DatabaseManager = Depends(get_db),
):
    doc = await db.fetch_one(
        """
        SELECT *
        FROM main.project_document
        WHERE project_id = $1 AND document_id = $2
        """,
        project_id,
        document_id,
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    updates = body.model_dump(exclude_unset=True)
    fields = []
    values = []
    idx = 1
    for key in ("document_name", "document_type", "raw_text_content", "serialization_status"):
        value = updates.get(key)
        if value is not None:
            fields.append(f"{key} = ${idx}")
            values.append(value)
            idx += 1
    if not fields:
        return dict(doc)
    fields.append("updated_at = NOW()")
    values.extend([project_id, document_id])

    updated = await db.fetch_one(
        f"""
        UPDATE main.project_document
        SET {", ".join(fields)}
        WHERE project_id = ${idx} AND document_id = ${idx + 1}
        RETURNING *
        """,
        *values,
    )
    if body.create_new_version:
        await document_version_service.create_version(
            db,
            project_id=project_id,
            document_id=document_id,
            version_label=body.version_label,
            source=body.source,
            change_summary=body.change_summary,
            raw_text_content=body.raw_text_content,
            structured_json=None,
            content_hash=None,
            created_by="dashboard",
        )
    return dict(updated) if updated else {}


@router.get("/projects/{project_id}/documents/{document_id}/versions")
async def list_document_versions(
    project_id: int,
    document_id: int,
    limit: int = Query(50, ge=1, le=500),
    db: DatabaseManager = Depends(get_db),
):
    p = await db.get_project_by_id(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return await document_version_service.list_versions(db, project_id, document_id, limit=limit)


@router.get("/projects/{project_id}/documents/{document_id}/versions/{version_number}")
async def get_document_version(
    project_id: int,
    document_id: int,
    version_number: int,
    db: DatabaseManager = Depends(get_db),
):
    row = await db.fetch_one(
        """
        SELECT *
        FROM main.document_version
        WHERE project_id = $1
          AND document_id = $2
          AND version_number = $3
        """,
        project_id,
        document_id,
        version_number,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Version not found")
    return decode_jsonb_fields(dict(row), ("structured_json",))


@router.post("/projects/{project_id}/documents/{document_id}/versions")
async def create_document_version(
    project_id: int,
    document_id: int,
    body: DocumentVersionCreateBody,
    db: DatabaseManager = Depends(get_db),
):
    p = await db.get_project_by_id(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    version = await document_version_service.create_version(
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
    if not version:
        raise HTTPException(status_code=400, detail="document_version table unavailable")
    return version


@router.post("/projects/{project_id}/documents/upload")
async def upload_document(
    project_id: int,
    db: DatabaseManager = Depends(get_db),
    file: UploadFile = File(...),
):
    p = await db.get_project_by_id(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    raw = await file.read()
    if len(raw) > app_config.upload_max_size:
        raise HTTPException(status_code=413, detail="File too large")

    name = file.filename or "upload"
    ext = Path(name).suffix.lower() or ""
    if ext and ext not in app_config.allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Extension not allowed. Allowed: {sorted(app_config.allowed_extensions)}",
        )

    mime = file.content_type or "application/octet-stream"
    text_extensions = {".txt", ".md", ".json", ".csv", ".xml", ".py", ".js", ".ts", ".tsx"}
    is_text = ext in text_extensions or (mime or "").startswith("text/")
    raw_text: Optional[str] = None
    file_bytes: Optional[bytes] = None
    if is_text:
        try:
            raw_text = raw.decode("utf-8")
        except UnicodeDecodeError:
            file_bytes = raw
    else:
        file_bytes = raw

    row = await db.insert_document_upload(
        project_id=project_id,
        document_name=name,
        document_type="uploaded",
        raw_text=raw_text,
        ext=ext or None,
        mime=mime,
        size=len(raw),
        file_bytes=file_bytes,
    )

    # Best-effort additive tracking for Phase 0-4 entities.
    try:
        document_id = int(row.get("document_id"))
        await document_version_service.create_version(
            db,
            project_id=project_id,
            document_id=document_id,
            version_label="upload-v1",
            source="upload",
            change_summary="Document uploaded from dashboard",
            raw_text_content=raw_text,
            structured_json=None,
            content_hash=None,
            created_by="dashboard",
        )
        await change_history_service.record_change(
            db,
            project_id=project_id,
            entity_type="project_document",
            entity_id=document_id,
            source="documents.upload",
            change_type="DOCUMENT_UPLOADED",
            title="Document uploaded",
            summary=f"Uploaded {name}",
            payload={
                "document_name": name,
                "document_type": "uploaded",
                "file_extension": ext,
                "file_size_bytes": len(raw),
            },
            created_by="dashboard",
        )
    except Exception:
        logger.exception("best-effort version/change tracking failed for project_id=%s", project_id)

    return row


@router.delete("/projects/{project_id}/documents/{document_id}")
async def delete_document(
    project_id: int,
    document_id: int,
    db: DatabaseManager = Depends(get_db),
):
    ok = await db.delete_document_if_pending(project_id, document_id)
    if not ok:
        raise HTTPException(
            status_code=400,
            detail="Not found or document already processed (only PENDING can be deleted)",
        )
    return {"deleted": True, "document_id": document_id}
