from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import app_config
from ..database import DatabaseManager
from .change_history_service import change_history_service
from .document_version_service import document_version_service
from .project_context_cache_service import project_context_cache_service
from .project_metadata_service import project_metadata_service


FIGMA_SPEC_CONTEXT_LIMIT = 1200  # legacy v1 analysis tasks only


class ContextPackService:
    def _is_implementation_task(self, task: Optional[Dict[str, Any]]) -> bool:
        if not task:
            return False
        ttype = str(task.get("task_type") or "").lower()
        name = str(task.get("task_name") or "").lower()
        return ttype in {"implementation", "design", "refactor"} or "implement section" in name

    def _section_slug_for_task(self, task: Optional[Dict[str, Any]]) -> Optional[str]:
        if not task:
            return None
        td = task.get("task_data")
        if isinstance(td, dict) and td.get("design_section_slug"):
            return str(td["design_section_slug"])
        name = str(task.get("task_name") or "")
        match = re.match(r"^Implement section \d+:\s*(\S+)", name, re.IGNORECASE)
        if match:
            return match.group(1).lower()
        if "Implement section:" in name:
            return name.split("Implement section:", 1)[-1].strip().lower()
        desc = str(task.get("description") or "")
        if "section:" in desc.lower():
            for token in desc.split():
                if token.startswith("sections/"):
                    return token.replace("sections/", "").replace(".json", "").strip("/")
        return None

    def _figma_spec_excerpt(
        self,
        document: Dict[str, Any],
        *,
        task: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        is_figma = (
            document.get("content_kind") == "figma_import"
            or document.get("document_type") == "figma_import"
        )
        if not is_figma:
            return None
        structured = document.get("_structured") or {}
        agent_context = structured.get("agent_context") or {}
        section_slug = self._section_slug_for_task(task)
        section_limit = app_config.context_pack_figma_section_chars
        use_section = self._is_implementation_task(task) or section_slug

        if section_slug:
            for sec in agent_context.get("sections") or []:
                if str(sec.get("slug")) == section_slug:
                    payload = {
                        "section": sec,
                        "manifest_text": sec.get("manifest_text"),
                        "staged_json": f".midnight/design/sections/{section_slug}.json",
                        "staged_png": f".midnight/design/sections/{section_slug}.png",
                    }
                    raw = json.dumps(payload, separators=(",", ":"), default=str)
                    return raw if len(raw) <= section_limit else raw[:section_limit] + "…"

        if use_section and agent_context.get("sections"):
            summary = {
                "extraction_version": agent_context.get("extraction_version"),
                "sections": agent_context.get("sections"),
                "tokens": agent_context.get("tokens"),
                "assets": agent_context.get("assets"),
            }
            raw = json.dumps(summary, separators=(",", ":"), default=str)
            limit = section_limit if use_section else FIGMA_SPEC_CONTEXT_LIMIT
            return raw if len(raw) <= limit else raw[:limit] + "…"

        preview = agent_context.get("text_preview")
        limit = section_limit if self._is_implementation_task(task) else FIGMA_SPEC_CONTEXT_LIMIT
        if preview:
            text = str(preview)
            return text if len(text) <= limit else text[:limit] + "…"
        spec = agent_context.get("compact_spec")
        if spec:
            raw = json.dumps(spec, separators=(",", ":"), default=str)
            return raw if len(raw) <= limit else raw[:limit] + "…"
        return None

    def _rag_document_entry(
        self,
        document: Dict[str, Any],
        versions: Any,
    ) -> Dict[str, Any]:
        latest_version = versions[0] if versions else {}
        ext = document.get("file_extension") or ""
        mime = document.get("file_mime_type") or ""
        content_kind = "text"
        if str(mime).startswith("image/") or ext in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}:
            content_kind = "image"
        elif document.get("document_type") == "figma_import" or document.get("content_kind") == "figma_import":
            content_kind = "figma_import"
        elif ext in {".fig", ".figma", ".sketch"} or "figma" in str(mime):
            content_kind = "figma_design"
        elif ext in {".pdf", ".docx"}:
            content_kind = "document_asset"
        elif not document.get("raw_text_preview"):
            content_kind = "binary_asset"

        figma_excerpt = None
        image_doc_ids = None
        section_export_ids = None
        asset_doc_ids = None
        design_sections = None
        if content_kind == "figma_import":
            structured = document.get("_structured") or {}
            ac = structured.get("agent_context") or {}
            figma_excerpt = self._figma_spec_excerpt(document)
            image_doc_ids = ac.get("image_document_ids")
            section_export_ids = ac.get("section_export_document_ids")
            asset_doc_ids = ac.get("asset_document_ids")
            design_sections = ac.get("sections")

        agent_usage = (
            "Use as direct text context."
            if content_kind == "text"
            else (
                "Figma v2 import: read .midnight/design/DESIGN_MANIFEST.md, sections/, assets/, tokens.css. "
                "Use ASSET_MANIFEST.json — stock photo URLs forbidden."
                if content_kind == "figma_import"
                else "Use as retrieval metadata and visual/design reference; inspect original asset when visual fidelity matters."
            )
        )

        entry: Dict[str, Any] = {
            "document_id": document.get("document_id"),
            "name": document.get("document_name"),
            "document_type": document.get("document_type"),
            "content_kind": content_kind,
            "file_extension": ext,
            "file_mime_type": mime,
            "file_size_bytes": document.get("file_size_bytes"),
            "serialization_status": document.get("serialization_status"),
            "latest_version": latest_version.get("version_number"),
            "latest_change_summary": latest_version.get("change_summary"),
            "text_preview": document.get("raw_text_preview"),
            "rag_ready": document.get("serialization_status") in {"READY", "RAG_READY"}
            or content_kind in {"text", "figma_import"},
            "agent_usage": agent_usage,
        }
        if figma_excerpt:
            entry["figma_spec_excerpt"] = figma_excerpt
        if image_doc_ids:
            entry["figma_image_document_ids"] = image_doc_ids
        if section_export_ids:
            entry["figma_section_export_document_ids"] = section_export_ids
        if asset_doc_ids:
            entry["figma_asset_document_ids"] = asset_doc_ids
        if design_sections:
            entry["design_sections"] = design_sections
        return entry

    @staticmethod
    def _task_search_text(task: Optional[Dict[str, Any]]) -> str:
        if not task:
            return ""
        parts = [
            str(task.get("task_name") or ""),
            str(task.get("task_type") or ""),
            str(task.get("description") or ""),
        ]
        td = task.get("task_data")
        if isinstance(td, dict):
            parts.append(str(td.get("goal") or ""))
        return " ".join(parts).lower()

    @staticmethod
    def _document_relevance_score(document: Dict[str, Any], task_text: str) -> float:
        name = str(document.get("name") or document.get("document_name") or "").lower()
        ext = str(document.get("file_extension") or "").lower()
        kind = str(document.get("content_kind") or document.get("document_type") or "").lower()
        score = 0.0
        if not task_text:
            return score

        for token in task_text.split():
            if len(token) < 4:
                continue
            if token in name:
                score += 3.0
            if token in kind:
                score += 1.5

        if any(word in task_text for word in ("review", "preview", "refactor", "design", "figma")):
            if kind in {"figma_import", "figma_design", "image", "document_asset"}:
                score += 5.0
        if any(word in task_text for word in ("implement", "execute", "repo", "code", "change", "plan")):
            if kind in {"figma_import", "figma_design", "image"}:
                score += 10.0
            if kind in {"text", "binary_asset"} or ext in {
                ".py",
                ".ts",
                ".tsx",
                ".js",
                ".jsx",
                ".go",
                ".rs",
                ".java",
                ".cs",
                ".sql",
            }:
                score += 3.0
            if "codebase" in name or kind == "codebase_file":
                score += 2.0
        if any(word in task_text for word in ("analyze", "context", "upload", "scope", "requirement", "plan")):
            if ext in {".md", ".txt", ".pdf", ".docx", ".json"} or kind in {"text", "document_asset"}:
                score += 3.0
        if kind == "figma_import":
            score += 1.0
        return score

    def _truncate(self, value: Any, limit: int) -> Any:
        if not isinstance(value, str):
            return value
        if len(value) <= limit:
            return value
        return value[:limit] + "…"

    def _task_context_limits(self, task: Optional[Dict[str, Any]]) -> Dict[str, int]:
        """Task-scoped context caps — smaller slices for implementation work."""
        if not task:
            return {
                "max_documents": app_config.context_pack_max_documents,
                "preview_chars": app_config.context_pack_preview_chars,
                "figma_chars": app_config.context_pack_figma_preview_chars,
            }
        task_type = str(task.get("task_type") or "").lower()
        name = str(task.get("task_name") or "").lower()
        if "implement section" in name or task_type == "implementation":
            return {
                "max_documents": app_config.context_pack_task_max_documents,
                "preview_chars": min(app_config.context_pack_preview_chars, 360),
                "figma_chars": min(app_config.context_pack_figma_section_chars, 6000),
            }
        if task_type in {"review", "planning", "analysis"}:
            return {
                "max_documents": min(app_config.context_pack_max_documents, 6),
                "preview_chars": app_config.context_pack_preview_chars,
                "figma_chars": app_config.context_pack_figma_preview_chars,
            }
        return {
            "max_documents": app_config.context_pack_task_max_documents,
            "preview_chars": app_config.context_pack_preview_chars,
            "figma_chars": app_config.context_pack_figma_preview_chars,
        }

    @staticmethod
    def compact_diff_context(diff_summary: Optional[Dict[str, Any]], *, max_files: int = 12) -> Dict[str, Any]:
        """Diff-only context for integrate/review tasks."""
        if not isinstance(diff_summary, dict):
            return {"changed_files": [], "summary": "No git diff available."}
        files = []
        for row in (diff_summary.get("files") or diff_summary.get("changed_files") or [])[:max_files]:
            if isinstance(row, dict):
                files.append(
                    {
                        "path": row.get("path") or row.get("file"),
                        "status": row.get("status"),
                        "additions": row.get("additions"),
                        "deletions": row.get("deletions"),
                    }
                )
            elif isinstance(row, str):
                files.append({"path": row})
        return {
            "summary": diff_summary.get("summary") or diff_summary.get("message"),
            "changed_file_count": diff_summary.get("changed_file_count") or len(files),
            "changed_files": files,
            "diff_only": True,
        }

    def compact_for_prompt(
        self,
        context_pack: Dict[str, Any],
        *,
        task: Optional[Dict[str, Any]] = None,
        max_documents: Optional[int] = None,
        preview_chars: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Token-efficient context slice for CLI prompts (full pack remains in DB)."""
        limits = self._task_context_limits(task)
        max_docs = max_documents or limits["max_documents"]
        preview_limit = preview_chars or limits["preview_chars"]
        figma_preview_limit = limits["figma_chars"]
        task_text = self._task_search_text(task)
        task_type = str(task.get("task_type") or "").lower() if task else ""
        task_name = str(task.get("task_name") or "").lower() if task else ""

        rag = context_pack.get("rag_ready_context") or {}
        source_docs = list(rag.get("documents") or [])

        pinned_kinds = {
            "figma_import",
            "figma_export_image",
            "figma_section_export",
            "figma_asset",
        }
        pinned_ids: set[int] = set()
        pinned_docs: List[Dict[str, Any]] = []
        for doc in source_docs:
            kind = str(doc.get("content_kind") or doc.get("document_type") or "").lower()
            if kind in pinned_kinds:
                pinned_docs.append(doc)
                doc_id = doc.get("document_id")
                if doc_id is not None:
                    pinned_ids.add(int(doc_id))
            if kind == "figma_import":
                for img_id in doc.get("figma_image_document_ids") or []:
                    pinned_ids.add(int(img_id))
                for img_id in doc.get("figma_section_export_document_ids") or []:
                    pinned_ids.add(int(img_id))
                for img_id in doc.get("figma_asset_document_ids") or []:
                    pinned_ids.add(int(img_id))

        for doc in source_docs:
            doc_id = doc.get("document_id")
            if doc_id is not None and int(doc_id) in pinned_ids:
                if doc not in pinned_docs:
                    pinned_docs.append(doc)

        remaining_docs = [
            doc for doc in source_docs if doc.get("document_id") not in pinned_ids
        ]
        if task_text and remaining_docs:
            ranked = sorted(
                remaining_docs,
                key=lambda doc: self._document_relevance_score(doc, task_text),
                reverse=True,
            )
            relevant = [doc for doc in ranked if self._document_relevance_score(doc, task_text) > 0]
            other_docs = (relevant or ranked)[:max_docs]
        else:
            other_docs = remaining_docs[:max_docs]

        documents = pinned_docs + other_docs

        compact_docs: List[Dict[str, Any]] = []
        has_figma = any(
            str(doc.get("content_kind") or doc.get("document_type") or "").lower() == "figma_import"
            for doc in pinned_docs
        )
        for doc in documents:
            kind = str(doc.get("content_kind") or doc.get("document_type") or "").lower()
            entry: Dict[str, Any] = {
                "document_id": doc.get("document_id"),
                "name": doc.get("name") or doc.get("document_name"),
                "content_kind": doc.get("content_kind") or doc.get("document_type"),
                "file_extension": doc.get("file_extension"),
                "agent_usage": doc.get("agent_usage"),
                "pinned": kind in pinned_kinds or (
                    doc.get("document_id") is not None and int(doc.get("document_id")) in pinned_ids
                ),
            }
            if kind == "figma_import":
                excerpt = self._figma_spec_excerpt(
                    {
                        "_structured": {
                            "agent_context": {
                                "text_preview": doc.get("text_preview") or doc.get("figma_spec_excerpt"),
                                "compact_spec": None,
                                "sections": doc.get("design_sections"),
                                "tokens": None,
                                "assets": None,
                                "extraction_version": "v2",
                            }
                        },
                        "content_kind": "figma_import",
                    },
                    task=task,
                ) or doc.get("figma_spec_excerpt") or doc.get("text_preview")
                limit = (
                    app_config.context_pack_figma_section_chars
                    if self._is_implementation_task(task)
                    else figma_preview_limit
                )
                if excerpt:
                    entry["text_preview"] = self._truncate(str(excerpt), limit)
                if doc.get("design_sections"):
                    entry["design_sections"] = doc.get("design_sections")
            else:
                preview = doc.get("text_preview")
                if preview:
                    entry["text_preview"] = self._truncate(str(preview), preview_limit)
            if doc.get("figma_image_document_ids"):
                entry["figma_image_document_ids"] = doc.get("figma_image_document_ids")
            compact_docs.append(entry)

        project = context_pack.get("project") or {}
        metadata = context_pack.get("project_metadata") or {}
        meta_blob = metadata.get("metadata") if isinstance(metadata.get("metadata"), dict) else {}
        runtime = metadata.get("runtime_preferences") if isinstance(metadata.get("runtime_preferences"), dict) else {}

        design_staging = context_pack.get("design_staging") or {}
        compact: Dict[str, Any] = {
            "project": {
                "project_id": project.get("project_id"),
                "project_name": project.get("project_name"),
            },
            "repo_path": runtime.get("repo_path"),
            "analysis_goal": meta_blob.get("analysis_goal") if isinstance(meta_blob, dict) else None,
            "context_documents": compact_docs,
            "document_count": len(source_docs),
            "included_document_count": len(compact_docs),
            "retrieval_guidance": (rag.get("retrieval_guidance") or [])[:3],
            "context_mode": "task_scoped" if task else "run_level",
        }
        if app_config.context_pack_use_architecture_cache:
            cache = meta_blob.get("architecture_cache") if isinstance(meta_blob, dict) else None
            cached = project_context_cache_service.compact_cached_summary(cache)
            if cached:
                compact["architecture_summary"] = cached
        if has_figma:
            compact["design_context_required"] = True
            compact["design_read_first"] = (
                "Read .midnight/design/DESIGN_MANIFEST.md and all staged PNG exports before any UI work."
            )
        if design_staging:
            compact["design_assets_staged"] = design_staging

        if task:
            compact["active_task"] = {
                "task_id": task.get("task_id"),
                "task_name": task.get("task_name"),
                "task_type": task.get("task_type"),
                "description": self._truncate(str(task.get("description") or ""), 800),
            }
            if "integrate" in task_name or "review" in task_name or task_type == "review":
                compact["context_hint"] = (
                    "Use diff-only updates and staged .midnight/context files; avoid reloading full project docs."
                )
        else:
            tasks = context_pack.get("tasks") or []
            compact["task_inventory"] = [
                {
                    "task_id": row.get("task_id"),
                    "task_name": row.get("task_name"),
                    "task_type": row.get("task_type"),
                    "status": row.get("status"),
                }
                for row in tasks[:8]
            ]

        raw = json.dumps(compact, default=str)
        if len(raw) > app_config.context_pack_max_json_chars:
            compact["context_documents"] = compact_docs[: max(1, max_docs // 2)]
            compact["truncated_for_budget"] = True

        if app_config.context_pack_include_change_history:
            changes = context_pack.get("recent_changes") or []
            compact["recent_changes"] = [
                {
                    "title": row.get("title"),
                    "summary": self._truncate(str(row.get("summary") or ""), 240),
                }
                for row in changes[:5]
            ]

        return compact

    @staticmethod
    def _file_slug(value: str) -> str:
        return re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-").lower() or "item"

    @staticmethod
    def _write_file(path: Path, content: str) -> int:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return len(content.encode("utf-8"))

    async def stage_context_files(
        self,
        context_pack: Dict[str, Any],
        *,
        worktree_path: str,
        tasks: List[Dict[str, Any]],
        goal: str,
        acceptance_criteria: List[str],
    ) -> Dict[str, Any]:
        """Write a token-efficient, file-based context bundle under .midnight/context/.

        Agents read these files with their normal file tools instead of receiving a
        large inline JSON context blob in every prompt.
        """
        base = Path(worktree_path) / ".midnight" / "context"
        docs_dir = base / "documents"
        tasks_dir = base / "tasks"

        manifest_files: List[Dict[str, Any]] = []

        project = context_pack.get("project") or {}
        metadata = context_pack.get("project_metadata") or {}
        runtime = (
            metadata.get("runtime_preferences")
            if isinstance(metadata.get("runtime_preferences"), dict)
            else {}
        )
        agent_team = runtime.get("agent_team") or []

        brief_lines = [
            f"# Project Brief: {project.get('project_name') or 'Project'}",
            "",
            "## Goal",
            goal or "(not set)",
            "",
        ]
        if acceptance_criteria:
            brief_lines.append("## Acceptance Criteria")
            for item in acceptance_criteria:
                brief_lines.append(f"- {item}")
            brief_lines.append("")
        if agent_team:
            brief_lines.append("## Agent Team")
            for member in agent_team:
                role = member.get("role")
                purpose = member.get("purpose")
                brief_lines.append(f"- **{role}**: {purpose}")
            brief_lines.append("")
        brief_text = "\n".join(brief_lines)
        size = self._write_file(base / "PROJECT_BRIEF.md", brief_text)
        manifest_files.append(
            {
                "path": ".midnight/context/PROJECT_BRIEF.md",
                "description": "Project goal, acceptance criteria, agent team",
                "bytes": size,
            }
        )

        rag = context_pack.get("rag_ready_context") or {}
        source_docs = list(rag.get("documents") or [])
        for doc in source_docs:
            doc_id = doc.get("document_id")
            name = str(doc.get("name") or doc.get("document_name") or f"document-{doc_id}")
            kind = str(doc.get("content_kind") or doc.get("document_type") or "").lower()
            if kind == "figma_import":
                text_content = (
                    self._figma_spec_excerpt(
                        {
                            "_structured": {
                                "agent_context": {
                                    "text_preview": doc.get("text_preview") or doc.get("figma_spec_excerpt"),
                                    "compact_spec": None,
                                    "sections": doc.get("design_sections"),
                                    "tokens": None,
                                    "assets": None,
                                    "extraction_version": "v2",
                                }
                            },
                            "content_kind": "figma_import",
                        }
                    )
                    or doc.get("figma_spec_excerpt")
                    or doc.get("text_preview")
                )
            else:
                text_content = doc.get("text_preview")
            if not text_content:
                continue
            filename = f"{doc_id}-{self._file_slug(name)}.md"
            doc_text = "\n".join([f"# {name}", "", f"_Type: {kind or 'unknown'}_", "", str(text_content)])
            size = self._write_file(docs_dir / filename, doc_text)
            manifest_files.append(
                {
                    "path": f".midnight/context/documents/{filename}",
                    "description": f"{kind or 'document'}: {name}",
                    "bytes": size,
                }
            )

        for task in tasks:
            task_id = task.get("task_id")
            if task_id is None:
                continue
            task_data = task.get("task_data") if isinstance(task.get("task_data"), dict) else {}
            spec = {
                "task_id": task_id,
                "task_name": task.get("task_name"),
                "task_type": task.get("task_type"),
                "description": task.get("description"),
                "status": task.get("status"),
                "priority": task.get("priority"),
                "agent_effort": task.get("agent_effort") or task_data.get("agent_effort"),
                "milestone_index": task_data.get("milestone_index"),
                "milestone_name": task_data.get("milestone_name"),
                "design_section_slug": task_data.get("design_section_slug"),
                "design_section_order": task_data.get("design_section_order"),
                "acceptance_criteria": acceptance_criteria,
            }
            filename = f"{task_id}.json"
            task_text = json.dumps(spec, indent=2, default=str)
            size = self._write_file(tasks_dir / filename, task_text)
            manifest_files.append(
                {
                    "path": f".midnight/context/tasks/{filename}",
                    "description": f"Full spec for task: {task.get('task_name')}",
                    "bytes": size,
                }
            )

        progress_path = base / "PROGRESS.md"
        if not progress_path.exists():
            self._write_file(progress_path, "# Progress\n\n_Not yet computed._\n")
        manifest_files.append(
            {
                "path": ".midnight/context/PROGRESS.md",
                "description": "Current milestone/task progress (rule-based, refreshed during execution)",
                "bytes": progress_path.stat().st_size,
            }
        )

        manifest = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "files": manifest_files,
        }
        self._write_file(base / "manifest.json", json.dumps(manifest, indent=2, default=str))
        return manifest

    def append_changelog(self, worktree_path: str, entry: str, max_entries: int = 10) -> None:
        """Append a one-line summary to .midnight/context/CHANGELOG.md, trimmed to recent entries."""
        path = Path(worktree_path) / ".midnight" / "context" / "CHANGELOG.md"
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        line = f"- [{timestamp}] {entry}"
        existing_lines: List[str] = []
        if path.exists():
            for raw in path.read_text(encoding="utf-8").splitlines():
                if raw.strip().startswith("- ["):
                    existing_lines.append(raw)
        existing_lines.append(line)
        existing_lines = existing_lines[-max_entries:]
        text = "# Changelog\n\n" + "\n".join(existing_lines) + "\n"
        self._write_file(path, text)

    def write_progress_markdown(self, worktree_path: str, markdown: str) -> None:
        self._write_file(Path(worktree_path) / ".midnight" / "context" / "PROGRESS.md", markdown)

    async def build_context_pack(
        self,
        db: DatabaseManager,
        project_id: int,
        include_change_history: bool = True,
        include_versions: bool = True,
        limit: int = 20,
    ) -> Dict[str, Any]:
        project = await db.get_project_by_id(project_id)
        if not project:
            return {}

        metadata = await project_metadata_service.get_project_metadata(db, project_id)
        documents = await db.get_documents_by_project(project_id)
        documents = [
            d for d in documents
            if d.get("is_active_version", True) is not False
            or str(d.get("document_type") or "") not in {
                "figma_import", "figma_export_image", "figma_section_export", "figma_asset"
            }
        ]
        tasks = await db.get_tasks_by_project(project_id, limit=limit)

        document_versions: Dict[str, Any] = {}
        if include_versions:
            for d in documents[:limit]:
                document_id = d.get("document_id")
                if document_id is None:
                    continue
                versions = await document_version_service.list_versions(
                    db,
                    project_id=project_id,
                    document_id=int(document_id),
                    limit=5,
                )
                document_versions[str(document_id)] = versions

        enriched_docs = []
        for d in documents[:limit]:
            copy = dict(d)
            is_figma = copy.get("document_type") == "figma_import" or copy.get("content_kind") == "figma_import"
            doc_id = copy.get("document_id")
            if is_figma and doc_id is not None:
                full = await db.fetch_one(
                    """
                    SELECT structured_json
                    FROM main.project_document
                    WHERE project_id = $1 AND document_id = $2
                    """,
                    project_id,
                    int(doc_id),
                )
                if full and full.get("structured_json"):
                    structured = full["structured_json"]
                    if isinstance(structured, str):
                        try:
                            structured = json.loads(structured)
                        except Exception:
                            structured = None
                    if isinstance(structured, dict):
                        copy["_structured"] = structured
            enriched_docs.append(copy)

        rag_documents = [
            self._rag_document_entry(d, document_versions.get(str(d.get("document_id")), []))
            for d in enriched_docs
        ]
        design_assets = [
            d
            for d in rag_documents
            if d.get("content_kind") in {"image", "figma_design", "figma_import", "document_asset"}
        ]

        history = []
        if include_change_history:
            history = await change_history_service.list_changes(
                db,
                project_id=project_id,
                limit=limit,
            )

        return {
            "project": project,
            "project_metadata": metadata,
            "documents": documents[:limit],
            "document_versions": document_versions,
            "rag_ready_context": {
                "documents": rag_documents,
                "design_assets": design_assets,
                "retrieval_guidance": [
                    "Prefer active/latest document versions for task prompts.",
                    "Use uploaded images and Figma/design files as visual reference inventory.",
                    "For figma_import v2, use section JSON/PNG under .midnight/design/sections/ and assets/.",
                    "Read tokens.css for colors, typography, and spacing variables.",
                    "Do not invent visual details that are not present in extracted text or inspected assets.",
                    "For binary assets, pass file metadata and request explicit inspection when an agent needs design fidelity.",
                ],
            },
            "tasks": tasks[:limit],
            "recent_changes": history[:limit],
        }


context_pack_service = ContextPackService()
