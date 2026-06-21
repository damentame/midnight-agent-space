"""Import MAS design packs exported by the Figma plugin (zip)."""
from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any, Dict, List, Optional, Tuple

from ..database import DatabaseManager
from .document_version_service import document_version_service
from .figma_service import build_figma_rag_descriptor
from .jsonb_utils import jsonb_dumps
from .project_metadata_service import project_metadata_service
from .layout_codegen_service import generate_section_layout_css

MAX_PREVIEW_CHARS = 4000
PLUGIN_FILE_KEY = "plugin-export"


def _safe_zip_paths(zf: zipfile.ZipFile) -> Dict[str, bytes]:
    """Read zip entries into a normalized path -> bytes map (no path traversal)."""
    out: Dict[str, bytes] = {}
    for info in zf.infolist():
        if info.is_dir():
            continue
        norm = PurePosixPath(info.filename.replace("\\", "/")).as_posix().lstrip("./")
        if not norm or norm.startswith("../") or "/../" in f"/{norm}/":
            continue
        out[norm] = zf.read(info)
    return out


def _read_json(files: Dict[str, bytes], path: str) -> Optional[Dict[str, Any]]:
    raw = files.get(path)
    if not raw:
        return None
    try:
        parsed = json.loads(raw.decode("utf-8"))
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _read_json_list(files: Dict[str, bytes], path: str) -> List[Any]:
    raw = files.get(path)
    if not raw:
        return []
    try:
        parsed = json.loads(raw.decode("utf-8"))
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def _read_text(files: Dict[str, bytes], path: str) -> str:
    raw = files.get(path)
    if not raw:
        return ""
    try:
        return raw.decode("utf-8")
    except Exception:
        return ""


def _section_sort_key(sec: Dict[str, Any]) -> tuple:
    order = sec.get("order")
    if order is not None:
        try:
            return (0, int(order))
        except (TypeError, ValueError):
            pass
    box = sec.get("box") if isinstance(sec.get("box"), dict) else {}
    try:
        y = float(box.get("y") or 0)
    except (TypeError, ValueError):
        y = 0.0
    return (1, y)


