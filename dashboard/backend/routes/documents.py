"""Project document upload and listing."""
import logging
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..config import app_config
from ..database import DatabaseManager, get_db
from ..services.change_history_service import change_history_service
from ..services.document_version_service import document_version_service
from ..services.jsonb_utils import decode_jsonb_fields, jsonb_dumps
from ..services.design_pack_service import import_design_pack as import_design_pack_service
from .figma_handlers import FigmaImportBody, import_figma_design_handler

router = APIRouter()
logger = logging.getLogger(__name__)

TEXT_EXTENSIONS = {".txt", ".md", ".json", ".csv", ".xml", ".py", ".js", ".ts", ".tsx"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
DESIGN_EXTENSIONS = {".fig", ".figma", ".sketch"}


def _content_disposition_filename(name: str) -> str:
    """Build a Content-Disposition value safe for non-ASCII filenames."""
    ascii_name = name.encode("ascii", "replace").decode("ascii").replace('"', "")
    encoded = quote(name, safe="")
    return f"inline; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded}"


def _content_kind(ext: str, mime: str) -> str:
    if ext in IMAGE_EXTENSIONS or mime.startswith("image/"):
        return "image"
    if ext in DESIGN_EXTENSIONS or "figma" in mime:
        return "figma_design"
    if ext in {".pdf", ".docx"}:
        return "document_asset"
    if ext in TEXT_EXTENSIONS or mime.startswith("text/"):
        return "text"
    return "binary_asset"


def _document_type_for_upload(content_kind: str) -> str:
    if content_kind == "image":
        return "design_image"
    if content_kind == "figma_design":
        return "figma_design"
    if content_kind == "document_asset":
        return "uploaded_document"
    if content_kind == "text":
        return "uploaded_text"
    return "uploaded_asset"


def _rag_asset_descriptor(
    *,
    name: str,
    ext: str,
    mime: str,
    size: int,
    content_kind: str,
    text_preview: Optional[str],
    instructions: Optional[str] = None,
) -> dict:
    extraction_status = "text_ready" if text_preview is not None else "metadata_ready"
    return {
        "rag_ready": True,
        "content_kind": content_kind,
        "source_file": {
            "name": name,
            "extension": ext or None,
            "mime_type": mime,
            "size_bytes": size,
        },
        "agent_context": {
            "summary": (
                f"Uploaded {content_kind.replace('_', ' ')} asset: {name}. "
                "Use this as project context during planning and execution."
            ),
            "text_preview": text_preview[:1200] if text_preview else None,
            "user_instructions": instructions.strip() if instructions else None,
            "extraction_status": extraction_status,
            "recommended_processing": [
                "Include this asset in context pack asset inventory.",
                "Use filename, mime type, and user-provided project notes as retrieval keys.",
                "If visual fidelity is needed, inspect the source file before implementation.",
            ],
        },
        "retrieval": {
            "namespace": "project_document",
            "modalities": ["text"] if content_kind == "text" else ["metadata", "visual_reference"],
            "keywords": [name, content_kind, ext.lstrip(".")],
        },
    }


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


class BatchDeleteDocumentsBody(BaseModel):
    document_ids: list[int] = Field(..., min_length=1)


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
        rag_descriptor = _rag_asset_descriptor(
            name=body.document_name,
            ext=body.file_extension or ".md",
            mime=body.file_mime_type or "text/plain",
            size=len(text.encode("utf-8")),
            content_kind="text",
            text_preview=text,
        )
        await db.execute(
            """
            UPDATE main.project_document
            SET structured_json = $1::jsonb,
                serialized_payload = $1::jsonb,
                serialization_status = 'RAG_READY',
                embedding_status = 'READY_FOR_EMBEDDING',
                updated_at = NOW()
            WHERE project_id = $2 AND document_id = $3
            """,
            jsonb_dumps(rag_descriptor),
            project_id,
            document_id,
        )
        await document_version_service.create_version(
            db,
            project_id=project_id,
            document_id=document_id,
            version_label="v1",
            source="manual",
            change_summary="Document created",
            raw_text_content=text,
            structured_json=rag_descriptor,
            content_hash=None,
            created_by="dashboard",
        )
        refreshed = await db.fetch_one(
            """
            SELECT document_id, project_id, document_name, document_type, file_extension,
                   file_mime_type, file_size_bytes, serialization_status, embedding_status, created_at, updated_at
            FROM main.project_document
            WHERE project_id = $1 AND document_id = $2
            """,
            project_id,
            document_id,
        )
        return dict(refreshed) if refreshed else row
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


def _upload_size_error_detail(size_bytes: int) -> str:
    limit_mb = max(1, app_config.upload_max_size // (1024 * 1024))
    got_mb = max(1, (size_bytes + 1024 * 1024 - 1) // (1024 * 1024))
    return f"File too large ({got_mb} MB). Maximum upload size is {limit_mb} MB."


@router.post("/projects/{project_id}/figma/import")
async def import_figma_design(
    project_id: int,
    body: FigmaImportBody,
    db: DatabaseManager = Depends(get_db),
):
    """Import a Figma frame/file into project context via the REST API."""
    return await import_figma_design_handler(project_id, body, db)


@router.post("/projects/{project_id}/design-pack/import")
async def import_design_pack(
    project_id: int,
    request: Request,
    db: DatabaseManager = Depends(get_db),
):
    """Import a MAS design pack zip exported by the Figma plugin."""
    p = await db.get_project_by_id(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        form = await request.form(max_part_size=app_config.upload_max_size)
    except Exception as exc:
        logger.warning("design-pack multipart parse failed: %s", exc)
        raise HTTPException(
            status_code=413,
            detail=_upload_size_error_detail(app_config.upload_max_size + 1),
        ) from exc

    upload = form.get("file")
    if upload is None or not hasattr(upload, "read"):
        raise HTTPException(status_code=400, detail="file is required (MAS design pack .zip)")

    notes_field = form.get("notes")
    notes = str(notes_field).strip() if notes_field is not None and str(notes_field).strip() else None

    raw = await upload.read()
    if len(raw) > app_config.upload_max_size:
        raise HTTPException(status_code=413, detail=_upload_size_error_detail(len(raw)))

    name = getattr(upload, "filename", None) or "mas-design-pack.zip"
    if not str(name).lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Design pack must be a .zip file from the Figma plugin.")

    try:
        return await import_design_pack_service(
            db,
            project_id=project_id,
            zip_bytes=raw,
            user_notes=notes,
            pack_filename=str(name),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("design-pack import failed project_id=%s", project_id)
        raise HTTPException(status_code=502, detail=f"Design pack import failed: {exc}") from exc


@router.get("/settings/uploads")
async def upload_settings():
    return {
        "max_size_bytes": app_config.upload_max_size,
        "max_size_mb": app_config.upload_max_size // (1024 * 1024),
        "allowed_extensions": sorted(app_config.allowed_extensions),
    }


@router.get("/projects/{project_id}/documents/{document_id}/file")
async def get_document_file(
    project_id: int,
    document_id: int,
    db: DatabaseManager = Depends(get_db),
):
    row = await db.get_document_file(project_id, document_id)
    if not row or not row.get("file_content"):
        raise HTTPException(status_code=404, detail="File content not found")
    content = row["file_content"]
    if isinstance(content, memoryview):
        content = content.tobytes()
    mime = row.get("file_mime_type") or "application/octet-stream"
    name = row.get("document_name") or "file"
    headers = {"Content-Disposition": _content_disposition_filename(str(name))}
    return Response(content=content, media_type=mime, headers=headers)


@router.post("/projects/{project_id}/documents/upload")
async def upload_document(
    project_id: int,
    request: Request,
    db: DatabaseManager = Depends(get_db),
):
    p = await db.get_project_by_id(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        form = await request.form(max_part_size=app_config.upload_max_size)
    except Exception as exc:
        logger.warning("multipart parse failed: %s", exc)
        raise HTTPException(
            status_code=413,
            detail=_upload_size_error_detail(app_config.upload_max_size + 1),
        ) from exc

    upload = form.get("file")
    if upload is None or not hasattr(upload, "read"):
        raise HTTPException(status_code=400, detail="file is required")

    instructions_field = form.get("instructions")
    instructions = (
        str(instructions_field).strip()
        if instructions_field is not None and str(instructions_field).strip()
        else None
    )

    raw = await upload.read()
    if len(raw) > app_config.upload_max_size:
        raise HTTPException(status_code=413, detail=_upload_size_error_detail(len(raw)))

    name = getattr(upload, "filename", None) or "upload"
    ext = Path(name).suffix.lower() or ""
    if ext and ext not in app_config.allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Extension not allowed. Allowed: {sorted(app_config.allowed_extensions)}",
        )

    mime = getattr(upload, "content_type", None) or "application/octet-stream"
    is_text = ext in TEXT_EXTENSIONS or (mime or "").startswith("text/")
    content_kind = _content_kind(ext, mime)
    document_type = _document_type_for_upload(content_kind)
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
        document_type=document_type,
        raw_text=raw_text,
        ext=ext or None,
        mime=mime,
        size=len(raw),
        file_bytes=file_bytes,
    )

    rag_descriptor = _rag_asset_descriptor(
        name=name,
        ext=ext,
        mime=mime,
        size=len(raw),
        content_kind=content_kind,
        text_preview=raw_text,
        instructions=instructions,
    )

    # Best-effort additive tracking for Phase 0-4 entities.
    try:
        document_id = int(row.get("document_id"))
        await db.execute(
            """
            UPDATE main.project_document
            SET structured_json = $1::jsonb,
                serialized_payload = $1::jsonb,
                serialization_status = 'RAG_READY',
                embedding_status = 'READY_FOR_EMBEDDING',
                updated_at = NOW()
            WHERE project_id = $2 AND document_id = $3
            """,
            jsonb_dumps(rag_descriptor),
            project_id,
            document_id,
        )
        await document_version_service.create_version(
            db,
            project_id=project_id,
            document_id=document_id,
            version_label="upload-v1",
            source="upload",
            change_summary=f"Uploaded {content_kind.replace('_', ' ')} for agent context",
            raw_text_content=raw_text,
            structured_json=rag_descriptor,
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
                "document_type": document_type,
                "content_kind": content_kind,
                "file_extension": ext,
                "file_mime_type": mime,
                "file_size_bytes": len(raw),
                "rag_ready": True,
            },
            created_by="dashboard",
        )
    except Exception:
        logger.exception("best-effort version/change tracking failed for project_id=%s", project_id)

    refreshed = await db.fetch_one(
        """
        SELECT document_id, project_id, document_name, document_type, file_extension,
               file_mime_type, file_size_bytes, serialization_status, embedding_status, created_at, updated_at
        FROM main.project_document
        WHERE project_id = $1 AND document_id = $2
        """,
        project_id,
        int(row.get("document_id") or 0),
    )
    return dict(refreshed) if refreshed else row


@router.delete("/projects/{project_id}/documents/{document_id}")
async def delete_document(
    project_id: int,
    document_id: int,
    db: DatabaseManager = Depends(get_db),
):
    deleted = await db.delete_documents(project_id, [document_id])
    if deleted <= 0:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"deleted": True, "document_id": document_id}


@router.post("/projects/{project_id}/documents/batch-delete")
async def batch_delete_documents(
    project_id: int,
    body: BatchDeleteDocumentsBody,
    db: DatabaseManager = Depends(get_db),
):
    p = await db.get_project_by_id(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    deleted = await db.delete_documents(project_id, body.document_ids)
    if deleted <= 0:
        raise HTTPException(status_code=404, detail="No matching documents found")
    return {"deleted": deleted, "document_ids": body.document_ids}
