"""Persistent, reusable project knowledge to avoid re-sending full context every task."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..database import DatabaseManager
from .project_metadata_service import project_metadata_service


class ProjectContextCacheService:
    async def get_cached_summary(
        self,
        db: DatabaseManager,
        project_id: int,
    ) -> Optional[Dict[str, Any]]:
        meta = await project_metadata_service.get_project_metadata(db, project_id)
        blob = meta.get("metadata") if isinstance(meta.get("metadata"), dict) else {}
        cache = blob.get("architecture_cache")
        return cache if isinstance(cache, dict) else None

    def build_architecture_summary(self, context_pack: Dict[str, Any]) -> Dict[str, Any]:
        project = context_pack.get("project") or {}
        metadata = context_pack.get("project_metadata") or {}
        meta_blob = metadata.get("metadata") if isinstance(metadata.get("metadata"), dict) else {}
        runtime = metadata.get("runtime_preferences") if isinstance(metadata.get("runtime_preferences"), dict) else {}
        rag = context_pack.get("rag_ready_context") or {}
        docs = rag.get("documents") or []
        tasks = context_pack.get("tasks") or []
        design = context_pack.get("design_staging") or {}

        doc_index: List[Dict[str, Any]] = []
        for doc in docs[:24]:
            doc_index.append(
                {
                    "document_id": doc.get("document_id"),
                    "name": doc.get("name") or doc.get("document_name"),
                    "kind": doc.get("content_kind") or doc.get("document_type"),
                }
            )

        task_index: List[Dict[str, Any]] = []
        for task in tasks[:16]:
            td = task.get("task_data") if isinstance(task.get("task_data"), dict) else {}
            task_index.append(
                {
                    "task_id": task.get("task_id"),
                    "task_name": task.get("task_name"),
                    "task_type": task.get("task_type"),
                    "status": task.get("status"),
                    "milestone_index": td.get("milestone_index"),
                    "design_section_slug": td.get("design_section_slug"),
                }
            )

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "project_id": project.get("project_id"),
            "project_name": project.get("project_name"),
            "repo_path": runtime.get("repo_path"),
            "analysis_goal": meta_blob.get("analysis_goal"),
            "document_count": len(docs),
            "task_count": len(tasks),
            "documents_index": doc_index,
            "task_index": task_index,
            "design_staging": {
                "asset_count": design.get("asset_count"),
                "section_count": design.get("section_count"),
                "manifest_path": ".midnight/design/DESIGN_MANIFEST.md",
            },
            "stable_guidance": [
                "Reuse staged design files under .midnight/design/ — do not re-fetch full Figma exports.",
                "Read .midnight/context/manifest.json for live context file index.",
                "Prefer editing only files relevant to the active task.",
            ],
        }

    async def refresh_cache(
        self,
        db: DatabaseManager,
        project_id: int,
        context_pack: Dict[str, Any],
    ) -> Dict[str, Any]:
        summary = self.build_architecture_summary(context_pack)
        meta = await project_metadata_service.get_project_metadata(db, project_id)
        blob = dict(meta.get("metadata") or {})
        blob["architecture_cache"] = summary
        await project_metadata_service.update_project_metadata(
            db,
            project_id,
            metadata=blob,
        )
        return summary

    def compact_cached_summary(self, cache: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not cache:
            return None
        return {
            "project_name": cache.get("project_name"),
            "analysis_goal": cache.get("analysis_goal"),
            "document_count": cache.get("document_count"),
            "task_count": cache.get("task_count"),
            "documents_index": (cache.get("documents_index") or [])[:8],
            "task_index": (cache.get("task_index") or [])[:8],
            "design_staging": cache.get("design_staging"),
            "stable_guidance": (cache.get("stable_guidance") or [])[:3],
            "cached": True,
        }


project_context_cache_service = ProjectContextCacheService()
