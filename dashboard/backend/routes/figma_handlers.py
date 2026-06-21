"""Figma API handlers (mounted on existing routers for reliable reload)."""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field

from ..config import app_config
from ..database import DatabaseManager
from ..services.document_version_service import document_version_service
from ..services.project_metadata_service import project_metadata_service
from ..services.figma_service import (
    FigmaService,
    build_figma_rag_descriptor,
    parse_figma_reference,
    slugify_name,
)
from ..services.jsonb_utils import jsonb_dumps

logger = logging.getLogger(__name__)
_figma = FigmaService(default_token=app_config.figma_access_token)


class FigmaTokenBody(BaseModel):
    token: str = Field(..., min_length=8)


class FigmaImportBody(BaseModel):
    url: str = Field(..., min_length=8, description="Figma design URL or file key")
    notes: Optional[str] = Field(None, max_length=8000)
    token: Optional[str] = Field(None, description="Personal access token (overrides server env)")


def _node_filename(node_id: str, ext: str) -> str:
    return f"{str(node_id).replace(':', '-')}{ext}"


async def _persist_child_image(
    db: DatabaseManager,
    *,
    project_id: int,
    parent_document_id: int,
    document_name: str,
    document_type: str,
    file_bytes: bytes,
    ext: str,
    mime: str,
    structured_json: Optional[Dict[str, Any]] = None,
) -> int:
    row = await db.insert_document_upload(
        project_id=project_id,
        document_name=document_name[:255],
        document_type=document_type,
        raw_text=None,
        ext=ext,
        mime=mime,
        size=len(file_bytes),
        file_bytes=file_bytes,
        parent_document_id=parent_document_id,
        structured_json=structured_json,
    )
    doc_id = int(row.get("document_id") or 0)
    if doc_id:
        await db.execute(
            """
            UPDATE main.project_document
            SET serialization_status = 'RAG_READY',
                embedding_status = 'READY_FOR_EMBEDDING',
                updated_at = NOW()
            WHERE project_id = $1 AND document_id = $2
            """,
            project_id,
            doc_id,
        )
    return doc_id


