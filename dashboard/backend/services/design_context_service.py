"""Stage Figma design assets into worktrees for CLI agent inspection."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..database import DatabaseManager
from .figma_service import tokens_to_css
from .layout_codegen_service import generate_section_layout_css


class DesignContextService:
    DESIGN_DIR = ".midnight/design"
    FIGMA_DOC_TYPES = frozenset(
        {"figma_import", "figma_export_image", "figma_section_export", "figma_asset"}
    )

    def _parse_structured(self, raw: Any) -> Optional[Dict[str, Any]]:
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except Exception:
                return None
        return None

    async def _load_figma_rows(self, db: DatabaseManager, project_id: int) -> List[Dict[str, Any]]:
        rows = await db.fetch_many(
            """
            SELECT document_id, parent_document_id, document_name, document_type,
                   raw_text_content, structured_json, (file_content IS NOT NULL) AS has_binary,
                   COALESCE(is_active_version, true) AS is_active_version
            FROM main.project_document
            WHERE project_id = $1
            ORDER BY document_id
            """,
            project_id,
        )
        return [dict(r) for r in rows]

    def _active_imports(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        imports = []
        for row in rows:
            if (
                str(row.get("document_type") or "") == "figma_import"
                and row.get("is_active_version")
            ):
                structured = self._parse_structured(row.get("structured_json"))
                agent_context = (structured or {}).get("agent_context") or {}
                imports.append(
                    {
                        "document_id": row.get("document_id"),
                        "document_name": row.get("document_name"),
                        "structured": structured,
                        "agent_context": agent_context,
                        "raw_text": row.get("raw_text_content"),
                    }
                )
        return imports

    async def validate_design_context(
        self,
        db: DatabaseManager,
        project_id: int,
    ) -> Dict[str, Any]:
        """Check whether active Figma imports have usable v2 spec, sections, assets."""
        rows = await self._load_figma_rows(db, project_id)
        figma_imports = self._active_imports(rows)

        child_exports = sum(
            1
            for r in rows
            if r.get("is_active_version")
            and str(r.get("document_type") or "")
            in {"figma_export_image", "figma_section_export"}
            and r.get("has_binary")
        )
        child_assets = sum(
            1
            for r in rows
            if r.get("is_active_version")
            and str(r.get("document_type") or "") == "figma_asset"
            and r.get("has_binary")
        )

        if not figma_imports:
            return {
                "ok": True,
                "required": False,
                "structural_ready": True,
                "figma_imports": [],
                "sections": [],
                "assets": [],
                "export_count": child_exports,
                "asset_count": child_assets,
                "gaps": [],
            }

        gaps: List[str] = []
        sections: List[Dict[str, Any]] = []
        assets: List[Dict[str, Any]] = []
        has_image_nodes = False
        blocking_warnings: List[str] = []

        for imp in figma_imports:
            ac = imp["agent_context"]
            if not (ac.get("compact_spec") or ac.get("text_preview") or imp.get("raw_text")):
                gaps.append(f"Figma import '{imp.get('document_name')}' has no compact spec.")
            for sec in ac.get("sections") or []:
                sections.append(sec)
                if not sec.get("section_export_document_id"):
                    gaps.append(f"Section '{sec.get('slug')}' missing PNG export.")
            for asset in ac.get("assets") or []:
                assets.append(asset)
            for w in ac.get("extraction_warnings") or []:
                if isinstance(w, dict) and w.get("severity") == "blocking":
                    blocking_warnings.append(str(w.get("message")))
            spec_tree = (ac.get("compact_spec") or {}).get("tree") or {}
            has_image_nodes = has_image_nodes or self._tree_has_image_fill(spec_tree)

        if not sections:
            gaps.append("No design sections extracted from Figma import.")
        if has_image_nodes and child_assets == 0 and not assets:
            gaps.append(
                "Design contains IMAGE fills but no figma_asset exports were persisted. Re-import from Figma."
            )
        gaps.extend(blocking_warnings)

        usable = bool(sections) and not blocking_warnings
        structural_ready = usable and (not has_image_nodes or child_assets > 0 or bool(assets))

        return {
            "ok": usable,
            "required": True,
            "structural_ready": structural_ready,
            "figma_imports": [
                {
                    "document_id": i.get("document_id"),
                    "document_name": i.get("document_name"),
                    "section_count": len(i["agent_context"].get("sections") or []),
                    "asset_count": len(i["agent_context"].get("assets") or []),
                    "extraction_version": i["agent_context"].get("extraction_version"),
                }
                for i in figma_imports
            ],
            "sections": sections,
            "assets": assets,
            "export_count": child_exports,
            "asset_count": child_assets,
            "gaps": gaps,
            "tokens_available": bool(
                figma_imports
                and (
                    figma_imports[0]["agent_context"].get("tokens")
                    or figma_imports[0]["agent_context"].get("tokens_css")
                )
            ),
        }

    def _tree_has_image_fill(self, node: Any) -> bool:
        if not isinstance(node, dict):
            return False
        if node.get("fillType") == "IMAGE":
            return True
        for child in node.get("children") or []:
            if self._tree_has_image_fill(child):
                return True
        return False

    async def stage_design_context(
        self,
        db: DatabaseManager,
        *,
        project_id: int,
        worktree_path: str,
    ) -> Dict[str, Any]:
        """Write Figma v2 spec, sections, assets, and tokens into the worktree."""
        root = Path(worktree_path) / self.DESIGN_DIR
        sections_dir = root / "sections"
        assets_dir = root / "assets"
        exports_dir = root / "exports"
        for d in (root, sections_dir, assets_dir, exports_dir):
            d.mkdir(parents=True, exist_ok=True)

        rows = await self._load_figma_rows(db, project_id)
        imports = self._active_imports(rows)
        if not imports:
            return {"ok": False, "files": [], "export_count": 0, "spec_written": False}

        imp = imports[-1]
        ac = imp["agent_context"]
        staged_files: List[str] = []
        export_index = 0
        asset_manifest: Dict[str, Any] = {"assets": [], "sections": []}

        compact_spec = ac.get("compact_spec")
        if compact_spec:
            spec_path = root / "figma-spec.json"
            spec_path.write_text(json.dumps(compact_spec, indent=2, default=str), encoding="utf-8")
            staged_files.append(str(spec_path.relative_to(worktree_path)))

        md_content = imp.get("raw_text") or ac.get("text_preview") or ""
        if md_content:
            md_path = root / "figma-spec.md"
            md_path.write_text(md_content, encoding="utf-8")
            staged_files.append(str(md_path.relative_to(worktree_path)))

        tokens = ac.get("tokens") or {}
        tokens_css = ac.get("tokens_css")
        if tokens or tokens_css:
            css_path = root / "tokens.css"
            css_text = tokens_to_css(tokens) if tokens else str(tokens_css)
            css_path.write_text(css_text, encoding="utf-8")
            staged_files.append(str(css_path.relative_to(worktree_path)))

        active_parent_id = imp.get("document_id")
        sections_order = ac.get("sections_order") or []
        section_slug_by_doc: Dict[int, str] = {}
        for sec in ac.get("sections") or []:
            slug = str(sec.get("slug") or "section")
            sec_json = sections_dir / f"{slug}.json"
            layout_css = sec.get("layout_css")
            if not layout_css:
                section_assets = [
                    a for a in (ac.get("assets") or []) if str(a.get("section_slug") or "") == slug
                ]
                layout_css = generate_section_layout_css(
                    slug,
                    section_box=sec.get("box"),
                    semantic_elements=sec.get("semantic_elements") or [],
                    assets=section_assets,
                )
            sec_payload = {
                "slug": slug,
                "name": sec.get("name"),
                "node_id": sec.get("node_id"),
                "order": sec.get("order"),
                "position_y": sec.get("position_y"),
                "section_role": sec.get("section_role"),
                "section_role_confidence": sec.get("section_role_confidence"),
                "semantic_elements": sec.get("semantic_elements") or [],
                "box": sec.get("box"),
                "node_count": sec.get("node_count"),
                "manifest_text": sec.get("manifest_text"),
                "tree": sec.get("tree"),
                "tree_omitted": sec.get("tree_omitted"),
            }
            sec_json.write_text(json.dumps(sec_payload, indent=2, default=str), encoding="utf-8")
            staged_files.append(str(sec_json.relative_to(worktree_path)))
            layout_path = sections_dir / f"{slug}.layout.css"
            layout_path.write_text(str(layout_css), encoding="utf-8")
            staged_files.append(str(layout_path.relative_to(worktree_path)))
            if isinstance(sec.get("tree"), dict):
                tree_path = sections_dir / f"{slug}.tree.json"
                tree_path.write_text(json.dumps(sec.get("tree"), indent=2, default=str), encoding="utf-8")
                staged_files.append(str(tree_path.relative_to(worktree_path)))
            doc_id = sec.get("section_export_document_id")
            if doc_id:
                section_slug_by_doc[int(doc_id)] = slug

        if sections_order:
            order_path = root / "sections-order.json"
            order_path.write_text(json.dumps(sections_order, indent=2, default=str), encoding="utf-8")
            staged_files.append(str(order_path.relative_to(worktree_path)))

        for row in rows:
            if not row.get("is_active_version"):
                continue
            doc_type = str(row.get("document_type") or "")
            doc_id = int(row.get("document_id") or 0)
            parent_id = row.get("parent_document_id")

            if doc_type == "figma_section_export" and row.get("has_binary"):
                slug = section_slug_by_doc.get(doc_id)
                if not slug:
                    structured = self._parse_structured(row.get("structured_json"))
                    slug = (structured or {}).get("section_slug") or f"section-{export_index + 1}"
                file_row = await db.get_document_file(project_id, doc_id)
                if file_row and file_row.get("file_content"):
                    export_index += 1
                    png_path = sections_dir / f"{slug}.png"
                    content = file_row["file_content"]
                    if isinstance(content, memoryview):
                        content = content.tobytes()
                    png_path.write_bytes(content)
                    staged_files.append(str(png_path.relative_to(worktree_path)))
                    legacy_path = exports_dir / f"frame-{export_index}.png"
                    legacy_path.write_bytes(content)
                    staged_files.append(str(legacy_path.relative_to(worktree_path)))
                    asset_manifest["sections"].append(
                        {"slug": slug, "png": str(png_path.relative_to(worktree_path))}
                    )

            elif doc_type == "figma_asset" and row.get("has_binary"):
                structured = self._parse_structured(row.get("structured_json"))
                filename = (structured or {}).get("filename") or f"asset-{doc_id}.png"
                file_row = await db.get_document_file(project_id, doc_id)
                if file_row and file_row.get("file_content"):
                    asset_path = assets_dir / filename
                    content = file_row["file_content"]
                    if isinstance(content, memoryview):
                        content = content.tobytes()
                    asset_path.write_bytes(content)
                    staged_files.append(str(asset_path.relative_to(worktree_path)))
                    asset_manifest["assets"].append(
                        {
                            "node_id": (structured or {}).get("node_id"),
                            "filename": filename,
                            "path": str(asset_path.relative_to(worktree_path)),
                            "asset_type": (structured or {}).get("asset_type"),
                            "section_slug": (structured or {}).get("section_slug"),
                            "box": next(
                                (
                                    a.get("box")
                                    for a in (ac.get("assets") or [])
                                    if str(a.get("filename") or "") == filename
                                ),
                                None,
                            ),
                        }
                    )

            elif doc_type == "figma_export_image" and row.get("has_binary"):
                if parent_id == active_parent_id or parent_id is None:
                    file_row = await db.get_document_file(project_id, doc_id)
                    if file_row and file_row.get("file_content"):
                        export_index += 1
                        export_path = exports_dir / f"frame-{export_index}.png"
                        content = file_row["file_content"]
                        if isinstance(content, memoryview):
                            content = content.tobytes()
                        export_path.write_bytes(content)
                        staged_files.append(str(export_path.relative_to(worktree_path)))

        manifest_json_path = root / "ASSET_MANIFEST.json"
        manifest_json_path.write_text(
            json.dumps(asset_manifest, indent=2, default=str), encoding="utf-8"
        )
        staged_files.append(str(manifest_json_path.relative_to(worktree_path)))

        manifest_path = root / "DESIGN_MANIFEST.md"
        manifest_lines = [
            "# Design Manifest (binding — v2)",
            "",
            "UI implementation **must** match these staged Figma assets. Stock photo URLs are forbidden.",
            "",
            "## Required reading order",
            "1. Read `sections-order.json` for top-to-bottom section order and inferred roles.",
            "2. Read `tokens.css` and apply CSS variables.",
            "3. Read `ASSET_MANIFEST.json` — map assets to elements by `node_id` and use listed `box` coordinates.",
            "4. For each section: read `sections/{slug}.json` (`semantic_elements[].box`), apply `sections/{slug}.layout.css`, verify with `sections/{slug}.png`.",
            "5. Reference `sections/{slug}.tree.json` or `figma-spec.json` for full tree when present.",
            "",
            "## Sections (top → bottom)",
            "",
        ]
        ordered_secs = sorted(
            ac.get("sections") or [],
            key=lambda s: (
                int(s.get("order") or 999),
                float((s.get("box") or {}).get("y") or 0) if isinstance(s.get("box"), dict) else 0,
            ),
        )
        for sec in ordered_secs:
            slug = sec.get("slug")
            role = sec.get("section_role") or "content_section"
            order = sec.get("order") or "?"
            manifest_lines.append(
                f"- [ ] **{order}. {sec.get('name')}** (`{slug}`, role: `{role}`) — "
                f"`sections/{slug}.json` + `sections/{slug}.layout.css` + `sections/{slug}.png`"
            )
        manifest_lines.extend(["", "## Staged files", ""])
        for rel in sorted(set(staged_files)):
            manifest_lines.append(f"- `{rel}`")
        manifest_lines.extend(["", f"Staged at: {datetime.now(timezone.utc).isoformat()}"])
        manifest_path.write_text("\n".join(manifest_lines), encoding="utf-8")
        staged_files.insert(0, str(manifest_path.relative_to(worktree_path)))

        return {
            "ok": bool(staged_files),
            "design_dir": str(root),
            "manifest": str(manifest_path),
            "files": staged_files,
            "export_count": export_index,
            "section_count": len(ac.get("sections") or []),
            "asset_count": len(asset_manifest.get("assets") or []),
            "spec_written": bool(compact_spec),
            "extraction_version": ac.get("extraction_version") or "v2",
        }


design_context_service = DesignContextService()
