"""Sync design context staging for Temporal task execution (mirrors dashboard design_context_service)."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from temporal.utils.db import get_connection

logger = logging.getLogger(__name__)


def _tokens_to_css(tokens: Dict[str, Any]) -> str:
    lines = [":root {"]
    for group in ("colors", "typography", "spacing"):
        for key, val in (tokens.get(group) or {}).items():
            lines.append(f"  {key}: {val};")
    lines.append("}")
    return "\n".join(lines)


def stage_design_context_sync(project_id: int, worktree_path: str) -> Dict[str, Any]:
    """Stage active Figma v2 design context into worktree (sync, for Temporal activities)."""
    root = Path(worktree_path) / ".midnight" / "design"
    sections_dir = root / "sections"
    assets_dir = root / "assets"
    exports_dir = root / "exports"
    for d in (root, sections_dir, assets_dir, exports_dir):
        d.mkdir(parents=True, exist_ok=True)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT document_id, parent_document_id, document_name, document_type,
                       raw_text_content, structured_json, file_content,
                       COALESCE(is_active_version, true) AS is_active_version
                FROM main.project_document
                WHERE project_id = %s
                ORDER BY document_id
                """,
                (project_id,),
            )
            rows = cur.fetchall()
            colnames = [d[0] for d in cur.description]
            doc_rows = [dict(zip(colnames, row)) for row in rows]

    imports = [
        r for r in doc_rows
        if r.get("document_type") == "figma_import" and r.get("is_active_version")
    ]
    if not imports:
        return {"ok": False, "skipped": True}

    imp = imports[-1]
    structured = imp.get("structured_json")
    if isinstance(structured, str):
        structured = json.loads(structured)
    ac = (structured or {}).get("agent_context") or {}
    staged: List[str] = []

    if ac.get("compact_spec"):
        p = root / "figma-spec.json"
        p.write_text(json.dumps(ac["compact_spec"], indent=2), encoding="utf-8")
        staged.append(str(p.relative_to(worktree_path)))

    raw = imp.get("raw_text_content") or ac.get("text_preview") or ""
    if raw:
        p = root / "figma-spec.md"
        p.write_text(raw, encoding="utf-8")
        staged.append(str(p.relative_to(worktree_path)))

    tokens = ac.get("tokens") or {}
    if tokens:
        p = root / "tokens.css"
        p.write_text(_tokens_to_css(tokens), encoding="utf-8")
        staged.append(str(p.relative_to(worktree_path)))

    slug_by_doc: Dict[int, str] = {}
    for sec in ac.get("sections") or []:
        slug = str(sec.get("slug") or "section")
        slug_by_doc[int(sec.get("section_export_document_id") or 0)] = slug
        sec_path = sections_dir / f"{slug}.json"
        sec_path.write_text(json.dumps(sec, indent=2), encoding="utf-8")
        staged.append(str(sec_path.relative_to(worktree_path)))

    asset_manifest: Dict[str, Any] = {"assets": [], "sections": []}
    export_idx = 0
    for row in doc_rows:
        if not row.get("is_active_version"):
            continue
        doc_id = int(row.get("document_id") or 0)
        doc_type = row.get("document_type")
        content = row.get("file_content")
        if not content:
            continue
        if isinstance(content, memoryview):
            content = content.tobytes()

        if doc_type == "figma_section_export":
            export_idx += 1
            slug = slug_by_doc.get(doc_id) or f"section-{export_idx}"
            png = sections_dir / f"{slug}.png"
            png.write_bytes(content)
            staged.append(str(png.relative_to(worktree_path)))
            asset_manifest["sections"].append({"slug": slug, "png": str(png.relative_to(worktree_path))})
        elif doc_type == "figma_asset":
            sj = row.get("structured_json")
            if isinstance(sj, str):
                sj = json.loads(sj)
            filename = (sj or {}).get("filename") or f"asset-{doc_id}.png"
            ap = assets_dir / filename
            ap.write_bytes(content)
            staged.append(str(ap.relative_to(worktree_path)))
            asset_manifest["assets"].append({"node_id": (sj or {}).get("node_id"), "filename": filename})

    manifest_json = root / "ASSET_MANIFEST.json"
    manifest_json.write_text(json.dumps(asset_manifest, indent=2), encoding="utf-8")
    staged.append(str(manifest_json.relative_to(worktree_path)))

    manifest_md = root / "DESIGN_MANIFEST.md"
    lines = [
        "# Design Manifest (binding — v2)",
        "",
        f"Staged at: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Sections",
    ]
    for sec in ac.get("sections") or []:
        lines.append(f"- {sec.get('name')} (`{sec.get('slug')}`)")
    manifest_md.write_text("\n".join(lines), encoding="utf-8")
    staged.insert(0, str(manifest_md.relative_to(worktree_path)))

    logger.info("Staged %s design files for project %s", len(staged), project_id)
    return {"ok": True, "files": staged, "section_count": len(ac.get("sections") or [])}
