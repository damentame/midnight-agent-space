from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..database import DatabaseManager
from .jsonb_utils import decode_jsonb_fields, jsonb_dumps
from .schema_support import schema_support


class GitChangeService:
    _JSON_FIELDS = ("metadata",)

    async def list_git_changes(
        self,
        db: DatabaseManager,
        *,
        run_id: int,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        if not await schema_support.table_exists(db, "git_change"):
            return []
        rows = await db.fetch_many(
            """
            SELECT *
            FROM main.git_change
            WHERE agent_run_id = $1
            ORDER BY git_change_id DESC
            LIMIT $2
            """,
            run_id,
            limit,
        )
        return [decode_jsonb_fields(dict(row), self._JSON_FIELDS) for row in rows]

    async def record_git_change(
        self,
        db: DatabaseManager,
        *,
        project_id: int,
        run_id: int,
        repository_url: Optional[str],
        worktree_path: Optional[str],
        branch_name: Optional[str],
        base_branch: Optional[str],
        file_path: Optional[str],
        change_type: Optional[str],
        diff_excerpt: Optional[str],
        commit_hash: Optional[str],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not await schema_support.table_exists(db, "git_change"):
            return
        await db.execute(
            """
            INSERT INTO main.git_change (
                project_id,
                agent_run_id,
                repository_url,
                worktree_path,
                branch_name,
                base_branch,
                file_path,
                change_type,
                diff_excerpt,
                commit_hash,
                metadata
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """,
            project_id,
            run_id,
            repository_url,
            worktree_path,
            branch_name,
            base_branch,
            file_path,
            change_type,
            diff_excerpt,
            commit_hash,
            jsonb_dumps(metadata or {}),
        )

    async def record_diff_snapshot(
        self,
        db: DatabaseManager,
        *,
        project_id: int,
        run_id: int,
        repository_url: Optional[str],
        worktree_path: str,
        branch_name: Optional[str],
        base_branch: Optional[str],
        status_lines: List[str],
        diff_excerpt: str,
    ) -> Dict[str, Any]:
        inserted = 0
        preview = diff_excerpt[:4000] if diff_excerpt else None
        if not status_lines:
            await self.record_git_change(
                db,
                project_id=project_id,
                run_id=run_id,
                repository_url=repository_url,
                worktree_path=worktree_path,
                branch_name=branch_name,
                base_branch=base_branch,
                file_path=None,
                change_type="UNCHANGED",
                diff_excerpt=preview,
                commit_hash=None,
                metadata={"status_lines": []},
            )
            return {"inserted": 1}

        for line in status_lines:
            if not line.strip():
                continue
            code = line[:2].strip() or "M"
            file_path = line[3:].strip() if len(line) > 3 else None
            await self.record_git_change(
                db,
                project_id=project_id,
                run_id=run_id,
                repository_url=repository_url,
                worktree_path=worktree_path,
                branch_name=branch_name,
                base_branch=base_branch,
                file_path=file_path,
                change_type=code,
                diff_excerpt=preview,
                commit_hash=None,
                metadata={"status_line": line},
            )
            inserted += 1
        return {"inserted": inserted}


git_change_service = GitChangeService()
