"""Reset a project execution state while preserving a git-tagged version snapshot."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..config import app_config
from ..database import DatabaseManager
from .change_history_service import change_history_service
from .git_worktree_service import git_worktree_service
from .preview_detection_service import preview_detection_service
from .project_metadata_service import project_metadata_service
from .run_service import run_service
from .schema_support import schema_support


class ProjectRefreshService:
    @staticmethod
    def _resolve_repo_path(project_metadata: Dict[str, Any], project_name: str) -> str:
        runtime_preferences = project_metadata.get("runtime_preferences") or {}
        if not isinstance(runtime_preferences, dict):
            runtime_preferences = {}
        return preview_detection_service.resolve_repo_path(
            runtime_preferences=runtime_preferences,
            project_name=project_name,
        )

    @staticmethod
    def _version_history(metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        meta = metadata.get("metadata") or {}
        if not isinstance(meta, dict):
            return []
        history = meta.get("project_version_history")
        return list(history) if isinstance(history, list) else []

    async def list_version_history(
        self,
        db: DatabaseManager,
        *,
        project_id: int,
    ) -> Dict[str, Any]:
        metadata = await project_metadata_service.get_project_metadata(db, project_id)
        history = self._version_history(metadata)
        changes = await change_history_service.list_changes(
            db,
            project_id=project_id,
            limit=50,
            entity_type="project",
        )
        refresh_events = [
            row
            for row in changes
            if str(row.get("change_type") or "").upper() == "PROJECT_REFRESHED"
        ]
        return {
            "ok": True,
            "project_id": project_id,
            "version_history": history,
            "refresh_events": refresh_events,
        }

    async def refresh_project(
        self,
        db: DatabaseManager,
        *,
        project_id: int,
        reason: str,
        created_by: str = "dashboard",
    ) -> Dict[str, Any]:
        project = await db.get_project_by_id(project_id)
        if not project:
            return {"ok": False, "error": "Project not found"}

        metadata = await project_metadata_service.get_project_metadata(db, project_id)
        project_name = str(project.get("project_name") or f"project-{project_id}")
        repo_path = self._resolve_repo_path(metadata, project_name)
        history = self._version_history(metadata)
        version = len(history) + 1
        reason_text = (reason or "Project refresh").strip()

        snapshot: Dict[str, Any] = {"ok": False, "skipped": True, "reason": "no repository path"}
        if repo_path:
            snapshot = await git_worktree_service.create_project_snapshot_tag(
                repo_path=repo_path,
                project_id=project_id,
                version=version,
                reason=reason_text,
                worktree_base_path=app_config.midnight_worktree_base_path or None,
            )

        runs = await run_service.list_runs(db, project_id=project_id, limit=500)
        run_ids = [int(row.get("agent_run_id") or 0) for row in runs if int(row.get("agent_run_id") or 0) > 0]
        cleaned_runs: List[Dict[str, Any]] = []
        for run_id in run_ids:
            cleaned_runs.append(
                await run_service.cleanup_run(
                    db,
                    project_id=project_id,
                    run_id=run_id,
                    delete_record=True,
                    created_by=created_by,
                )
            )

        git_cleanup: Dict[str, Any] = {"ok": True, "skipped": True}
        branch_cleanup: Dict[str, Any] = {"ok": True, "skipped": True}
        if repo_path:
            git_cleanup = await git_worktree_service.cleanup_project_worktrees(
                repo_path=repo_path,
                project_id=project_id,
                worktree_base_path=app_config.midnight_worktree_base_path or None,
            )
            branch_cleanup = await git_worktree_service.delete_run_branches(
                repo_path,
                run_ids,
            )

        tasks_reset = 0
        if await schema_support.table_exists(db, "task"):
            tasks_reset = int(
                await db.fetch_val(
                    """
                    WITH updated AS (
                        UPDATE main.task
                        SET status = 'QUEUED',
                            updated_at = NOW()
                        WHERE project_id = $1
                          AND COALESCE(status, '') NOT IN ('SUPERSEDED')
                        RETURNING task_id
                    )
                    SELECT COUNT(*) FROM updated
                    """,
                    project_id,
                )
                or 0
            )

        runtime_preferences = metadata.get("runtime_preferences") or {}
        if not isinstance(runtime_preferences, dict):
            runtime_preferences = {}
        runtime_preferences.pop("preview_session", None)
        runtime_preferences = preview_detection_service._clear_invalid_preview_prefs(runtime_preferences)

        meta = metadata.get("metadata") or {}
        if not isinstance(meta, dict):
            meta = {}
        entry = {
            "version": version,
            "git_tag": snapshot.get("tag"),
            "commit_hash": snapshot.get("commit_hash"),
            "worktree_path": snapshot.get("worktree_path"),
            "reason": reason_text,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": created_by,
            "runs_cleaned": len(run_ids),
            "tasks_reset": tasks_reset,
        }
        history.append(entry)
        meta["project_version_history"] = history
        meta["last_refresh_at"] = entry["created_at"]
        meta["last_refresh_reason"] = reason_text

        await project_metadata_service.update_project_metadata(
            db,
            project_id=project_id,
            metadata=meta,
            repository_url=metadata.get("repository_url"),
            default_branch=metadata.get("default_branch"),
            runtime_preferences=runtime_preferences,
            updated_by=created_by,
        )

        payload = {
            "version": version,
            "snapshot": snapshot,
            "runs_cleaned": len(run_ids),
            "tasks_reset": tasks_reset,
            "git_cleanup": git_cleanup,
            "branch_cleanup": branch_cleanup,
            "reason": reason_text,
        }
        await change_history_service.record_change(
            db,
            project_id=project_id,
            entity_type="project",
            entity_id=project_id,
            source="dashboard.refresh",
            change_type="PROJECT_REFRESHED",
            title=f"Project refreshed (v{version})",
            summary=reason_text,
            payload=payload,
            created_by=created_by,
        )

        return {
            "ok": True,
            "project_id": project_id,
            "version": version,
            "snapshot": snapshot,
            "runs_cleaned": len(run_ids),
            "tasks_reset": tasks_reset,
            "git_cleanup": git_cleanup,
            "branch_cleanup": branch_cleanup,
            "version_history_entry": entry,
        }


project_refresh_service = ProjectRefreshService()
