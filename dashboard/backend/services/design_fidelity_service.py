"""Structural and advisory visual design fidelity checks."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import app_config

logger = logging.getLogger(__name__)

_STOCK_PHOTO_PATTERNS = (
    r"unsplash\.com",
    r"placehold\.co",
    r"picsum\.photos",
    r"placeholder\.com",
    r"loremflickr\.com",
    r"via\.placeholder",
)


class DesignFidelityService:
    def scan_changed_files(
        self,
        worktree_path: str,
        changed_files: Optional[List[str]] = None,
    ) -> List[Path]:
        root = Path(worktree_path)
        if changed_files:
            paths = []
            for rel in changed_files:
                p = root / rel
                if p.is_file():
                    paths.append(p)
            return paths
        # Fallback: scan common UI extensions
        exts = {".html", ".css", ".scss", ".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte"}
        return [p for p in root.rglob("*") if p.suffix.lower() in exts and p.is_file()]

    def check_stock_photos(self, file_paths: List[Path]) -> Dict[str, Any]:
        hits: List[Dict[str, str]] = []
        for path in file_paths:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for pattern in _STOCK_PHOTO_PATTERNS:
                if re.search(pattern, text, re.I):
                    hits.append({"file": str(path), "pattern": pattern})
                    break
        return {"ok": len(hits) == 0, "hits": hits}

    def check_asset_manifest_usage(
        self,
        worktree_path: str,
        file_paths: List[Path],
    ) -> Dict[str, Any]:
        manifest_path = Path(worktree_path) / ".midnight" / "design" / "ASSET_MANIFEST.json"
        if not manifest_path.exists():
            return {"ok": True, "skipped": True, "missing_refs": []}
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"ok": True, "skipped": True, "missing_refs": []}

        combined = ""
        for path in file_paths:
            try:
                combined += path.read_text(encoding="utf-8", errors="ignore") + "\n"
            except OSError:
                pass

        missing: List[str] = []
        for asset in manifest.get("assets") or []:
            filename = str(asset.get("filename") or "")
            node_id = str(asset.get("node_id") or "")
            if filename and filename not in combined and node_id.replace(":", "-") not in combined:
                missing.append(filename or node_id)

        # Only fail if we have assets and none referenced
        assets = manifest.get("assets") or []
        ok = not assets or len(missing) < len(assets)
        return {"ok": ok, "missing_refs": missing, "total_assets": len(assets)}

    def check_tokens_usage(self, worktree_path: str, file_paths: List[Path]) -> Dict[str, Any]:
        tokens_path = Path(worktree_path) / ".midnight" / "design" / "tokens.css"
        if not tokens_path.exists():
            return {"ok": True, "skipped": True}
        css_text = tokens_path.read_text(encoding="utf-8", errors="ignore")
        vars_found = re.findall(r"(--[\w-]+)\s*:", css_text)
        if not vars_found:
            return {"ok": True, "skipped": True}

        combined = ""
        for path in file_paths:
            if path.suffix.lower() in {".css", ".scss", ".html", ".tsx", ".jsx", ".vue"}:
                try:
                    combined += path.read_text(encoding="utf-8", errors="ignore") + "\n"
                except OSError:
                    pass
        used = [v for v in vars_found if f"var({v})" in combined or v in combined]
        ok = len(used) > 0 or "tokens.css" in combined
        return {"ok": ok, "vars_defined": len(vars_found), "vars_used": len(used)}

    def check_section_landmarks(
        self,
        worktree_path: str,
        sections: List[Dict[str, Any]],
        file_paths: List[Path],
    ) -> Dict[str, Any]:
        if not sections:
            return {"ok": True, "skipped": True, "missing": []}
        html_paths = [p for p in file_paths if p.suffix.lower() in {".html", ".tsx", ".jsx", ".vue"}]
        if not html_paths:
            return {"ok": True, "skipped": True, "missing": []}
        combined = ""
        for path in html_paths:
            try:
                combined += path.read_text(encoding="utf-8", errors="ignore") + "\n"
            except OSError:
                pass
        missing = []
        for sec in sections:
            slug = str(sec.get("slug") or "")
            if not slug:
                continue
            if f'data-section="{slug}"' not in combined and f"id=\"{slug}\"" not in combined:
                if f"data-section='{slug}'" not in combined and f"id='{slug}'" not in combined:
                    missing.append(slug)
        ok = len(missing) == 0
        return {"ok": ok, "missing": missing, "total_sections": len(sections)}

    def advisory_visual_diff(
        self,
        worktree_path: str,
        sections: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Advisory per-section visual scores (requires Pillow; never blocks)."""
        if not app_config.design_fidelity_visual_advisory:
            return {"ok": True, "advisory": True, "skipped": True, "sections": []}

        try:
            from PIL import Image, ImageChops, ImageStat  # type: ignore
        except ImportError:
            return {
                "ok": True,
                "advisory": True,
                "skipped": True,
                "reason": "Pillow not installed",
                "sections": [],
            }

        design_root = Path(worktree_path) / ".midnight" / "design" / "sections"
        results: List[Dict[str, Any]] = []
        for sec in sections:
            slug = str(sec.get("slug") or "")
            png_path = design_root / f"{slug}.png"
            if not png_path.exists():
                results.append({"slug": slug, "score": None, "note": "no reference PNG"})
                continue
            try:
                ref = Image.open(png_path).convert("RGB")
                # Without Playwright we cannot capture live preview; record reference dimensions as baseline
                results.append(
                    {
                        "slug": slug,
                        "score": None,
                        "advisory": True,
                        "reference_size": ref.size,
                        "note": "Visual capture unavailable; reference PNG staged for manual comparison.",
                    }
                )
            except Exception as e:
                results.append({"slug": slug, "score": None, "error": str(e)})

        return {"ok": True, "advisory": True, "sections": results}

    def run_structural_checks(
        self,
        *,
        worktree_path: Optional[str],
        context_pack: Optional[Dict[str, Any]] = None,
        changed_files: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        if not worktree_path:
            return {"ok": True, "skipped": True, "reason": "no worktree"}

        design_required = False
        sections: List[Dict[str, Any]] = []
        if context_pack:
            rag = context_pack.get("rag_ready_context") or {}
            for doc in rag.get("documents") or []:
                if str(doc.get("content_kind") or "").lower() == "figma_import":
                    design_required = True
                    sections.extend(doc.get("design_sections") or [])

        design_dir = Path(worktree_path) / ".midnight" / "design"
        if not design_dir.exists() and not design_required:
            return {"ok": True, "skipped": True, "reason": "no design context"}

        file_paths = self.scan_changed_files(worktree_path, changed_files)
        if not file_paths:
            file_paths = self.scan_changed_files(worktree_path)

        stock = self.check_stock_photos(file_paths)
        assets = self.check_asset_manifest_usage(worktree_path, file_paths)
        tokens = self.check_tokens_usage(worktree_path, file_paths)
        landmarks = self.check_section_landmarks(worktree_path, sections, file_paths)
        visual = self.advisory_visual_diff(worktree_path, sections)

        structural_ok = stock["ok"] and assets["ok"] and tokens["ok"] and landmarks["ok"]
        hard_block = app_config.design_fidelity_structural_block and design_required

        return {
            "ok": structural_ok or not hard_block,
            "structural_pass": structural_ok,
            "hard_block_enabled": hard_block,
            "stock_photos": stock,
            "assets_used": assets,
            "tokens_used": tokens,
            "section_landmarks": landmarks,
            "visual_fidelity": visual,
            "blocking_failures": [] if structural_ok else [
                name for name, check in [
                    ("stock_photos", stock),
                    ("assets_used", assets),
                    ("tokens_used", tokens),
                    ("section_landmarks", landmarks),
                ] if not check.get("ok") and not check.get("skipped")
            ],
        }


design_fidelity_service = DesignFidelityService()