def _sort_sections(sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(sections, key=_section_sort_key)


def css_to_tokens(css: str) -> Dict[str, Any]:
    """Best-effort parse of plugin tokens.css into the tokens dict shape."""
    colors: Dict[str, str] = {}
    typography: Dict[str, Dict[str, Any]] = {}
    spacing: Dict[str, int] = {}

    for line in css.splitlines():
        m = re.match(r"\s*--([a-zA-Z0-9_-]+)\s*:\s*(.+?)\s*;?\s*$", line)
        if not m:
            continue
        key, value = m.group(1), m.group(2).strip()
        if value.startswith("#") or value.lower().startswith("rgb"):
            colors[f"--{key}"] = value
            continue
        fam = re.match(r"^text-(\d+)-family$", key)
        if fam:
            slug = f"text-{fam.group(1)}"
            typography.setdefault(slug, {})["fontFamily"] = value.strip("'\"")
            continue
        size = re.match(r"^text-(\d+)-size$", key)
        if size:
            slug = f"text-{size.group(1)}"
            typography.setdefault(slug, {})["fontSize"] = float(value.replace("px", ""))
            continue
        weight = re.match(r"^text-(\d+)-weight$", key)
        if weight:
            slug = f"text-{weight.group(1)}"
            typography.setdefault(slug, {})["fontWeight"] = int(float(value))
            continue
        gap = re.match(r"^gap-(\d+)$", key)
        if gap:
            spacing[f"--{key}"] = int(gap.group(1))
            continue
        pad = re.match(r"^padding-(\d+)$", key)
        if pad:
            spacing[f"--{key}"] = int(pad.group(1))

    return {"colors": colors, "typography": typography, "spacing": spacing}


def _discover_sections(files: Dict[str, bytes]) -> List[str]:
    slugs: List[str] = []
    for path in sorted(files):
        if path.startswith("sections/") and path.endswith(".png"):
            slug = PurePosixPath(path).stem
            json_path = f"sections/{slug}.json"
            if json_path in files and slug not in slugs:
                slugs.append(slug)
    return slugs


def parse_design_pack(zip_bytes: bytes) -> Tuple[Dict[str, bytes], Dict[str, Any], List[str]]:
    """Validate and parse a plugin design pack. Returns files map, meta dict, warnings."""
    warnings: List[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            files = _safe_zip_paths(zf)
    except zipfile.BadZipFile as exc:
        raise ValueError("Invalid zip file — export again from the Figma plugin.") from exc

    if not files:
        raise ValueError("Zip is empty.")

    section_slugs = _discover_sections(files)
    if not section_slugs:
        raise ValueError(
            "No section exports found. Expected sections/{slug}.png and sections/{slug}.json in the zip."
        )

    meta = _read_json(files, "mas-export.meta.json") or {}
    if not meta:
        warnings.append("mas-export.meta.json missing — using section files only.")

    return files, meta, warnings


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


async def import_design_pack(
    db: DatabaseManager,
    *,
    project_id: int,
    zip_bytes: bytes,
    user_notes: Optional[str] = None,
    pack_filename: Optional[str] = None,
) -> dict:
    """Ingest a Figma plugin design pack zip into project context."""
    files, meta, parse_warnings = parse_design_pack(zip_bytes)
    section_slugs = _discover_sections(files)
    asset_manifest = _read_json(files, "ASSET_MANIFEST.json") or {}
    manifest_sections = asset_manifest.get("sections") or []
    sections_order_meta = meta.get("sections_order") or _read_json_list(files, "sections-order.json")
    if not isinstance(sections_order_meta, list):
        sections_order_meta = []
    manifest_assets = asset_manifest.get("assets") or []

    file_name = str(meta.get("file_name") or pack_filename or "Plugin export").strip()
    node_id = str(meta.get("root_node_id") or "").strip() or None
    page_name = str(meta.get("page_name") or "").strip()
    extraction_version = str(meta.get("extraction_version") or "plugin-v1")
    plugin_warnings = meta.get("warnings") or []
    if isinstance(plugin_warnings, list):
        warnings = parse_warnings + [str(w) for w in plugin_warnings]
    else:
        warnings = list(parse_warnings)

    await db.deactivate_figma_import_family(project_id, node_id=None)

    design_spec = _read_text(files, "design-spec.md")
    design_manifest = _read_text(files, "DESIGN_MANIFEST.md")
    agent_text = design_spec or design_manifest or f"Figma plugin export: {file_name}"
    if user_notes:
        agent_text = f"{agent_text}\n\nUser notes: {user_notes.strip()}"

    doc_name = f"Figma: {file_name}"[:255]
    row = await db.insert_document_upload(
        project_id=project_id,
        document_name=doc_name,
        document_type="figma_import",
        raw_text=agent_text,
        ext=".md",
        mime="text/markdown",
        size=len(agent_text.encode("utf-8")),
        file_bytes=None,
    )
    document_id = int(row.get("document_id") or 0)

    section_export_document_ids: List[int] = []
    image_document_ids: List[int] = []
    asset_document_ids: List[int] = []
    asset_entries: List[Dict[str, Any]] = []
    sections: List[Dict[str, Any]] = []

    slug_order = section_slugs
    if manifest_sections:
        ordered = sorted(
            manifest_sections,
            key=lambda s: (
                int(s.get("order") or 999),
                float((s.get("position_y") if isinstance(s.get("position_y"), (int, float)) else 0) or 0),
            ),
        )
        slug_order = [str(s.get("slug")) for s in ordered if s.get("slug") in section_slugs] + [
            s for s in section_slugs if s not in {str(x.get("slug")) for x in ordered}
        ]
    elif sections_order_meta:
        slug_order = [str(s.get("slug")) for s in sections_order_meta if str(s.get("slug")) in section_slugs] + [
            s for s in section_slugs if s not in {str(x.get("slug")) for x in sections_order_meta}
        ]

    for slug in slug_order:
        sec_json = _read_json(files, f"sections/{slug}.json") or {}
        png_bytes = files.get(f"sections/{slug}.png")
        if not png_bytes:
            warnings.append(f"Section '{slug}' missing PNG — skipped.")
            continue

        img_name = f"{doc_name} — {sec_json.get('name') or slug}"[:255]
        img_id = await _persist_child_image(
            db,
            project_id=project_id,
            parent_document_id=document_id,
            document_name=img_name,
            document_type="figma_section_export",
            file_bytes=png_bytes,
            ext=".png",
            mime="image/png",
            structured_json={
                "content_kind": "figma_section_export",
                "node_id": sec_json.get("node_id"),
                "section_slug": slug,
                "parent_import_id": document_id,
            },
        )
        if img_id:
            section_export_document_ids.append(img_id)
            image_document_ids.append(img_id)

        sec_tree = sec_json.get("tree")
        sec_tree_omitted = bool(sec_json.get("tree_omitted"))
        section_assets_for_layout = [
            {
                "node_id": item.get("node_id"),
                "filename": item.get("filename"),
                "section_slug": item.get("section_slug"),
                "box": item.get("box"),
            }
            for item in manifest_assets
            if str(item.get("section_slug") or "") == slug
        ]
        layout_css = generate_section_layout_css(
            slug,
            section_box=sec_json.get("box"),
            semantic_elements=sec_json.get("semantic_elements") or [],
            assets=section_assets_for_layout,
        )

        sections.append(
            {
                "slug": slug,
                "name": sec_json.get("name") or slug,
                "node_id": sec_json.get("node_id"),
                "order": sec_json.get("order"),
                "position_y": sec_json.get("position_y"),
                "section_role": sec_json.get("section_role"),
                "section_role_confidence": sec_json.get("section_role_confidence"),
                "semantic_elements": sec_json.get("semantic_elements") or [],
                "box": sec_json.get("box"),
                "node_count": sec_json.get("node_count"),
                "manifest_text": sec_json.get("manifest_text"),
                "tree": sec_tree if isinstance(sec_tree, dict) else None,
                "tree_omitted": sec_tree_omitted,
                "layout_css": layout_css,
                "section_export_document_id": img_id or None,
            }
        )

    if not sections:
        raise ValueError("No section PNGs could be imported from the design pack.")

    sections = _sort_sections(sections)

    seen_asset_paths: set[str] = set()
    asset_items = manifest_assets if manifest_assets else []
    if not asset_items:
        for path in sorted(files):
            if path.startswith("assets/") and path not in seen_asset_paths:
                asset_items.append({"path": path, "filename": PurePosixPath(path).name})

    for item in asset_items:
        rel_path = str(item.get("path") or "").lstrip("/")
        filename = str(item.get("filename") or PurePosixPath(rel_path).name)
        if not rel_path:
            rel_path = f"assets/{filename}"
        if rel_path in seen_asset_paths:
            continue
        seen_asset_paths.add(rel_path)
        asset_bytes = files.get(rel_path)
        if not asset_bytes:
            warnings.append(f"Asset missing in zip: {rel_path}")
            continue

        ext = PurePosixPath(filename).suffix.lower() or ".png"
        asset_type = str(item.get("asset_type") or ("VECTOR" if ext == ".svg" else "IMAGE"))
        mime = "image/svg+xml" if ext == ".svg" else "image/png"
        asset_id = await _persist_child_image(
            db,
            project_id=project_id,
            parent_document_id=document_id,
            document_name=f"{doc_name} — {filename}"[:255],
            document_type="figma_asset",
            file_bytes=asset_bytes,
            ext=ext,
            mime=mime,
            structured_json={
                "content_kind": "figma_asset",
                "node_id": item.get("node_id"),
                "asset_type": asset_type,
                "section_slug": item.get("section_slug"),
                "filename": filename,
                "parent_import_id": document_id,
            },
        )
        if asset_id:
            asset_document_ids.append(asset_id)
            asset_entries.append(
                {
                    "node_id": item.get("node_id"),
                    "document_id": asset_id,
                    "filename": filename,
                    "section_slug": item.get("section_slug"),
                    "asset_type": asset_type,
                    "name": filename,
                    "box": item.get("box"),
                }
            )

    tokens_css = _read_text(files, "tokens.css")
    tokens = css_to_tokens(tokens_css) if tokens_css else {}
    figma_spec = _read_json(files, "figma-spec.json")
    compact_spec: Dict[str, Any] = figma_spec or {
        "file_name": file_name,
        "root_name": file_name,
        "page_name": page_name,
        "node_id": node_id,
        "extraction_version": extraction_version,
        "section_slugs": [s.get("slug") for s in sections],
        "sections_order": sections_order_meta or [
            {
                "order": s.get("order"),
                "slug": s.get("slug"),
                "name": s.get("name"),
                "position_y": s.get("position_y"),
                "section_role": s.get("section_role"),
            }
            for s in sections
        ],
    }

    rag_descriptor = build_figma_rag_descriptor(
        file_key=PLUGIN_FILE_KEY,
        file_name=file_name,
        node_id=node_id,
        reference="figma-plugin://design-pack",
        spec=compact_spec,
        text_preview=agent_text[:MAX_PREVIEW_CHARS],
        user_notes=user_notes,
        image_document_ids=image_document_ids,
        sections=sections,
        assets=asset_entries,
        tokens=tokens,
        section_export_document_ids=section_export_document_ids,
        asset_document_ids=asset_document_ids,
        extraction_warnings=[{"severity": "info", "message": w} for w in warnings],
        extraction_version=extraction_version,
        extraction_status="plugin_v1_ready",
        import_source="figma_plugin",
        tokens_css=tokens_css or None,
        design_manifest_md=design_manifest or None,
        sections_order=sections_order_meta or compact_spec.get("sections_order"),
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
            source="figma_plugin",
            change_summary=f"Imported from Figma plugin ({extraction_version})",
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
        "source": "figma_plugin",
        "pack_filename": pack_filename,
        "file_name": file_name,
        "node_id": node_id,
        "page_name": page_name,
        "document_id": document_id,
        "active_document_id": document_id,
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "extraction_version": extraction_version,
        "section_count": len(sections),
        "asset_count": len(asset_entries),
        "import_warnings": warnings,
    }
    await project_metadata_service.update_project_metadata(
        db,
        project_id,
        metadata=metadata,
        updated_by="design-pack-import",
    )

    section_summary = [
        {
            "slug": s.get("slug"),
            "name": s.get("name"),
            "node_id": s.get("node_id"),
            "order": s.get("order"),
            "position_y": s.get("position_y"),
            "section_role": s.get("section_role"),
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
        "file_key": PLUGIN_FILE_KEY,
        "node_id": node_id,
        "image_document_ids": image_document_ids,
        "section_export_document_ids": section_export_document_ids,
        "asset_document_ids": asset_document_ids,
        "node_count": sum(int(s.get("node_count") or 0) for s in sections),
        "preview": agent_text[:400],
        "warnings": warnings,
        "extraction_version": extraction_version,
        "extraction_status": "plugin_v1_ready",
        "import_source": "figma_plugin",
        "sections": section_summary,
        "assets": asset_entries,
        "tokens_summary": {
            "colors": len(tokens.get("colors") or {}),
            "typography": len(tokens.get("typography") or {}),
            "spacing": len(tokens.get("spacing") or {}),
        },
    }