async def import_figma_design_handler(
    project_id: int,
    body: FigmaImportBody,
    db: DatabaseManager,
) -> dict:
    project = await db.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        design = await _figma.fetch_design(
            body.url,
            token=body.token,
            user_notes=body.notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("figma import failed project_id=%s", project_id)
        raise HTTPException(status_code=502, detail=f"Figma import failed: {e}") from e

    warnings = design.get("warnings") or []
    blocking = [w for w in warnings if isinstance(w, dict) and w.get("severity") == "blocking"]
    if blocking:
        raise HTTPException(
            status_code=400,
            detail="; ".join(str(w.get("message")) for w in blocking),
        )

    file_key = design["file_key"]
    file_name = design["file_name"]
    node_id = design.get("node_id")
    spec = design["spec"]
    agent_text = design["agent_text"]
    user_notes = design.get("user_notes")
    extraction_version = design.get("extraction_version") or "v2"
    sections: List[Dict[str, Any]] = list(design.get("sections") or [])
    asset_candidates: List[Dict[str, Any]] = list(design.get("assets") or [])

    try:
        _, parsed_node = parse_figma_reference(body.url)
    except ValueError:
        parsed_node = node_id

    await db.deactivate_figma_import_family(project_id, node_id=parsed_node or node_id)

    doc_name = f"Figma: {file_name}"
    if node_id and spec.get("root_name"):
        doc_name = f"Figma: {spec['root_name']}"

    row = await db.insert_document_upload(
        project_id=project_id,
        document_name=doc_name[:255],
        document_type="figma_import",
        raw_text=agent_text,
        ext=".md",
        mime="text/markdown",
        size=len(agent_text.encode("utf-8")),
        file_bytes=None,
    )
    document_id = int(row.get("document_id") or 0)

    image_document_ids: List[int] = []
    section_export_document_ids: List[int] = []
    asset_document_ids: List[int] = []
    asset_entries: List[Dict[str, Any]] = []

    section_export_by_node: Dict[str, int] = {}
    for idx, img in enumerate(design.get("section_exports") or design.get("export_images") or []):
        nid = str(img.get("node_id") or "")
        sec = next((s for s in sections if str(s.get("node_id")) == nid), None)
        slug = sec.get("slug") if sec else f"section-{idx + 1}"
        img_name = f"{doc_name} — {slug}"[:255]
        img_id = await _persist_child_image(
            db,
            project_id=project_id,
            parent_document_id=document_id,
            document_name=img_name,
            document_type="figma_section_export",
            file_bytes=img.get("bytes") or b"",
            ext=".png",
            mime="image/png",
            structured_json={
                "content_kind": "figma_section_export",
                "node_id": nid,
                "section_slug": slug,
                "parent_import_id": document_id,
            },
        )
        if img_id:
            section_export_document_ids.append(img_id)
            image_document_ids.append(img_id)
            section_export_by_node[nid] = img_id
            if sec:
                sec["section_export_document_id"] = img_id

    asset_bytes_by_node: Dict[str, Dict[str, Any]] = {}
    for item in design.get("asset_exports") or []:
        nid = str(item.get("node_id") or "")
        if nid:
            asset_bytes_by_node[nid] = item

    for cand in asset_candidates:
        nid = str(cand.get("node_id") or "")
        exported = asset_bytes_by_node.get(nid)
        if not exported:
            continue
        asset_type = cand.get("asset_type") or "IMAGE"
        ext = ".svg" if asset_type == "VECTOR" else ".png"
        mime = "image/svg+xml" if ext == ".svg" else "image/png"
        filename = _node_filename(nid, ext)
        asset_id = await _persist_child_image(
            db,
            project_id=project_id,
            parent_document_id=document_id,
            document_name=f"{doc_name} — {cand.get('name') or filename}"[:255],
            document_type="figma_asset",
            file_bytes=exported.get("bytes") or b"",
            ext=ext,
            mime=mime,
            structured_json={
                "content_kind": "figma_asset",
                "node_id": nid,
                "asset_type": asset_type,
                "section_slug": cand.get("section_slug"),
                "filename": filename,
                "parent_import_id": document_id,
            },
        )
        if asset_id:
            asset_document_ids.append(asset_id)
            asset_entries.append(
                {
                    "node_id": nid,
                    "document_id": asset_id,
                    "filename": filename,
                    "section_slug": cand.get("section_slug"),
                    "asset_type": asset_type,
                    "name": cand.get("name"),
                }
            )

    rag_descriptor = build_figma_rag_descriptor(
        file_key=file_key,
        file_name=file_name,
        node_id=node_id,
        reference=design["reference"],
        spec=spec,
        text_preview=design["text_preview"],
        user_notes=user_notes,
        image_document_ids=image_document_ids,
        sections=sections,
        assets=asset_entries,
        tokens=design.get("tokens"),
        section_export_document_ids=section_export_document_ids,
        asset_document_ids=asset_document_ids,
        extraction_warnings=warnings if isinstance(warnings, list) else [],
        extraction_version=extraction_version,
        extraction_status=design.get("extraction_status") or "figma_api_v2_ready",
        font_resolution=design.get("font_resolution"),
    )

    if document_id > 0:
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
            source="figma_api",
            change_summary=f"Imported from Figma API ({extraction_version})",
            raw_text_content=agent_text,
            structured_json=rag_descriptor,
            content_hash=None,
            created_by="dashboard",
        )

    existing_meta = await project_metadata_service.get_project_metadata(db, project_id)
    metadata = existing_meta.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    metadata["figma_source"] = {
        "url": body.url.strip(),
        "file_key": file_key,
        "node_id": parsed_node or node_id,
        "document_id": document_id,
        "active_document_id": document_id,
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "extraction_version": extraction_version,
        "section_count": len(sections),
        "asset_count": len(asset_entries),
        "import_warnings": [
            w.get("message") if isinstance(w, dict) else str(w) for w in warnings
        ],
    }
    await project_metadata_service.update_project_metadata(
        db,
        project_id,
        metadata=metadata,
        updated_by="figma-import",
    )

    section_summary = [
        {
            "slug": s.get("slug"),
            "name": s.get("name"),
            "node_id": s.get("node_id"),
            "node_count": s.get("node_count"),
            "has_png": bool(s.get("section_export_document_id")),
            "section_export_document_id": s.get("section_export_document_id"),
        }
        for s in sections
    ]

    return {
        "ok": True,
        "document_id": document_id,
        "document_name": doc_name,
        "file_key": file_key,
        "node_id": parsed_node or node_id,
        "image_document_ids": image_document_ids,
        "section_export_document_ids": section_export_document_ids,
        "asset_document_ids": asset_document_ids,
        "node_count": spec.get("node_count"),
        "preview": design["text_preview"][:400],
        "warnings": warnings,
        "extraction_version": extraction_version,
        "extraction_status": design.get("extraction_status"),
        "sections": section_summary,
        "assets": asset_entries,
        "tokens_summary": {
            "colors": len((design.get("tokens") or {}).get("colors") or {}),
            "typography": len((design.get("tokens") or {}).get("typography") or {}),
            "spacing": len((design.get("tokens") or {}).get("spacing") or {}),
        },
    }


async def validate_figma_token_handler(body: FigmaTokenBody) -> dict:
    try:
        return await _figma.validate_token(body.token.strip())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("figma token validation failed")
        raise HTTPException(status_code=502, detail=f"Figma API error: {e}") from e


async def reimport_figma_for_project(
    db: DatabaseManager,
    *,
    project_id: int,
    url: Optional[str] = None,
    token: Optional[str] = None,
    notes: Optional[str] = None,
) -> dict:
    """Re-import Figma design from stored metadata or explicit URL."""
    existing_meta = await project_metadata_service.get_project_metadata(db, project_id)
    metadata = existing_meta.get("metadata") or {}
    figma_source = metadata.get("figma_source") if isinstance(metadata, dict) else None
    resolved_url = (url or "").strip()
    if not resolved_url and isinstance(figma_source, dict):
        resolved_url = str(figma_source.get("url") or "").strip()
    if not resolved_url:
        raise ValueError("No Figma URL provided and none stored in project metadata.")
    return await import_figma_design_handler(
        project_id,
        FigmaImportBody(url=resolved_url, notes=notes, token=token),
        db,
    )
