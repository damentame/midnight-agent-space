"""Project document upload and listing."""
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from ..config import app_config
from ..database import DatabaseManager, get_db

router = APIRouter()


@router.get("/projects/{project_id}/documents")
async def list_documents(project_id: int, db: DatabaseManager = Depends(get_db)):
    p = await db.get_project_by_id(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return await db.get_documents_by_project(project_id)


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
