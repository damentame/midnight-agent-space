from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from ..config import app_config
from ..database import DatabaseManager
from .artifact_service import artifact_service
from .change_history_service import change_history_service
from .agent_routing_service import (
    EXECUTABLE_CLI_PROVIDERS,
    build_task_agent_plan,
    resolve_reviewer_provider,
    should_run_post_execution_reviewer,
    uses_balanced_agent_routing,
)
from .claude_cli_runner import ClaudeCliRunPlan, claude_cli_runner
from .codex_cli_runner import CodexCliRunPlan, codex_cli_runner
from .cursor_agent_runner import CursorAgentRunPlan, cursor_agent_runner
from .context_pack_service import context_pack_service
from .design_context_service import design_context_service
from .design_fidelity_service import design_fidelity_service
from .git_change_service import git_change_service
from .git_worktree_service import git_worktree_service
from .jsonb_utils import decode_jsonb_fields, jsonb_dumps
from .prompt_template_service import prompt_template_service
from .progress_service import progress_service
from .project_metadata_service import project_metadata_service
from .agent_effort_service import enrich_task_with_agent_effort
from .model_routing_service import (
    MODEL_SELECTION_FIXED,
    MODEL_SELECTION_OPTIMIZED,
    build_task_model_plan,
    resolve_cli_model,
)
from .review_check_service import review_check_service
from .runtime_check_service import runtime_check_service
from .schema_support import schema_support
from .verification_service import verification_service

logger = logging.getLogger(__name__)

_CLI_SPAWN_LOCK: Optional[asyncio.Lock] = None
_PROJECT_RUN_LOCKS: Dict[int, asyncio.Lock] = {}
_COMPLETED_TASK_STATUSES = frozenset({"COMPLETED", "DONE", "PASSED"})


def _get_cli_spawn_lock() -> asyncio.Lock:
    global _CLI_SPAWN_LOCK
    if _CLI_SPAWN_LOCK is None:
        _CLI_SPAWN_LOCK = asyncio.Lock()
    return _CLI_SPAWN_LOCK


def _get_project_run_lock(project_id: int) -> asyncio.Lock:
    lock = _PROJECT_RUN_LOCKS.get(project_id)
    if lock is None:
        lock = asyncio.Lock()
        _PROJECT_RUN_LOCKS[project_id] = lock
    return lock

_FATAL_CLI_ERROR_MARKERS = (
    "requires --verbose",
    "cli binary not found",
    "cursor-agent binary not found",
    "failed to launch claude cli",
    "failed to launch codex",
    "failed to launch cursor-agent",
    "workspace trust required",
    "pass --trust",
)


class RunService:
    _RUN_JSON_FIELDS = ("request_payload", "context_pack", "result_payload")
    _EVENT_JSON_FIELDS = ("event_payload",)

    def __init__(self) -> None:
        self._active_tasks: Dict[int, asyncio.Task[None]] = {}

    def _prune_active_tasks(self) -> None:
        for run_id in [rid for rid, task in self._active_tasks.items() if task.done()]:
            self._active_tasks.pop(run_id, None)

    async def _release_stale_running_runs(self, db: DatabaseManager) -> List[int]:
        """Fail RUNNING rows that have no live asyncio executor (prevents false concurrency blocks)."""
        if not await schema_support.table_exists(db, "agent_run"):
            return []
        self._prune_active_tasks()
        rows = await db.fetch_many(
            """
            SELECT agent_run_id, project_id
            FROM main.agent_run
            WHERE UPPER(COALESCE(status, '')) = 'RUNNING'
            ORDER BY agent_run_id
            """
        )
        released: List[int] = []
        for row in rows:
            run_id = int(row.get("agent_run_id") or 0)
            project_id = int(row.get("project_id") or 0)
            if run_id <= 0:
                continue
            active = self._active_tasks.get(run_id)
            if active is not None and not active.done():
                continue
            error_detail = "Run marked stale (no active executor)"
            await self._update_run(
                db,
                run_id,
                status="FAILED",
                result_payload={"error": error_detail, "stale_executor": True},
                finished=True,
            )
            await self.create_event(
                db,
                run_id=run_id,
                project_id=project_id,
                event_type="RUN_FAILED",
                event_order=None,
                payload={"error": error_detail, "stale_executor": True},
            )
            released.append(run_id)
        return released

    async def _live_executor_count(self, db: DatabaseManager) -> int:
        await self._release_stale_running_runs(db)
        self._prune_active_tasks()
        return self._active_task_count(self._active_tasks)

    async def _live_project_run(
        self,
        db: DatabaseManager,
        project_id: int,
    ) -> Optional[Dict[str, Any]]:
        if not await schema_support.table_exists(db, "agent_run"):
            return None
        row = await db.fetch_one(
            """
            SELECT *
            FROM main.agent_run
            WHERE project_id = $1
              AND UPPER(COALESCE(status, '')) = 'RUNNING'
            ORDER BY agent_run_id DESC
            LIMIT 1
            """,
            project_id,
        )
        if not row:
            return None
        run_id = int(row.get("agent_run_id") or 0)
        if run_id <= 0:
            return None
        task = self._active_tasks.get(run_id)
        if task is not None and not task.done():
            return decode_jsonb_fields(dict(row), self._RUN_JSON_FIELDS)
        return None

    @staticmethod
    def _already_running_response(run_row: Dict[str, Any]) -> Dict[str, Any]:
        run_id = int(run_row.get("agent_run_id") or 0)
        return {
            "ok": True,
            "already_running": True,
            "errors": [],
            "warnings": [
                f"Project already has active run #{run_id}. "
                "Only one run per project is allowed — open that run to monitor progress."
            ],
            "run": run_row,
            "runtime": {},
            "command": [],
            "worktree_plan": (run_row.get("result_payload") or {}).get("worktree"),
            "dry_run": False,
            "message": f"Active run #{run_id} already in progress.",
        }

    @staticmethod
    def _active_task_count(tasks: Dict[int, asyncio.Task[None]]) -> int:
        return sum(1 for task in tasks.values() if not task.done())

    @staticmethod
    def _first_non_empty_string(*values: Any) -> Optional[str]:
        for value in values:
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _resolve_project_repo_path(self, project_metadata: Dict[str, Any]) -> Optional[str]:
        metadata = project_metadata.get("metadata") or {}
        runtime_preferences = project_metadata.get("runtime_preferences") or {}
        top_level = project_metadata or {}

        if not isinstance(metadata, dict):
            metadata = {}
        if not isinstance(runtime_preferences, dict):
            runtime_preferences = {}

        return self._first_non_empty_string(
            top_level.get("repo_path"),
            top_level.get("repository_path"),
            top_level.get("local_repo_path"),
            runtime_preferences.get("repo_path"),
            runtime_preferences.get("repository_path"),
            runtime_preferences.get("local_repo_path"),
            runtime_preferences.get("workspace_root"),
            metadata.get("repo_path"),
            metadata.get("repository_path"),
            metadata.get("local_repo_path"),
            metadata.get("workspace_root"),
        )

    @staticmethod
    def _discover_nested_git_repos(repo_path: str, *, max_depth: int = 4, limit: int = 10) -> List[str]:
        root = Path(repo_path).expanduser()
        found: List[str] = []

        def visit(path: Path, depth: int) -> None:
            if len(found) >= limit or depth > max_depth:
                return
            try:
                if (path / ".git").exists():
                    found.append(str(path.resolve()))
                    return
                children = [child for child in path.iterdir() if child.is_dir()]
            except (OSError, PermissionError):
                return
            for child in sorted(children, key=lambda item: item.name.lower()):
                if child.name in {".midnight", "node_modules", ".venv", "__pycache__"}:
                    continue
                visit(child, depth + 1)

        visit(root, 0)
        return found

    @staticmethod
    def _task_failure_detail(result: Dict[str, Any]) -> Optional[str]:
        if not result or result.get("ok"):
            return None
        parts: List[str] = []
        error = result.get("error")
        if isinstance(error, str) and error.strip():
            parts.append(error.strip())
        stderr_tail = result.get("stderr_tail")
        if isinstance(stderr_tail, list):
            for line in stderr_tail[-8:]:
                if isinstance(line, str) and line.strip():
                    parts.append(line.strip())
        if not parts:
            exit_code = result.get("exit_code")
            if exit_code is not None:
                parts.append(f"CLI exited with code {exit_code}")
        if not parts:
            return None
        return "\n".join(dict.fromkeys(parts))

    @classmethod
    def _fatal_cli_failure(cls, result: Dict[str, Any]) -> Optional[str]:
        detail = cls._task_failure_detail(result)
        if not detail:
            return None
        lowered = detail.lower()
        for marker in _FATAL_CLI_ERROR_MARKERS:
            if marker in lowered:
                return detail
        return None

    @staticmethod
    def _sanitize_cli_task_result(result: Dict[str, Any]) -> Dict[str, Any]:
        """Strip large streams and avoid embedding self-referential execution payloads."""
        if not isinstance(result, dict):
            return {"ok": False, "error": "invalid task result"}
        stdout_tail = result.get("stdout_tail")
        stderr_tail = result.get("stderr_tail")
        return {
            "ok": bool(result.get("ok")),
            "error": result.get("error"),
            "exit_code": result.get("exit_code"),
            "timed_out": bool(result.get("timed_out")),
            "elapsed_ms": result.get("elapsed_ms"),
            "command": result.get("command"),
            "event_count": result.get("event_count"),
            "fatal_cli": result.get("fatal_cli"),
            "stdout_tail": stdout_tail[-4:] if isinstance(stdout_tail, list) else [],
            "stderr_tail": stderr_tail[-4:] if isinstance(stderr_tail, list) else [],
        }

    @classmethod
    def _build_execution_result(
        cls,
        *,
        per_task_results: List[Dict[str, Any]],
        all_ok: bool,
        selection_mode: str,
    ) -> Dict[str, Any]:
        safe_tasks = [cls._sanitize_cli_task_result(item) for item in per_task_results]
        summary = cls._sanitize_cli_task_result(per_task_results[-1] if per_task_results else {"ok": False})
        return {
            **summary,
            "ok": all_ok,
            "per_task_results": safe_tasks,
            "model_selection_mode": selection_mode,
        }

    @staticmethod
    def _resolve_run_artifact_dir(repo_path: str, run_id: int) -> Path:
        repo_root = Path(repo_path).resolve()
        configured_base = (app_config.midnight_run_artifact_path or "").strip()
        if configured_base:
            base_path = Path(configured_base).expanduser()
            if not base_path.is_absolute():
                base_path = (repo_root / base_path).resolve()
        else:
            base_path = repo_root / ".midnight" / "runs"
        return base_path / str(run_id)

    async def list_runs(
        self,
        db: DatabaseManager,
        project_id: Optional[int] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        if not await schema_support.table_exists(db, "agent_run"):
            return []

        if project_id is None:
            rows = await db.fetch_many(
                """
                SELECT *
                FROM main.agent_run
                ORDER BY agent_run_id DESC
                LIMIT $1
                """,
                limit,
            )
        else:
            rows = await db.fetch_many(
                """
                SELECT *
                FROM main.agent_run
                WHERE project_id = $1
                ORDER BY agent_run_id DESC
                LIMIT $2
                """,
                project_id,
                limit,
            )
        return [decode_jsonb_fields(dict(r), self._RUN_JSON_FIELDS) for r in rows]

    async def get_run(self, db: DatabaseManager, run_id: int) -> Dict[str, Any]:
        if not await schema_support.table_exists(db, "agent_run"):
            return {}
        row = await db.fetch_one("SELECT * FROM main.agent_run WHERE agent_run_id = $1", run_id)
        return decode_jsonb_fields(dict(row), self._RUN_JSON_FIELDS) if row else {}

    _VERBOSE_EVENT_TYPES = frozenset(
        {
            "THINKING",
            "TOOL_CALL",
            "ASSISTANT",
            "SYSTEM",
            "USER",
            "RATE_LIMIT_EVENT",
        }
    )

    async def list_run_events(
        self,
        db: DatabaseManager,
        run_id: int,
        limit: int = 500,
        *,
        mode: str = "timeline",
    ) -> List[Dict[str, Any]]:
        if not await schema_support.table_exists(db, "agent_event"):
            return []

        normalized_mode = (mode or "timeline").strip().lower()
        if normalized_mode != "timeline":
            rows = await db.fetch_many(
                """
                SELECT *
                FROM main.agent_event
                WHERE agent_run_id = $1
                ORDER BY agent_event_id ASC
                LIMIT $2
                """,
                run_id,
                limit,
            )
            return [decode_jsonb_fields(dict(r), self._EVENT_JSON_FIELDS) for r in rows]

        lifecycle_rows = await db.fetch_many(
            """
            SELECT *
            FROM main.agent_event
            WHERE agent_run_id = $1
              AND NOT (UPPER(event_type) = ANY($2::text[]))
            ORDER BY agent_event_id ASC
            """,
            run_id,
            list(self._VERBOSE_EVENT_TYPES),
        )
        verbose_limit = max(50, limit - len(lifecycle_rows))
        verbose_rows: List[Dict[str, Any]] = []
        if verbose_limit > 0:
            verbose_rows = await db.fetch_many(
                """
                SELECT *
                FROM main.agent_event
                WHERE agent_run_id = $1
                  AND UPPER(event_type) = ANY($2::text[])
                ORDER BY agent_event_id DESC
                LIMIT $3
                """,
                run_id,
                list(self._VERBOSE_EVENT_TYPES),
                verbose_limit,
            )
            verbose_rows = list(reversed(verbose_rows))

        merged: Dict[int, Dict[str, Any]] = {}
        for row in [*lifecycle_rows, *verbose_rows]:
            event_id = int(row.get("agent_event_id") or 0)
            if event_id > 0:
                merged[event_id] = dict(row)
        ordered = [merged[key] for key in sorted(merged.keys())]
        return [decode_jsonb_fields(dict(r), self._EVENT_JSON_FIELDS) for r in ordered]

    async def list_run_artifacts(
        self,
        db: DatabaseManager,
        run_id: int,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        return await artifact_service.list_artifacts(db, run_id=run_id, limit=limit)

    async def list_run_git_changes(
        self,
        db: DatabaseManager,
        run_id: int,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        return await git_change_service.list_git_changes(db, run_id=run_id, limit=limit)

    async def create_event(
        self,
        db: DatabaseManager,
        *,
        run_id: int,
        project_id: Optional[int],
        event_type: str,
        event_order: Optional[int],
        payload: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not await schema_support.table_exists(db, "agent_event"):
            return {}
        row = await db.fetch_one(
            """
            INSERT INTO main.agent_event (
                agent_run_id,
                project_id,
                event_type,
                event_order,
                event_payload
            )
            VALUES ($1, $2, $3, $4, $5)
            RETURNING *
            """,
            run_id,
            project_id,
            event_type,
            event_order,
            jsonb_dumps(payload),
        )
        return decode_jsonb_fields(dict(row), self._EVENT_JSON_FIELDS) if row else {}

    async def _project_tasks(self, db: DatabaseManager, project_id: int) -> List[Dict[str, Any]]:
        if not await schema_support.table_exists(db, "task"):
            return []
        rows = await db.fetch_many(
            """
            SELECT task_id, task_name, task_type, description, status, priority,
                   task_data, parameters, created_at, updated_at
            FROM main.task
            WHERE project_id = $1
              AND COALESCE(status, '') NOT IN ('SUPERSEDED')
            ORDER BY COALESCE(priority, 999999), task_id
            """,
            project_id,
        )
        out = []
        for row in rows:
            task = dict(row)
            if isinstance(task.get("task_data"), str):
                try:
                    task["task_data"] = json.loads(task["task_data"])
                except json.JSONDecodeError:
                    task["task_data"] = {}
            if isinstance(task.get("parameters"), str):
                try:
                    task["parameters"] = json.loads(task["parameters"])
                except json.JSONDecodeError:
                    task["parameters"] = {}
            out.append(enrich_task_with_agent_effort(task))
        return out

    @staticmethod
    def _parse_task_data(task: Dict[str, Any]) -> Dict[str, Any]:
        task_data = task.get("task_data") or {}
        if isinstance(task_data, str):
            try:
                task_data = json.loads(task_data)
            except Exception:
                task_data = {}
        return task_data if isinstance(task_data, dict) else {}

    @staticmethod
    def _is_parallel_section_task(task: Dict[str, Any]) -> bool:
        td = RunService._parse_task_data(task)
        if td.get("parallel_group") == "sections" and td.get("parallel_safe"):
            return True
        name = str(task.get("task_name") or "")
        return bool(re.match(r"^Implement section \d+:", name))

    @staticmethod
    def _task_execution_mode(task: Dict[str, Any]) -> str:
        td = RunService._parse_task_data(task)
        mode = str(td.get("execution_mode") or "").lower()
        if mode in {"parallel", "sequential"}:
            return mode
        if RunService._is_parallel_section_task(task):
            return "parallel"
        return "sequential"

    @staticmethod
    def _task_is_completed(task: Dict[str, Any]) -> bool:
        return str(task.get("status") or "").upper() in _COMPLETED_TASK_STATUSES

    @staticmethod
    def _first_incomplete_task(tasks: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        for task in tasks:
            if not RunService._task_is_completed(task):
                return task
        return None

    @staticmethod
    def _partition_task_batches(tasks: List[Dict[str, Any]]) -> List[tuple[str, List[Dict[str, Any]]]]:
        batches: List[tuple[str, List[Dict[str, Any]]]] = []
        index = 0
        while index < len(tasks):
            task = tasks[index]
            if RunService._task_execution_mode(task) == "parallel":
                parallel: List[Dict[str, Any]] = []
                while index < len(tasks) and RunService._task_execution_mode(tasks[index]) == "parallel":
                    parallel.append(tasks[index])
                    index += 1
                batches.append(("parallel", parallel))
            else:
                batches.append(("sequential", [task]))
                index += 1
        return batches

    async def _execute_single_project_task(
        self,
        db: DatabaseManager,
        *,
        run_id: int,
        project_id: int,
        task: Dict[str, Any],
        index: int,
        total: int,
        base_prompt: str,
        command_plan: Any,
        worktree_path: Optional[str],
        plan_by_task_id: Dict[int, Dict[str, Any]],
        runtime_provider: str,
        selection_mode: str,
        request_payload: Dict[str, Any],
        execution_context_pack: Optional[Dict[str, Any]],
        output_schema_path: Optional[str],
        output_path_str: Optional[str],
        on_event: Any,
        commit_on_success: bool = True,
        cli_spawn_guard: bool = False,
        cli_spawn_delay_seconds: float = 0.0,
        context_staged: bool = False,
    ) -> Dict[str, Any]:
        task_id = int(task.get("task_id") or 0)
        prior_status = str(task.get("status") or "").upper()
        if prior_status in {"COMPLETED", "DONE", "PASSED"}:
            if task_id > 0:
                await self.create_event(
                    db,
                    run_id=run_id,
                    project_id=project_id,
                    event_type="TASK_COMPLETED",
                    event_order=None,
                    payload={
                        "task_id": task_id,
                        "task_name": task.get("task_name"),
                        "status": "COMPLETED",
                        "skipped": True,
                        "message": f"{task.get('task_name') or 'Task'} already completed — skipped",
                    },
                )
            return {"ok": True, "skipped": True, "task_id": task_id}

        plan_entry = plan_by_task_id.get(task_id) or {}
        task_provider = str(plan_entry.get("runtime_provider") or runtime_provider)
        task_model = str(
            plan_entry.get("model")
            or resolve_cli_model(
                runtime_provider=task_provider,
                selection_mode=selection_mode,
                fixed_model=request_payload.get("model"),
                task=task,
            )
        )
        if task_id > 0:
            await self._update_task_status(db, task_id=task_id, status="RUNNING")
            await self.create_event(
                db,
                run_id=run_id,
                project_id=project_id,
                event_type="TASK_STARTED",
                event_order=None,
                payload={
                    "task_id": task_id,
                    "task_name": task.get("task_name"),
                    "status": "RUNNING",
                    "runtime_provider": task_provider,
                    "model": task_model,
                    "message": f"Started {task.get('task_name') or 'task'}",
                },
            )
        task_prompt = self._task_focused_prompt(
            base_prompt,
            task,
            index=index,
            total=total,
            model=task_model,
            context_pack=execution_context_pack,
            context_staged=context_staged,
        )
        task_plan = await self._build_cli_plan(
            runtime_provider=task_provider,
            prompt=task_prompt,
            model=task_model,
            worktree_path=worktree_path,
            output_schema_path=output_schema_path if index == total - 1 else None,
            output_path=output_path_str if index == total - 1 else None,
        )
        await self.create_event(
            db,
            run_id=run_id,
            project_id=project_id,
            event_type="TASK_MODEL_SELECTED",
            event_order=None,
            payload={
                "task_id": task_id,
                "task_name": task.get("task_name"),
                "model": task_model,
                "runtime_provider": task_provider,
                "task_role": plan_entry.get("task_role"),
                "agent_effort": task.get("agent_effort"),
                "selection_mode": selection_mode,
            },
        )
        if cli_spawn_delay_seconds > 0:
            await asyncio.sleep(cli_spawn_delay_seconds)
        if cli_spawn_guard:
            async with _get_cli_spawn_lock():
                task_result = await self._execute_cli_plan(
                    runtime_provider=task_provider,
                    plan=task_plan,
                    event_callback=on_event,
                )
        else:
            task_result = await self._execute_cli_plan(
                runtime_provider=task_provider,
                plan=task_plan,
                event_callback=on_event,
            )
        task_result["runtime_provider"] = task_provider
        task_result["task_id"] = task_id
        failure_detail = self._task_failure_detail(task_result)
        if task_id > 0:
            task_status = "COMPLETED" if task_result.get("ok") else "FAILED"
            if task_status == "COMPLETED" and commit_on_success and worktree_path:
                commit_result = await git_worktree_service.commit_changes(
                    worktree_path=worktree_path,
                    message=f"MAS run {run_id} task {task_id}",
                )
                if commit_result.get("committed"):
                    await self.create_event(
                        db,
                        run_id=run_id,
                        project_id=project_id,
                        event_type="GIT_COMMIT",
                        event_order=None,
                        payload={
                            "task_id": task_id,
                            "commit_hash": commit_result.get("commit_hash"),
                            "message": f"MAS run {run_id} task {task_id}",
                        },
                    )
            await self._update_task_status(db, task_id=task_id, status=task_status)
            await self.create_event(
                db,
                run_id=run_id,
                project_id=project_id,
                event_type="TASK_COMPLETED" if task_status == "COMPLETED" else "TASK_FAILED",
                event_order=None,
                payload={
                    "task_id": task_id,
                    "task_name": task.get("task_name"),
                    "status": task_status,
                    "model": task_model,
                    "agent_effort": task.get("agent_effort"),
                    "error": failure_detail if task_status == "FAILED" else None,
                    "exit_code": task_result.get("exit_code"),
                    "message": failure_detail
                    if task_status == "FAILED"
                    else f"{task.get('task_name') or 'Task'} completed",
                },
            )
        return task_result

    @staticmethod
    def _task_focused_prompt(
        base_prompt: str,
        task: Dict[str, Any],
        *,
        index: int,
        total: int,
        model: str,
        context_pack: Optional[Dict[str, Any]] = None,
        context_staged: bool = False,
    ) -> str:
        effort = task.get("agent_effort") or {}
        level = effort.get("level") or "medium"
        score = effort.get("score") or "?"
        compact_context = ""
        if context_staged:
            task_id = task.get("task_id")
            compact_context = (
                "\nProject context is staged under `.midnight/context/` (read with your file tools):\n"
                "- `.midnight/context/manifest.json` — index of all staged context files\n"
                "- `.midnight/context/PROJECT_BRIEF.md` — goal + acceptance criteria\n"
                "- `.midnight/context/PROGRESS.md` — current milestone/task status\n"
                f"- `.midnight/context/tasks/{task_id}.json` — full spec for THIS task\n"
                "- `.midnight/context/documents/*.md` — open only files relevant to this task\n"
                "Do not ask for context inline; everything needed is staged on disk.\n"
            )
        elif context_pack:
            compact = context_pack_service.compact_for_prompt(context_pack, task=task)
            compact_context = f"\nTask-relevant context (compact):\n{json.dumps(compact, default=str)}\n"
        return (
            f"{base_prompt}\n"
            f"{compact_context}\n"
            f"--- Task {index + 1} of {total} ---\n"
            f"Name: {task.get('task_name') or 'Task'}\n"
            f"Type: {task.get('task_type') or 'task'}\n"
            f"Agent effort: {level} ({score}/5) — {effort.get('rationale') or 'estimated for this step'}\n"
            f"Assigned model: {model}\n"
            f"Description:\n{task.get('description') or '(none)'}\n\n"
            f"Focus on completing this task only. Prior work from earlier tasks in this run may already exist in the repo."
        )

    async def _build_cli_plan(
        self,
        *,
        runtime_provider: str,
        prompt: str,
        model: str,
        worktree_path: Optional[str],
        output_schema_path: Optional[str] = None,
        output_path: Optional[str] = None,
    ) -> CodexCliRunPlan | ClaudeCliRunPlan | CursorAgentRunPlan:
        if runtime_provider == "cursor-agent":
            return CursorAgentRunPlan(
                prompt=prompt,
                model=model,
                worktree_path=worktree_path,
                output_json=True,
            )
        if runtime_provider == "claude-cli":
            return ClaudeCliRunPlan(
                prompt=prompt,
                model=model,
                worktree_path=worktree_path,
                output_json=True,
                permission_mode=app_config.claude_permission_mode,
                allowed_tools=app_config.claude_allowed_tools,
            )
        return CodexCliRunPlan(
            prompt=prompt,
            model=model,
            worktree_path=worktree_path,
            output_json=True,
            output_schema_path=output_schema_path,
            output_path=output_path,
            approval_mode=app_config.codex_approval_mode,
            sandbox_mode=app_config.codex_sandbox_mode,
        )

    async def _build_cli_command(
        self,
        runtime_provider: str,
        plan: CodexCliRunPlan | ClaudeCliRunPlan | CursorAgentRunPlan,
    ) -> List[str]:
        if runtime_provider == "cursor-agent":
            capabilities = await cursor_agent_runner.detect_capabilities(app_config.cursor_agent_bin)
            return cursor_agent_runner.build_command(
                app_config.cursor_agent_bin,
                plan,
                capabilities,
                include_prompt=True,
            )
        if runtime_provider == "claude-cli":
            capabilities = await claude_cli_runner.detect_capabilities(app_config.claude_cli_bin)
            return claude_cli_runner.build_command(
                app_config.claude_cli_bin,
                plan,
                capabilities,
                include_prompt=False,
            )
        capabilities = await codex_cli_runner.detect_capabilities(app_config.codex_cli_bin)
        return codex_cli_runner.build_command(
            app_config.codex_cli_bin,
            plan,
            capabilities,
            include_prompt=False,
        )

    async def _run_post_execution_reviewer(
        self,
        *,
        db: DatabaseManager,
        run_id: int,
        project_id: int,
        reviewer_provider: str,
        selection_mode: str,
        fixed_model: Optional[str],
        context_pack: Dict[str, Any],
        worktree_path: Optional[str],
        diff_summary: Dict[str, Any],
        per_task_results: List[Dict[str, Any]],
        event_callback,
    ) -> Dict[str, Any]:
        try:
            template_text = prompt_template_service.load_prompt_template("reviewer_prompt")
        except FileNotFoundError:
            return {"ok": False, "error": "reviewer_prompt template not found"}

        review_model = resolve_cli_model(
            runtime_provider=reviewer_provider,
            selection_mode=selection_mode,
            fixed_model=fixed_model,
            task={"task_type": "review", "task_name": "Design and quality review"},
        )
        compact_context = context_pack_service.compact_for_prompt(context_pack)
        review_prompt = (
            f"{template_text}\n\n"
            "You are reviewing an implementation pass that should match uploaded design context.\n"
            "Compare the built UI/code against Figma imports, staged files in .midnight/design/exports/, SVG/image assets, and text specs in the context pack.\n"
            "Flag any visual, layout, typography, or component mismatches. Recommend needs_changes when design fidelity is missing.\n\n"
            f"Context pack (compact):\n{json.dumps(compact_context, default=str)}\n\n"
            f"Git diff summary:\n{json.dumps(diff_summary, default=str)}\n\n"
            f"Per-task execution summary:\n{json.dumps(per_task_results, default=str)[:12000]}\n"
        )
        plan = await self._build_cli_plan(
            runtime_provider=reviewer_provider,
            prompt=review_prompt,
            model=review_model,
            worktree_path=worktree_path,
        )
        await self.create_event(
            db,
            run_id=run_id,
            project_id=project_id,
            event_type="QUALITY_REVIEW_STARTED",
            event_order=None,
            payload={
                "runtime_provider": reviewer_provider,
                "model": review_model,
                "message": "Running post-execution design and quality review",
            },
        )
        result = await self._execute_cli_plan(
            runtime_provider=reviewer_provider,
            plan=plan,
            event_callback=event_callback,
        )
        await self.create_event(
            db,
            run_id=run_id,
            project_id=project_id,
            event_type="QUALITY_REVIEW_COMPLETED" if result.get("ok") else "QUALITY_REVIEW_FAILED",
            event_order=None,
            payload={
                "runtime_provider": reviewer_provider,
                "model": review_model,
                "ok": result.get("ok"),
                "error": result.get("error"),
                "exit_code": result.get("exit_code"),
            },
        )
        return result

    async def _execute_cli_plan(
        self,
        *,
        runtime_provider: str,
        plan: CodexCliRunPlan | ClaudeCliRunPlan | CursorAgentRunPlan,
        event_callback,
    ) -> Dict[str, Any]:
        if runtime_provider == "cursor-agent":
            return await cursor_agent_runner.execute_streaming(
                cli_binary=app_config.cursor_agent_bin,
                plan=plan,
                timeout_seconds=app_config.cursor_agent_timeout_seconds,
                event_callback=event_callback,
            )
        if runtime_provider == "claude-cli":
            return await claude_cli_runner.execute_streaming(
                cli_binary=app_config.claude_cli_bin,
                plan=plan,
                timeout_seconds=app_config.claude_cli_timeout_seconds,
                event_callback=event_callback,
            )
        return await codex_cli_runner.execute_streaming(
            cli_binary=app_config.codex_cli_bin,
            plan=plan,
            timeout_seconds=app_config.codex_cli_timeout_seconds,
            event_callback=event_callback,
        )

    async def _update_task_status(
        self,
        db: DatabaseManager,
        *,
        task_id: int,
        status: str,
    ) -> None:
        if not await schema_support.table_exists(db, "task"):
            return
        await db.execute(
            """
            UPDATE main.task
            SET status = $1,
                updated_at = NOW()
            WHERE task_id = $2
            """,
            status,
            task_id,
        )

    async def _update_run(
        self,
        db: DatabaseManager,
        run_id: int,
        *,
        status: Optional[str] = None,
        command_preview: Optional[str] = None,
        result_payload: Optional[Dict[str, Any]] = None,
        finished: bool = False,
        mark_started: bool = False,
    ) -> Dict[str, Any]:
        fields: List[str] = []
        values: List[Any] = []
        idx = 1
        if mark_started:
            fields.append("started_at = COALESCE(started_at, NOW())")
        if status is not None:
            fields.append(f"status = ${idx}")
            values.append(status)
            idx += 1
        if command_preview is not None:
            fields.append(f"command_preview = ${idx}")
            values.append(command_preview)
            idx += 1
        if result_payload is not None:
            fields.append(f"result_payload = ${idx}")
            values.append(jsonb_dumps(result_payload))
            idx += 1
        fields.append("updated_at = NOW()")
        if finished:
            fields.append("finished_at = NOW()")
        values.append(run_id)
        row = await db.fetch_one(
            f"""
            UPDATE main.agent_run
            SET {", ".join(fields)}
            WHERE agent_run_id = ${idx}
            RETURNING *
            """,
            *values,
        )
        return decode_jsonb_fields(dict(row), self._RUN_JSON_FIELDS) if row else {}

    async def _resolve_continuation_source_run_id(
        self,
        db: DatabaseManager,
        *,
        project_id: int,
        repo_path: str,
        explicit: Optional[int] = None,
    ) -> Optional[int]:
        if explicit and explicit > 0:
            return explicit
        runs = await self.list_runs(db, project_id=project_id, limit=30)
        for run in runs:
            rid = int(run.get("agent_run_id") or 0)
            if rid <= 0:
                continue
            wt_path = git_worktree_service.resolve_worktree_path(
                repo_path=repo_path,
                project_id=project_id,
                run_id=rid,
                worktree_base_path=app_config.midnight_worktree_base_path or None,
            )
            if Path(wt_path).exists():
                return rid
            result_payload = run.get("result_payload") or {}
            worktree_payload = result_payload.get("worktree") or {}
            stored_path = worktree_payload.get("worktree_path")
            if stored_path and Path(str(stored_path)).exists():
                return rid
        return None

    async def _prepare_quick_run(
        self,
        db: DatabaseManager,
        *,
        project_id: int,
        user_prompt: str,
        template_name: str,
        runtime_provider: str,
        model: Optional[str],
        model_selection_mode: str = MODEL_SELECTION_OPTIMIZED,
        include_change_history: bool,
        include_document_versions: bool,
        use_worktree: bool,
        dry_run: bool,
        created_by: str,
        output_schema_name: Optional[str] = None,
        reviewer_provider: Optional[str] = None,
        source_run_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        verification = verification_service.verify_quick_run_inputs(
            project_id=project_id,
            user_prompt=user_prompt,
            runtime_provider=runtime_provider,
            template_name=template_name,
        )
        if not verification.ok:
            return {"ok": False, "errors": verification.errors, "warnings": verification.warnings}

        runtime = runtime_check_service.runtime_check()
        project_metadata = await project_metadata_service.get_project_metadata(db, project_id)
        context_pack = await context_pack_service.build_context_pack(
            db,
            project_id=project_id,
            include_change_history=include_change_history,
            include_versions=include_document_versions,
        )
        if not context_pack:
            return {
                "ok": False,
                "errors": [f"project {project_id} not found"],
                "warnings": verification.warnings,
            }

        try:
            template_text = prompt_template_service.load_prompt_template(template_name)
        except FileNotFoundError:
            return {
                "ok": False,
                "errors": [f"prompt template '{template_name}' not found"],
                "warnings": verification.warnings,
            }

        selection_mode = (model_selection_mode or MODEL_SELECTION_OPTIMIZED).strip().lower()
        if selection_mode not in {MODEL_SELECTION_OPTIMIZED, MODEL_SELECTION_FIXED}:
            selection_mode = MODEL_SELECTION_OPTIMIZED

        project_tasks = await self._project_tasks(db, project_id)
        runtime_prefs = project_metadata.get("runtime_preferences") or {}
        if not isinstance(runtime_prefs, dict):
            runtime_prefs = {}
        exec_params_meta = runtime_prefs.get("execution_parameters") or {}
        if not isinstance(exec_params_meta, dict):
            exec_params_meta = {}
        execution_mode = str(exec_params_meta.get("execution_mode") or runtime_prefs.get("execution_mode") or "standard")
        milestones_meta = exec_params_meta.get("milestones") or []
        if not isinstance(milestones_meta, list):
            milestones_meta = []
        resolved_reviewer = resolve_reviewer_provider(
            primary_provider=runtime_provider,
            reviewer_provider=reviewer_provider or runtime_prefs.get("reviewer_provider"),
        )
        cursor_available = bool((runtime.get("cursor_agent") or {}).get("found"))
        balanced_routing = uses_balanced_agent_routing(selection_mode)
        task_agent_plan = build_task_agent_plan(
            primary_provider=runtime_provider,
            reviewer_provider=resolved_reviewer,
            model_selection_mode=selection_mode,
            fixed_model=model,
            tasks=project_tasks,
            cursor_available=cursor_available,
        )
        task_model_plan = [
            {
                "task_id": entry.get("task_id"),
                "task_name": entry.get("task_name"),
                "task_type": entry.get("task_type"),
                "agent_effort": entry.get("agent_effort"),
                "model": entry.get("model"),
                "runtime_provider": entry.get("runtime_provider"),
                "task_role": entry.get("task_role"),
                "selection_mode": selection_mode,
            }
            for entry in task_agent_plan
        ]
        if not task_model_plan:
            task_model_plan = build_task_model_plan(
                runtime_provider=runtime_provider,
                selection_mode=selection_mode,
                fixed_model=model,
                tasks=project_tasks,
            )
        if task_model_plan:
            selected_model = task_model_plan[0]["model"]
        else:
            selected_model = resolve_cli_model(
                runtime_provider=runtime_provider,
                selection_mode=selection_mode,
                fixed_model=model,
                task=None,
            )
        full_prompt = (
            f"{template_text}\n\n"
            f"Project ID: {project_id}\n"
            f"User Prompt:\n{user_prompt}\n\n"
            f"Context Pack (compact):\n{json.dumps(context_pack_service.compact_for_prompt(context_pack), default=str)}"
        )
        prompt_chars = len(full_prompt)
        warnings = list(verification.warnings)
        if prompt_chars > app_config.context_pack_max_json_chars:
            warnings.append(
                f"Prompt context is large (~{prompt_chars // 1000}k chars). "
                "Consider removing unused uploads or re-serializing with a smaller codebase index."
            )
        errors: List[str] = []
        if runtime_provider not in EXECUTABLE_CLI_PROVIDERS:
            warnings.append(f"runtime_provider '{runtime_provider}' is currently preview-only")
            if not dry_run:
                errors.append(f"runtime_provider '{runtime_provider}' is not executable yet")
        if runtime_provider == "codex-cli" and not runtime["codex_cli"]["found"]:
            warnings.append("codex cli binary not found on PATH; run can only be planned")
            if not dry_run:
                errors.append("codex cli binary not found on PATH")
        if runtime_provider == "claude-cli" and not runtime["claude_cli"]["found"]:
            warnings.append("claude cli binary not found on PATH; run can only be planned")
            if not dry_run:
                errors.append("claude cli binary not found on PATH")
        if runtime_provider == "cursor-agent" and not runtime["cursor_agent"]["found"]:
            warnings.append("cursor-agent binary not found on PATH; run can only be planned")
            if not dry_run:
                errors.append("cursor-agent binary not found on PATH")
        if balanced_routing and not cursor_available:
            warnings.append(
                "Balanced agent usage expects cursor-agent for code tasks, but it was not detected. "
                "Code tasks will fall back to the primary runtime."
            )
        if balanced_routing:
            needs_reviewer = resolved_reviewer == "claude-cli"
            reviewer_found = runtime["claude_cli"]["found"] if needs_reviewer else runtime["codex_cli"]["found"]
            if not reviewer_found and not dry_run:
                errors.append(
                    f"{resolved_reviewer} is required for review tasks in balanced mode but was not found on PATH"
                )

        repo_path = self._resolve_project_repo_path(project_metadata) or ""
        base_branch = project_metadata.get("default_branch") if project_metadata else None
        if not base_branch:
            base_branch = "main"

        if not repo_path:
            warning_text = (
                "project repository path is not configured in metadata/runtime_preferences; "
                "dry-run planning is available but execution is blocked"
            )
            warnings.append(warning_text)
            if not dry_run:
                errors.append(
                    "project repository path is required for execution "
                    "(set metadata.repo_path or runtime_preferences.repo_path)"
                )
        elif not dry_run:
            repo_valid = await git_worktree_service.validate_repository(repo_path)
            if not repo_valid.get("ok"):
                suggestions = self._discover_nested_git_repos(repo_path)
                suggestion_text = f"; found nested git repos: {', '.join(suggestions)}" if suggestions else ""
                errors.append(
                    "selected repository path is not a git repository: "
                    f"{repo_path} ({repo_valid.get('error') or repo_valid.get('stderr') or 'validation failed'})"
                    f"{suggestion_text}"
                )
            else:
                repo_path = str(repo_valid.get("repo_path") or repo_path)
        if not dry_run:
            live_executors = await self._live_executor_count(db)
            if live_executors >= app_config.midnight_max_concurrency:
                errors.append(
                    f"max concurrency reached ({live_executors}/{app_config.midnight_max_concurrency}); "
                    "wait for active runs to complete or cancel them from the Runs tab"
                )

        design_validation = await design_context_service.validate_design_context(db, project_id)
        if design_validation.get("required") and not design_validation.get("ok"):
            gap_text = "; ".join(design_validation.get("gaps") or [])
            design_msg = (
                gap_text
                or "Figma design context is incomplete. Re-import from Figma with a node-id URL."
            )
            if dry_run:
                warnings.append(design_msg)
            else:
                errors.append(design_msg)
        elif design_validation.get("required") and not design_validation.get("structural_ready"):
            gap_text = "; ".join(design_validation.get("gaps") or [])
            struct_msg = gap_text or "Design context not structurally ready (sections/assets missing)."
            if dry_run:
                warnings.append(struct_msg)
            else:
                errors.append(struct_msg)

        if await schema_support.table_exists(db, "agent_run"):
            row = await db.fetch_one(
                """
                INSERT INTO main.agent_run (
                    project_id,
                    run_kind,
                    runtime_provider,
                    status,
                    request_payload,
                    context_pack,
                    created_by,
                    started_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, NULL)
                RETURNING *
                """,
                project_id,
                "quick_run",
                runtime_provider,
                "PENDING",
                jsonb_dumps(
                    {
                        "template_name": template_name,
                        "user_prompt": user_prompt,
                        "model": model if selection_mode == MODEL_SELECTION_FIXED else None,
                        "model_selection_mode": selection_mode,
                        "task_model_plan": task_model_plan,
                        "task_agent_plan": task_agent_plan,
                        "reviewer_provider": resolved_reviewer,
                        "balanced_agent_routing": balanced_routing,
                        "dry_run": dry_run,
                        "include_change_history": include_change_history,
                        "include_document_versions": include_document_versions,
                        "use_worktree": use_worktree,
                        "output_schema_name": output_schema_name,
                        "source_run_id": source_run_id,
                        "execution_mode": execution_mode,
                        "milestones": milestones_meta,
                        "execution_parameters": exec_params_meta,
                        "repo_path": repo_path,
                    }
                ),
                jsonb_dumps(context_pack),
                created_by,
            )
            run_row = decode_jsonb_fields(dict(row), self._RUN_JSON_FIELDS) if row else {}
        else:
            run_row = {}

        run_id = int(run_row.get("agent_run_id") or 0)
        execution_path = repo_path or None
        worktree = {
            "branch_name": None,
            "worktree_path": execution_path,
            "base_branch": base_branch,
            "reuse_existing_branch": False,
            "seeded_from": None,
        }
        can_prepare_execution_paths = not errors
        if use_worktree and repo_path and run_id > 0 and can_prepare_execution_paths:
            resolved_worktree_path = git_worktree_service.resolve_worktree_path(
                repo_path=repo_path,
                project_id=project_id,
                run_id=run_id,
                worktree_base_path=app_config.midnight_worktree_base_path or None,
            )
            has_completed_tasks = any(
                str(task.get("status") or "").upper() in {"COMPLETED", "DONE", "PASSED"}
                for task in project_tasks
            )
            continuation_source = None
            if source_run_id or has_completed_tasks:
                continuation_source = await self._resolve_continuation_source_run_id(
                    db,
                    project_id=project_id,
                    repo_path=repo_path,
                    explicit=source_run_id,
                )
            if dry_run:
                if execution_mode == "milestones":
                    persistent_path = git_worktree_service.resolve_persistent_worktree_path(
                        repo_path=repo_path,
                        project_id=project_id,
                        branch_suffix="working",
                        worktree_base_path=app_config.midnight_worktree_base_path or None,
                    )
                    worktree = {
                        "branch_name": "mas/working",
                        "worktree_path": persistent_path,
                        "base_branch": base_branch,
                        "reuse_existing_branch": False,
                        "seeded_from": continuation_source,
                    }
                else:
                    worktree = {
                        "branch_name": git_worktree_service.resolve_run_branch_name(run_id),
                        "worktree_path": resolved_worktree_path,
                        "base_branch": base_branch,
                        "reuse_existing_branch": False,
                        "seeded_from": continuation_source,
                    }
            else:
                try:
                    if execution_mode == "milestones":
                        plan = await git_worktree_service.ensure_persistent_worktree(
                            repo_path,
                            project_id,
                            "mas/working",
                            base_branch=base_branch,
                            worktree_base_path=app_config.midnight_worktree_base_path or None,
                        )
                        try:
                            await git_worktree_service.ensure_persistent_worktree(
                                repo_path,
                                project_id,
                                "mas/preview",
                                base_branch=base_branch,
                                worktree_base_path=app_config.midnight_worktree_base_path or None,
                            )
                        except Exception as exc:
                            warnings.append(f"mas/preview worktree setup failed: {exc}")
                    elif continuation_source:
                        plan = await git_worktree_service.create_continuation_worktree(
                            repo_path=repo_path,
                            project_id=project_id,
                            run_id=run_id,
                            source_run_id=continuation_source,
                            base_branch=base_branch,
                            worktree_base_path=app_config.midnight_worktree_base_path or None,
                        )
                    else:
                        plan = await git_worktree_service.create_worktree(
                            repo_path=repo_path,
                            project_id=project_id,
                            run_id=run_id,
                            base_branch=base_branch,
                            worktree_base_path=app_config.midnight_worktree_base_path or None,
                        )
                    worktree = {
                        "branch_name": plan.branch_name,
                        "worktree_path": plan.worktree_path,
                        "base_branch": base_branch,
                        "reuse_existing_branch": plan.reuse_existing_branch,
                        "seeded_from": continuation_source,
                    }
                except Exception as exc:
                    errors.append(f"worktree creation failed: {exc}")
                    worktree = {
                        "branch_name": None,
                        "worktree_path": execution_path,
                        "base_branch": base_branch,
                        "reuse_existing_branch": False,
                        "seeded_from": continuation_source,
                    }
        elif use_worktree and not repo_path:
            warnings.append("worktree planning skipped because project repository path is not configured")

        design_staging: Dict[str, Any] = {}
        wt_path = worktree.get("worktree_path")
        if not dry_run and wt_path and can_prepare_execution_paths and design_validation.get("required"):
            try:
                design_staging = await design_context_service.stage_design_context(
                    db,
                    project_id=project_id,
                    worktree_path=str(wt_path),
                )
                if not design_staging.get("ok"):
                    errors.append(
                        "Failed to stage Figma design assets into worktree (.midnight/design/). "
                        "Re-import Figma before executing."
                    )
                else:
                    context_pack["design_staging"] = design_staging
            except Exception as exc:
                errors.append(f"design context staging failed: {exc}")

        run_dir: Optional[Path] = None
        output_path: Optional[Path] = None
        output_schema_path: Optional[Path] = None
        if run_id > 0 and repo_path and can_prepare_execution_paths:
            run_dir = self._resolve_run_artifact_dir(repo_path, run_id)
            run_dir.mkdir(parents=True, exist_ok=True)
            if runtime_provider == "claude-cli":
                output_name = "claude-output.json"
            elif runtime_provider == "cursor-agent":
                output_name = "cursor-agent-output.json"
            else:
                output_name = "codex-output.json"
            output_path = run_dir / output_name
            if output_schema_name:
                try:
                    schema = prompt_template_service.load_json_schema(output_schema_name)
                    output_schema_path = run_dir / f"{output_schema_name}.schema.json"
                    output_schema_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
                except FileNotFoundError:
                    warnings.append(f"json schema '{output_schema_name}' not found")

        plan = await self._build_cli_plan(
            runtime_provider=runtime_provider,
            prompt=full_prompt,
            model=selected_model,
            worktree_path=worktree.get("worktree_path"),
            output_schema_path=str(output_schema_path) if output_schema_path else None,
            output_path=str(output_path) if output_path else None,
        )
        if selection_mode == MODEL_SELECTION_OPTIMIZED and len(task_model_plan) > 1:
            command = [
                runtime_provider,
                "exec",
                f"--optimized ({len(task_model_plan)} tasks, per-task models)",
            ]
        elif runtime_provider in EXECUTABLE_CLI_PROVIDERS:
            command = await self._build_cli_command(runtime_provider, plan)
        else:
            command = []

        if runtime_provider not in EXECUTABLE_CLI_PROVIDERS:
            command = [
                "provider-adapter",
                "--provider",
                runtime_provider,
                "--model",
                selected_model,
                "--project-id",
                str(project_id),
            ]
        cmd_verification = verification_service.verify_command_preview(command)
        warnings.extend(cmd_verification.warnings)
        errors.extend(cmd_verification.errors)

        if runtime_provider == "codex-cli":
            preflight = await verification_service.run_command(
                [app_config.codex_cli_bin, "--version"],
                timeout_seconds=10,
            )
            if not preflight.ok:
                warnings.append("codex --version preflight failed")
        elif runtime_provider == "claude-cli":
            preflight = await verification_service.run_command(
                [app_config.claude_cli_bin, "-v"],
                timeout_seconds=10,
            )
            if not preflight.ok:
                warnings.append("claude -v preflight failed")
        else:
            preflight = await verification_service.run_command(["git", "--version"], timeout_seconds=10)

        if run_id > 0:
            await self.create_event(
                db,
                run_id=run_id,
                project_id=project_id,
                event_type="RUN_PLANNED",
                event_order=1,
                payload={
                    "runtime_provider": runtime_provider,
                    "template_name": template_name,
                    "model_selection_mode": selection_mode,
                    "task_model_plan": task_model_plan,
                    "dry_run": dry_run,
                    "worktree_path": worktree.get("worktree_path"),
                },
            )

        return {
            "ok": not errors,
            "errors": errors,
            "warnings": warnings,
            "run": run_row,
            "runtime": runtime,
            "command": command,
            "command_plan": plan,
            "worktree": worktree,
            "dry_run": dry_run,
            "run_dir": str(run_dir) if run_dir else None,
            "output_path": str(output_path) if output_path else None,
            "project_metadata": project_metadata,
            "preflight": {
                "ok": preflight.ok,
                "exit_code": preflight.exit_code,
                "stderr": preflight.stderr.strip(),
            },
            "task_model_plan": task_model_plan,
            "task_agent_plan": task_agent_plan,
            "reviewer_provider": resolved_reviewer,
            "balanced_agent_routing": balanced_routing,
            "model_selection_mode": selection_mode,
        }

    async def create_quick_run_plan(
        self,
        db: DatabaseManager,
        *,
        project_id: int,
        user_prompt: str,
        template_name: str,
        runtime_provider: str = app_config.midnight_default_runtime,
        model: Optional[str] = None,
        model_selection_mode: str = MODEL_SELECTION_OPTIMIZED,
        include_change_history: bool = True,
        include_document_versions: bool = True,
        use_worktree: bool = True,
        dry_run: bool = True,
        created_by: str = "dashboard",
        output_schema_name: Optional[str] = None,
        reviewer_provider: Optional[str] = None,
        source_run_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        if not dry_run:
            async with _get_project_run_lock(project_id):
                await self._release_stale_running_runs(db)
                existing = await self._live_project_run(db, project_id)
                if existing:
                    return self._already_running_response(existing)
                return await self._create_quick_run_plan_unlocked(
                    db,
                    project_id=project_id,
                    user_prompt=user_prompt,
                    template_name=template_name,
                    runtime_provider=runtime_provider,
                    model=model,
                    model_selection_mode=model_selection_mode,
                    include_change_history=include_change_history,
                    include_document_versions=include_document_versions,
                    use_worktree=use_worktree,
                    dry_run=dry_run,
                    created_by=created_by,
                    output_schema_name=output_schema_name,
                    reviewer_provider=reviewer_provider,
                    source_run_id=source_run_id,
                )
        return await self._create_quick_run_plan_unlocked(
            db,
            project_id=project_id,
            user_prompt=user_prompt,
            template_name=template_name,
            runtime_provider=runtime_provider,
            model=model,
            model_selection_mode=model_selection_mode,
            include_change_history=include_change_history,
            include_document_versions=include_document_versions,
            use_worktree=use_worktree,
            dry_run=dry_run,
            created_by=created_by,
            output_schema_name=output_schema_name,
            reviewer_provider=reviewer_provider,
            source_run_id=source_run_id,
        )

    async def _create_quick_run_plan_unlocked(
        self,
        db: DatabaseManager,
        *,
        project_id: int,
        user_prompt: str,
        template_name: str,
        runtime_provider: str = app_config.midnight_default_runtime,
        model: Optional[str] = None,
        model_selection_mode: str = MODEL_SELECTION_OPTIMIZED,
        include_change_history: bool = True,
        include_document_versions: bool = True,
        use_worktree: bool = True,
        dry_run: bool = True,
        created_by: str = "dashboard",
        output_schema_name: Optional[str] = None,
        reviewer_provider: Optional[str] = None,
        source_run_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        prepared = await self._prepare_quick_run(
            db,
            project_id=project_id,
            user_prompt=user_prompt,
            template_name=template_name,
            runtime_provider=runtime_provider,
            model=model,
            model_selection_mode=model_selection_mode,
            include_change_history=include_change_history,
            include_document_versions=include_document_versions,
            use_worktree=use_worktree,
            dry_run=dry_run,
            created_by=created_by,
            output_schema_name=output_schema_name,
            reviewer_provider=reviewer_provider,
            source_run_id=source_run_id,
        )
        run_row = prepared.get("run") or {}
        run_id = int(run_row.get("agent_run_id") or 0)
        command = prepared.get("command") or []
        run_status = "PLANNED"
        if not prepared.get("ok"):
            run_status = "BLOCKED"
        if not dry_run and prepared.get("ok") and run_id > 0:
            run_status = "RUNNING"

        if run_id > 0:
            updated = await self._update_run(
                db,
                run_id,
                status=run_status,
                mark_started=run_status == "RUNNING",
                command_preview=" ".join(command),
                result_payload={
                    "warnings": prepared.get("warnings", []),
                    "errors": prepared.get("errors", []),
                    "dry_run": dry_run,
                    "worktree": prepared.get("worktree"),
                    "preflight": prepared.get("preflight"),
                    "task_model_plan": prepared.get("task_model_plan") or (prepared.get("run") or {}).get("request_payload", {}).get("task_model_plan"),
                },
            )
            prepared["run"] = updated or run_row

        prepared["task_model_plan"] = (prepared.get("run") or {}).get("request_payload", {}).get("task_model_plan") or prepared.get("task_model_plan")

        if run_id > 0 and run_status == "RUNNING":
            await self.create_event(
                db,
                run_id=run_id,
                project_id=project_id,
                event_type="RUN_STARTED",
                event_order=2,
                payload={"command": command},
            )
            task = asyncio.create_task(
                self._execute_run(
                    db=db,
                    run_id=run_id,
                    project_id=project_id,
                    command_plan=prepared["command_plan"],
                    command=command,
                    runtime_provider=runtime_provider,
                    worktree=prepared.get("worktree") or {},
                    run_dir=prepared.get("run_dir"),
                    output_path=prepared.get("output_path"),
                    repository_url=(prepared.get("project_metadata") or {}).get("repository_url"),
                    created_by=created_by,
                )
            )
            self._active_tasks[run_id] = task

        await change_history_service.record_change(
            db,
            project_id=project_id,
            entity_type="agent_run",
            entity_id=run_id if run_id > 0 else None,
            source="agentic.quick_run",
            change_type="QUICK_RUN_CREATED",
            title="Quick run created",
            summary=f"Quick run is {run_status.lower()}",
            payload={"status": run_status, "dry_run": dry_run},
            created_by=created_by,
        )

        # Keep compatibility with previous response shape.
        prepared["worktree_plan"] = prepared.get("worktree")
        prepared.pop("command_plan", None)
        prepared.pop("run_dir", None)
        prepared.pop("project_metadata", None)
        return prepared

    async def _milestone_boundary(
        self,
        db: DatabaseManager,
        *,
        run_id: int,
        project_id: int,
        repo_path: str,
        worktree_path: str,
        milestone_index: int,
        milestone_name: str,
        percent_target: int,
        completed_task_count: int,
        total_task_count: int,
    ) -> None:
        """Tag/promote the working branch and refresh staged progress at a milestone boundary."""
        await self.create_event(
            db,
            run_id=run_id,
            project_id=project_id,
            event_type="MILESTONE_COMPLETED",
            event_order=None,
            payload={
                "milestone_index": milestone_index,
                "milestone_name": milestone_name,
                "percent_complete": percent_target,
                "completed_tasks": completed_task_count,
                "total_tasks": total_task_count,
                "message": f"Milestone completed: {milestone_name} ({percent_target}%)",
            },
        )
        if repo_path:
            try:
                await git_worktree_service.tag_milestone(
                    repo_path,
                    project_id=project_id,
                    run_id=run_id,
                    milestone_index=milestone_index,
                    milestone_name=milestone_name,
                    branch="mas/working",
                )
                await git_worktree_service.promote_branch(
                    repo_path,
                    from_branch="mas/working",
                    to_branch="mas/preview",
                    worktree_base_path=app_config.midnight_worktree_base_path or None,
                )
            except Exception:
                logger.exception(
                    "milestone tag/promote failed for run_id=%s milestone=%s", run_id, milestone_index
                )

        progress = await progress_service.compute_progress(db, project_id)
        if worktree_path:
            try:
                context_pack_service.write_progress_markdown(
                    worktree_path, progress_service.render_markdown(progress)
                )
                context_pack_service.append_changelog(
                    worktree_path,
                    f"Milestone completed: {milestone_name} ({percent_target}% target) — "
                    f"{progress.get('completed_task_count', 0)}/{progress.get('total_tasks', 0)} tasks done.",
                )
            except Exception:
                logger.exception("failed to refresh staged progress for run_id=%s", run_id)

        await self.create_event(
            db,
            run_id=run_id,
            project_id=project_id,
            event_type="PROGRESS_UPDATE",
            event_order=None,
            payload=progress,
        )

    async def _execute_run(
        self,
        *,
        db: DatabaseManager,
        run_id: int,
        project_id: int,
        command_plan: CodexCliRunPlan | ClaudeCliRunPlan,
        command: List[str],
        runtime_provider: str,
        worktree: Dict[str, Any],
        run_dir: Optional[str],
        output_path: Optional[str],
        repository_url: Optional[str],
        created_by: str,
    ) -> None:
        if runtime_provider not in EXECUTABLE_CLI_PROVIDERS:
            await self._update_run(
                db,
                run_id,
                status="BLOCKED",
                result_payload={"error": f"runtime_provider '{runtime_provider}' is not executable yet"},
                finished=True,
            )
            return

        log_dir = Path(run_dir) if run_dir else None
        stdout_log = (log_dir / "stdout.log") if log_dir else None
        stderr_log = (log_dir / "stderr.log") if log_dir else None
        if log_dir:
            log_dir.mkdir(parents=True, exist_ok=True)
            if stdout_log:
                stdout_log.write_text("", encoding="utf-8")
            if stderr_log:
                stderr_log.write_text("", encoding="utf-8")

        project_tasks = await self._project_tasks(db, project_id)
        run_row = await self.get_run(db, run_id)
        execution_context_pack = run_row.get("context_pack") if isinstance(run_row, dict) else {}
        if not isinstance(execution_context_pack, dict):
            execution_context_pack = {}
        request_payload = run_row.get("request_payload") if isinstance(run_row, dict) else {}
        if not isinstance(request_payload, dict):
            request_payload = {}
        selection_mode = str(request_payload.get("model_selection_mode") or MODEL_SELECTION_OPTIMIZED)
        execution_mode = str(request_payload.get("execution_mode") or "standard")
        milestones_meta = request_payload.get("milestones") or []
        if not isinstance(milestones_meta, list):
            milestones_meta = []
        repo_path = str(request_payload.get("repo_path") or "")
        milestone_groups: Dict[int, List[int]] = {}
        milestone_names: Dict[int, str] = {}
        milestone_percent_targets: Dict[int, int] = {}
        for entry in milestones_meta:
            if not isinstance(entry, dict) or entry.get("index") is None:
                continue
            idx = int(entry["index"])
            milestone_percent_targets[idx] = int(entry.get("percent_target") or 0)
        for task in project_tasks:
            task_data = task.get("task_data") if isinstance(task.get("task_data"), dict) else {}
            m_index = task_data.get("milestone_index")
            if m_index is None:
                continue
            m_index = int(m_index)
            task_id = int(task.get("task_id") or 0)
            if task_id <= 0:
                continue
            milestone_groups.setdefault(m_index, []).append(task_id)
            milestone_names.setdefault(m_index, str(task_data.get("milestone_name") or f"Milestone {m_index}"))

        context_staged = False
        worktree_path_for_staging = worktree.get("worktree_path")
        if worktree_path_for_staging and project_tasks:
            try:
                first_params = project_tasks[0].get("parameters") or {}
                if not isinstance(first_params, dict):
                    first_params = {}
                goal = str(first_params.get("goal") or "")
                acceptance_criteria = first_params.get("acceptance_criteria") or []
                if not isinstance(acceptance_criteria, list):
                    acceptance_criteria = []
                await context_pack_service.stage_context_files(
                    execution_context_pack,
                    worktree_path=str(worktree_path_for_staging),
                    tasks=project_tasks,
                    goal=goal,
                    acceptance_criteria=[str(item) for item in acceptance_criteria],
                )
                context_staged = True
            except Exception:
                logger.exception("failed to stage .midnight/context for run_id=%s", run_id)

        active_task_id: Optional[int] = None
        if project_tasks:
            for index, task in enumerate(project_tasks):
                task_id = int(task.get("task_id") or 0)
                if task_id <= 0:
                    continue
                prior_status = str(task.get("status") or "").upper()
                if prior_status in _COMPLETED_TASK_STATUSES:
                    await self.create_event(
                        db,
                        run_id=run_id,
                        project_id=project_id,
                        event_type="TASK_COMPLETED",
                        event_order=None,
                        payload={
                            "task_id": task_id,
                            "task_name": task.get("task_name"),
                            "status": "COMPLETED",
                            "skipped": True,
                            "message": f"{task.get('task_name') or 'Task'} already completed — skipped",
                        },
                    )
                    continue
                if selection_mode == MODEL_SELECTION_OPTIMIZED:
                    next_status = "QUEUED"
                    event_type = "TASK_QUEUED"
                    message = f"Queued {task.get('task_name') or 'task'}"
                else:
                    next_status = "RUNNING" if index == 0 else "QUEUED"
                    event_type = "TASK_STARTED" if index == 0 else "TASK_QUEUED"
                    message = (
                        f"Started {task.get('task_name') or 'task'}"
                        if index == 0
                        else f"Queued {task.get('task_name') or 'task'}"
                    )
                    if index == 0:
                        active_task_id = task_id
                await self._update_task_status(db, task_id=task_id, status=next_status)
                await self.create_event(
                    db,
                    run_id=run_id,
                    project_id=project_id,
                    event_type=event_type,
                    event_order=None,
                    payload={
                        "task_id": task_id,
                        "task_name": task.get("task_name"),
                        "status": next_status,
                        "agent": runtime_provider,
                        "message": message,
                    },
                )

        async def on_event(event: Dict[str, Any]) -> None:
            event_type = str(event.get("event_type") or "event")
            payload = dict(event)
            message = str(payload.get("message") or "")
            if event_type == "stderr" and stderr_log and message:
                with stderr_log.open("a", encoding="utf-8") as handle:
                    handle.write(message + "\n")
            if event_type != "stderr" and stdout_log and message:
                with stdout_log.open("a", encoding="utf-8") as handle:
                    handle.write(message + "\n")
            await self.create_event(
                db,
                run_id=run_id,
                project_id=project_id,
                event_type=event_type.upper(),
                event_order=payload.get("event_order"),
                payload=payload,
            )

        execution_result: Dict[str, Any] = {}
        per_task_results: List[Dict[str, Any]] = []
        all_ok = True
        completed_task_ids: set[int] = set()
        diff_summary: Dict[str, Any] = {"inserted": 0}
        artifact_count = 0
        task_model_plan = request_payload.get("task_model_plan") or []
        task_agent_plan = request_payload.get("task_agent_plan") or task_model_plan
        reviewer_provider = resolve_reviewer_provider(
            primary_provider=runtime_provider,
            reviewer_provider=request_payload.get("reviewer_provider"),
        )
        balanced_routing = bool(request_payload.get("balanced_agent_routing")) or uses_balanced_agent_routing(
            selection_mode
        )
        plan_by_task_id = {
            int(entry["task_id"]): entry
            for entry in task_agent_plan
            if entry.get("task_id") is not None
        }
        output_schema_path = None
        output_path_str = str(output_path) if output_path else None
        if log_dir and output_path_str:
            schema_candidate = Path(output_path_str).parent / "review.schema.json"
            if schema_candidate.exists():
                output_schema_path = str(schema_candidate)

        try:
            use_per_task = (
                selection_mode == MODEL_SELECTION_OPTIMIZED
                and len(project_tasks) > 0
                and runtime_provider in EXECUTABLE_CLI_PROVIDERS
            )
            if use_per_task:
                all_ok = True
                fatal_cli_result: Optional[Dict[str, Any]] = None
                base_prompt = command_plan.prompt
                worktree_path = worktree.get("worktree_path")
                total = len(project_tasks)
                exec_params = request_payload.get("execution_parameters") or {}
                if not isinstance(exec_params, dict):
                    exec_params = {}
                section_parallel = int(
                    exec_params.get("section_task_parallelism")
                    or exec_params.get("max_concurrency")
                    or app_config.section_task_max_parallel
                )
                section_parallel = max(1, min(section_parallel, app_config.section_task_max_parallel))
                task_index = 0
                stop_run = False
                skip_reason = "Prior task failed"

                for batch_mode, batch_tasks in self._partition_task_batches(project_tasks):
                    if stop_run:
                        for remaining in batch_tasks:
                            remaining_id = int(remaining.get("task_id") or 0)
                            if remaining_id <= 0:
                                continue
                            await self._update_task_status(db, task_id=remaining_id, status="FAILED")
                            await self.create_event(
                                db,
                                run_id=run_id,
                                project_id=project_id,
                                event_type="TASK_FAILED",
                                event_order=None,
                                payload={
                                    "task_id": remaining_id,
                                    "task_name": remaining.get("task_name"),
                                    "status": "FAILED",
                                    "skipped": True,
                                    "error": "Prior task failed",
                                    "message": "Skipped — prior task failed",
                                },
                            )
                        continue

                    if batch_mode == "parallel":
                        incomplete_batch = [
                            t for t in batch_tasks if not self._task_is_completed(t)
                        ]
                        if not incomplete_batch:
                            for task in batch_tasks:
                                task_id = int(task.get("task_id") or 0)
                                if task_id <= 0:
                                    continue
                                await self.create_event(
                                    db,
                                    run_id=run_id,
                                    project_id=project_id,
                                    event_type="TASK_COMPLETED",
                                    event_order=None,
                                    payload={
                                        "task_id": task_id,
                                        "task_name": task.get("task_name"),
                                        "status": "COMPLETED",
                                        "skipped": True,
                                        "message": f"{task.get('task_name') or 'Task'} already completed — skipped",
                                    },
                                )
                                per_task_results.append({"ok": True, "skipped": True, "task_id": task_id})
                            await self.create_event(
                                db,
                                run_id=run_id,
                                project_id=project_id,
                                event_type="TASK_BATCH_COMPLETED",
                                event_order=None,
                                payload={
                                    "parallel": True,
                                    "skipped": True,
                                    "task_count": len(batch_tasks),
                                    "success_count": len(batch_tasks),
                                    "message": f"Skipped parallel batch — all {len(batch_tasks)} section tasks already completed",
                                },
                            )
                            task_index += len(batch_tasks)
                            continue

                        batch_td = self._parse_task_data(batch_tasks[0])
                        batch_parallel = int(
                            batch_td.get("execution_max_concurrency")
                            or exec_params.get("section_task_parallelism")
                            or exec_params.get("max_concurrency")
                            or section_parallel
                        )
                        batch_parallel = max(1, min(batch_parallel, app_config.section_task_max_parallel))
                        stagger_seconds = float(
                            exec_params.get("parallel_cli_stagger_seconds")
                            or app_config.parallel_cli_stagger_seconds
                        )
                        batch_label = str(
                            batch_td.get("execution_batch_label")
                            or f"{len(batch_tasks)} parallel section tasks"
                        )
                        await self.create_event(
                            db,
                            run_id=run_id,
                            project_id=project_id,
                            event_type="TASK_BATCH_STARTED",
                            event_order=None,
                            payload={
                                "parallel": True,
                                "task_count": len(batch_tasks),
                                "max_concurrency": batch_parallel,
                                "task_ids": [int(t.get("task_id") or 0) for t in batch_tasks],
                                "batch_label": batch_label,
                                "message": (
                                    f"Running {len(batch_tasks)} tasks in parallel "
                                    f"(max {batch_parallel}, stagger {stagger_seconds}s): {batch_label}"
                                ),
                            },
                        )
                        semaphore = asyncio.Semaphore(batch_parallel)
                        spawn_slot = 0
                        spawn_slot_lock = asyncio.Lock()

                        async def _run_parallel_task(batch_task: Dict[str, Any], batch_index: int) -> Dict[str, Any]:
                            nonlocal spawn_slot
                            async with spawn_slot_lock:
                                slot = spawn_slot
                                spawn_slot += 1
                            delay = slot * stagger_seconds
                            async with semaphore:
                                return await self._execute_single_project_task(
                                    db,
                                    run_id=run_id,
                                    project_id=project_id,
                                    task=batch_task,
                                    index=batch_index,
                                    total=total,
                                    base_prompt=base_prompt,
                                    command_plan=command_plan,
                                    worktree_path=worktree_path,
                                    plan_by_task_id=plan_by_task_id,
                                    runtime_provider=runtime_provider,
                                    selection_mode=selection_mode,
                                    request_payload=request_payload,
                                    execution_context_pack=execution_context_pack,
                                    output_schema_path=output_schema_path,
                                    output_path_str=output_path_str,
                                    on_event=on_event,
                                    commit_on_success=False,
                                    cli_spawn_guard=True,
                                    cli_spawn_delay_seconds=delay,
                                )

                        batch_results = await asyncio.gather(
                            *[
                                _run_parallel_task(t, task_index + idx)
                                for idx, t in enumerate(batch_tasks)
                            ],
                            return_exceptions=True,
                        )
                        normalized: List[Dict[str, Any]] = []
                        for idx, result in enumerate(batch_results):
                            if isinstance(result, Exception):
                                normalized.append(
                                    {
                                        "ok": False,
                                        "task_id": int(batch_tasks[idx].get("task_id") or 0),
                                        "error": str(result),
                                    }
                                )
                            else:
                                normalized.append(result)
                        per_task_results.extend(normalized)
                        success_count = sum(1 for r in normalized if r.get("ok"))
                        batch_all_ok = success_count == len(normalized)
                        batch_ok = success_count > 0
                        all_ok = all_ok and batch_all_ok
                        if batch_ok and worktree_path:
                            for t in batch_tasks:
                                tid = int(t.get("task_id") or 0)
                                if tid > 0 and any(
                                    r.get("ok") and int(r.get("task_id") or 0) == tid for r in normalized
                                ):
                                    completed_task_ids.add(tid)
                            commit_result = await git_worktree_service.commit_changes(
                                worktree_path=worktree_path,
                                message=f"MAS run {run_id} parallel sections ({success_count}/{len(batch_tasks)} ok)",
                            )
                            if commit_result.get("committed"):
                                await self.create_event(
                                    db,
                                    run_id=run_id,
                                    project_id=project_id,
                                    event_type="GIT_COMMIT",
                                    event_order=None,
                                    payload={
                                        "commit_hash": commit_result.get("commit_hash"),
                                        "message": f"MAS run {run_id} parallel sections",
                                        "task_ids": [int(t.get("task_id") or 0) for t in batch_tasks],
                                    },
                                )
                        batch_event_type = "TASK_BATCH_COMPLETED"
                        if not batch_ok:
                            batch_event_type = "TASK_BATCH_FAILED"
                        elif not batch_all_ok:
                            batch_event_type = "TASK_BATCH_PARTIAL"
                        await self.create_event(
                            db,
                            run_id=run_id,
                            project_id=project_id,
                            event_type=batch_event_type,
                            event_order=None,
                            payload={
                                "parallel": True,
                                "task_count": len(batch_tasks),
                                "success_count": success_count,
                                "ok": batch_ok,
                                "partial": batch_ok and not batch_all_ok,
                                "task_ids": [int(t.get("task_id") or 0) for t in batch_tasks],
                                "message": (
                                    f"Parallel batch complete: {success_count}/{len(batch_tasks)} tasks succeeded"
                                ),
                            },
                        )
                        if not batch_ok:
                            fatal_error = next(
                                (
                                    self._fatal_cli_failure(r)
                                    for r in normalized
                                    if not r.get("ok")
                                ),
                                None,
                            ) or "All parallel section tasks failed"
                            skip_reason = fatal_error
                            fatal_cli_result = {
                                "ok": False,
                                "error": fatal_error,
                                "fatal_cli": bool(fatal_error),
                                "per_task_results": per_task_results,
                            }
                            stop_run = True
                        task_index += len(batch_tasks)
                        continue

                    for task in batch_tasks:
                        task_id = int(task.get("task_id") or 0)
                        if task_id > 0:
                            active_task_id = task_id
                        task_result = await self._execute_single_project_task(
                            db,
                            run_id=run_id,
                            project_id=project_id,
                            task=task,
                            index=task_index,
                            total=total,
                            base_prompt=base_prompt,
                            command_plan=command_plan,
                            worktree_path=worktree_path,
                            plan_by_task_id=plan_by_task_id,
                            runtime_provider=runtime_provider,
                            selection_mode=selection_mode,
                            request_payload=request_payload,
                            execution_context_pack=execution_context_pack,
                            output_schema_path=output_schema_path,
                            output_path_str=output_path_str,
                            on_event=on_event,
                            commit_on_success=True,
                            context_staged=context_staged,
                        )
                        if task_result.get("ok") and task_id > 0:
                            completed_task_ids.add(task_id)
                        per_task_results.append(task_result)
                        all_ok = all_ok and bool(task_result.get("ok"))
                        fatal_error = self._fatal_cli_failure(task_result)
                        if fatal_error or not task_result.get("ok"):
                            skip_reason = fatal_error or self._task_failure_detail(task_result) or "Task execution failed"
                            if fatal_error:
                                fatal_cli_result = {
                                    "ok": False,
                                    "error": fatal_error,
                                    "fatal_cli": True,
                                    "per_task_results": per_task_results,
                                }
                            stop_run = True
                            break
                        if (
                            execution_mode == "milestones"
                            and task_result.get("ok")
                            and task_id > 0
                        ):
                            for m_index, m_task_ids in milestone_groups.items():
                                if m_task_ids and m_task_ids[-1] == task_id:
                                    await self._milestone_boundary(
                                        db,
                                        run_id=run_id,
                                        project_id=project_id,
                                        repo_path=repo_path,
                                        worktree_path=str(worktree_path or ""),
                                        milestone_index=m_index,
                                        milestone_name=milestone_names.get(m_index, f"Milestone {m_index}"),
                                        percent_target=milestone_percent_targets.get(m_index, 0),
                                        completed_task_count=len(completed_task_ids),
                                        total_task_count=total,
                                    )
                                    break
                        task_index += 1
                    if stop_run:
                        # Mark any tasks not yet started as skipped/failed
                        remaining_ids = {
                            int(t.get("task_id") or 0)
                            for t in project_tasks[task_index:]
                            if int(t.get("task_id") or 0) > 0
                        }
                        for remaining in project_tasks:
                            remaining_id = int(remaining.get("task_id") or 0)
                            if remaining_id not in remaining_ids:
                                continue
                            status = str(remaining.get("status") or "").upper()
                            if status in {"COMPLETED", "DONE", "PASSED", "FAILED"}:
                                continue
                            await self._update_task_status(db, task_id=remaining_id, status="FAILED")
                            await self.create_event(
                                db,
                                run_id=run_id,
                                project_id=project_id,
                                event_type="TASK_FAILED",
                                event_order=None,
                                payload={
                                    "task_id": remaining_id,
                                    "task_name": remaining.get("task_name"),
                                    "status": "FAILED",
                                    "skipped": True,
                                    "error": skip_reason,
                                    "message": f"Skipped — prior task failed: {skip_reason}",
                                },
                            )
                        all_ok = False
                        break
                if fatal_cli_result:
                    execution_result = self._sanitize_cli_task_result(fatal_cli_result)
                    execution_result["per_task_results"] = [
                        self._sanitize_cli_task_result(item) for item in per_task_results
                    ]
                    execution_result["model_selection_mode"] = selection_mode
                else:
                    execution_result = self._build_execution_result(
                        per_task_results=per_task_results,
                        all_ok=all_ok,
                        selection_mode=selection_mode,
                    )
            else:
                execution_result = await self._execute_cli_plan(
                    runtime_provider=runtime_provider,
                    plan=command_plan,
                    event_callback=on_event,
                )
            run_status = "COMPLETED" if execution_result.get("ok") else "FAILED"

            if not use_per_task:
                for task in project_tasks:
                    task_id = int(task.get("task_id") or 0)
                    if task_id <= 0:
                        continue
                    task_status = "COMPLETED" if run_status == "COMPLETED" else "FAILED"
                    await self._update_task_status(db, task_id=task_id, status=task_status)
                    await self.create_event(
                        db,
                        run_id=run_id,
                        project_id=project_id,
                        event_type="TASK_COMPLETED" if task_status == "COMPLETED" else "TASK_FAILED",
                        event_order=None,
                        payload={
                            "task_id": task_id,
                            "task_name": task.get("task_name"),
                            "status": task_status,
                            "agent": runtime_provider,
                            "message": f"{task.get('task_name') or 'Task'} {task_status.lower()}",
                        },
                    )

            if stdout_log and stdout_log.exists():
                row = await artifact_service.record_artifact(
                    db,
                    run_id=run_id,
                    project_id=project_id,
                    artifact_type="log",
                    artifact_name="stdout.log",
                    artifact_path=str(stdout_log),
                    content_type="text/plain",
                    size_bytes=stdout_log.stat().st_size,
                    metadata={"stream": "stdout"},
                )
                artifact_count += 1 if row else 0
            if stderr_log and stderr_log.exists():
                row = await artifact_service.record_artifact(
                    db,
                    run_id=run_id,
                    project_id=project_id,
                    artifact_type="log",
                    artifact_name="stderr.log",
                    artifact_path=str(stderr_log),
                    content_type="text/plain",
                    size_bytes=stderr_log.stat().st_size,
                    metadata={"stream": "stderr"},
                )
                artifact_count += 1 if row else 0
            if output_path:
                out_file = Path(output_path)
                if out_file.exists():
                    row = await artifact_service.record_artifact(
                        db,
                        run_id=run_id,
                        project_id=project_id,
                        artifact_type="json-output",
                        artifact_name=out_file.name,
                        artifact_path=str(out_file),
                        content_type="application/json",
                        size_bytes=out_file.stat().st_size,
                        metadata={"source": runtime_provider},
                    )
                    artifact_count += 1 if row else 0

            worktree_path = worktree.get("worktree_path")
            if worktree_path:
                diff = await git_worktree_service.capture_diff(worktree_path)
                diff_summary = await git_change_service.record_diff_snapshot(
                    db,
                    project_id=project_id,
                    run_id=run_id,
                    repository_url=repository_url,
                    worktree_path=worktree_path,
                    branch_name=worktree.get("branch_name"),
                    base_branch=worktree.get("base_branch"),
                    status_lines=diff.get("status_lines") or [],
                    diff_excerpt=diff.get("diff_excerpt") or "",
                )

            design_fidelity_result: Optional[Dict[str, Any]] = None
            if worktree.get("worktree_path"):
                changed = diff_summary.get("changed_files") or []
                design_fidelity_result = design_fidelity_service.run_structural_checks(
                    worktree_path=worktree.get("worktree_path"),
                    context_pack=execution_context_pack,
                    changed_files=changed if isinstance(changed, list) else None,
                )
                execution_result["design_fidelity"] = design_fidelity_result
                if (
                    design_fidelity_result.get("hard_block_enabled")
                    and not design_fidelity_result.get("structural_pass")
                    and design_fidelity_result.get("blocking_failures")
                ):
                    execution_result["ok"] = False
                    run_status = "FAILED"

            quality_review_result: Optional[Dict[str, Any]] = None
            if should_run_post_execution_reviewer(
                task_agent_plan=task_agent_plan,
                balanced=balanced_routing,
            ):
                quality_review_result = await self._run_post_execution_reviewer(
                    db=db,
                    run_id=run_id,
                    project_id=project_id,
                    reviewer_provider=reviewer_provider,
                    selection_mode=selection_mode,
                    fixed_model=request_payload.get("model"),
                    context_pack=execution_context_pack,
                    worktree_path=worktree.get("worktree_path"),
                    diff_summary=diff_summary,
                    per_task_results=per_task_results,
                    event_callback=on_event,
                )
                if quality_review_result:
                    execution_result["quality_review_cli"] = quality_review_result
                    if not quality_review_result.get("ok"):
                        execution_result["ok"] = False
                        run_status = "FAILED"

            final_worktree_path = worktree.get("worktree_path")
            if final_worktree_path:
                try:
                    final_progress = await progress_service.compute_progress(db, project_id)
                    context_pack_service.write_progress_markdown(
                        str(final_worktree_path), progress_service.render_markdown(final_progress)
                    )
                    success_count = sum(1 for r in per_task_results if r.get("ok"))
                    context_pack_service.append_changelog(
                        str(final_worktree_path),
                        f"Run {run_id} {run_status.lower()}: {success_count}/{len(per_task_results)} tasks succeeded.",
                    )
                except Exception:
                    logger.exception("failed to refresh staged progress for run_id=%s", run_id)

            review = review_check_service.build_review(
                run_status=run_status,
                execution_result=execution_result,
                diff_summary=diff_summary,
                artifact_count=artifact_count,
                context_pack=execution_context_pack,
                design_fidelity=design_fidelity_result,
            )
            if quality_review_result:
                review["quality_review_cli"] = quality_review_result
            feature_review = review.get("feature_review") if isinstance(review, dict) else None
            if isinstance(feature_review, dict):
                row = await artifact_service.record_artifact(
                    db,
                    run_id=run_id,
                    project_id=project_id,
                    artifact_type="feature-review",
                    artifact_name="Feature quality review",
                    artifact_path=None,
                    content_type="application/json",
                    size_bytes=len(json.dumps(feature_review, default=str)),
                    metadata=feature_review,
                )
                artifact_count += 1 if row else 0
            await self._update_run(
                db,
                run_id,
                status=run_status,
                command_preview=" ".join(command),
                result_payload={
                    "execution": execution_result,
                    "review": review,
                    "git_changes": diff_summary,
                    "design_fidelity": design_fidelity_result,
                },
                finished=True,
            )
            await self.create_event(
                db,
                run_id=run_id,
                project_id=project_id,
                event_type="RUN_COMPLETED" if run_status == "COMPLETED" else "RUN_FAILED",
                event_order=None,
                payload={
                    "status": run_status,
                    "error": execution_result.get("error"),
                    "exit_code": execution_result.get("exit_code"),
                    "timed_out": execution_result.get("timed_out"),
                },
            )
            await change_history_service.record_change(
                db,
                project_id=project_id,
                entity_type="agent_run",
                entity_id=run_id,
                source="agentic.execution",
                change_type="RUN_COMPLETED" if run_status == "COMPLETED" else "RUN_FAILED",
                title=f"Run {run_status.lower()}",
                summary=f"Run {run_id} {run_status.lower()}",
                payload={"execution": execution_result, "review": review},
                created_by=created_by,
            )
        except asyncio.CancelledError:
            await self._update_run(
                db,
                run_id,
                status="CANCELLED",
                result_payload={"cancelled": True},
                finished=True,
            )
            await self.create_event(
                db,
                run_id=run_id,
                project_id=project_id,
                event_type="RUN_CANCELLED",
                event_order=None,
                payload={"reason": "cancelled by request"},
            )
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("run execution failed for run_id=%s", run_id)
            error_detail = f"{type(exc).__name__}: {exc}"
            if active_task_id and active_task_id not in completed_task_ids:
                await self._update_task_status(db, task_id=active_task_id, status="FAILED")
            safe_execution = (
                self._build_execution_result(
                    per_task_results=per_task_results,
                    all_ok=all_ok,
                    selection_mode=selection_mode,
                )
                if per_task_results
                else execution_result
            )
            try:
                await self._update_run(
                    db,
                    run_id,
                    status="FAILED",
                    result_payload={"error": error_detail, "execution": safe_execution},
                    finished=True,
                )
            except Exception:  # noqa: BLE001
                logger.exception("unable to persist failed run payload for run_id=%s", run_id)
                await self._update_run(
                    db,
                    run_id,
                    status="FAILED",
                    result_payload={"error": error_detail},
                    finished=True,
                )
            await self.create_event(
                db,
                run_id=run_id,
                project_id=project_id,
                event_type="RUN_FAILED",
                event_order=None,
                payload={"error": error_detail},
            )
        finally:
            self._active_tasks.pop(run_id, None)
            try:
                await self._finalize_stuck_run_if_needed(
                    db,
                    run_id=run_id,
                    project_id=project_id,
                    per_task_results=per_task_results,
                )
            except Exception:  # noqa: BLE001
                logger.exception("stuck-run finalize failed for run_id=%s", run_id)

    async def _task_statuses_from_run_events(
        self,
        db: DatabaseManager,
        *,
        run_id: int,
    ) -> Dict[int, str]:
        events = await self.list_run_events(db, run_id=run_id, limit=5000)
        statuses: Dict[int, str] = {}
        for event in events:
            event_type = str(event.get("event_type") or "").upper()
            payload = event.get("event_payload") if isinstance(event.get("event_payload"), dict) else {}
            task_id = int(payload.get("task_id") or 0)
            if task_id <= 0:
                continue
            if event_type == "TASK_QUEUED":
                statuses[task_id] = "QUEUED"
            elif event_type in {"TASK_MODEL_SELECTED", "TASK_STARTED", "TASK_RUNNING"}:
                statuses[task_id] = "RUNNING"
            elif event_type == "TASK_COMPLETED":
                statuses[task_id] = "COMPLETED"
            elif event_type == "TASK_FAILED":
                statuses[task_id] = "FAILED"
            elif event_type == "TASK_CANCELLED":
                statuses[task_id] = "CANCELLED"
        return statuses

    async def _finalize_stuck_run_if_needed(
        self,
        db: DatabaseManager,
        *,
        run_id: int,
        project_id: int,
        per_task_results: List[Dict[str, Any]],
    ) -> None:
        run = await self.get_run(db, run_id=run_id)
        if not run or str(run.get("status") or "").upper() != "RUNNING":
            return
        await self.reconcile_run(db, project_id=project_id, run_id=run_id, per_task_results=per_task_results)

    async def reconcile_run(
        self,
        db: DatabaseManager,
        *,
        project_id: int,
        run_id: int,
        per_task_results: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        run = await self.get_run(db, run_id=run_id)
        if not run or int(run.get("project_id") or 0) != project_id:
            return {"ok": False, "error": "Run not found"}

        statuses = await self._task_statuses_from_run_events(db, run_id=run_id)
        for task_id, status in statuses.items():
            await self._update_task_status(db, task_id=task_id, status=status)

        terminal_run_events = {
            "RUN_COMPLETED",
            "RUN_FAILED",
            "RUN_CANCELLED",
        }
        events = await self.list_run_events(db, run_id=run_id, limit=5000)
        for event in events:
            if str(event.get("event_type") or "").upper() in terminal_run_events:
                return {
                    "ok": True,
                    "run_id": run_id,
                    "status": str(run.get("status") or "").upper(),
                    "reconciled_tasks": statuses,
                    "already_terminal": True,
                }

        active = self._active_tasks.get(run_id)
        executor_live = active is not None and not active.done()
        running_tasks = [task_id for task_id, status in statuses.items() if status == "RUNNING"]
        if running_tasks and not executor_live:
            for task_id in running_tasks:
                statuses[task_id] = "FAILED"
                await self._update_task_status(db, task_id=task_id, status="FAILED")
                await self.create_event(
                    db,
                    run_id=run_id,
                    project_id=project_id,
                    event_type="TASK_FAILED",
                    event_order=None,
                    payload={
                        "task_id": task_id,
                        "status": "FAILED",
                        "stale": True,
                        "message": "Task marked failed — executor no longer running",
                    },
                )

        failed_tasks = [task_id for task_id, status in statuses.items() if status == "FAILED"]
        completed_tasks = [task_id for task_id, status in statuses.items() if status == "COMPLETED"]
        run_status = "FAILED" if failed_tasks else "COMPLETED" if completed_tasks else "FAILED"
        request_payload = run.get("request_payload") if isinstance(run.get("request_payload"), dict) else {}
        selection_mode = str(request_payload.get("model_selection_mode") or MODEL_SELECTION_OPTIMIZED)
        safe_results = per_task_results or []
        execution_payload = (
            self._build_execution_result(
                per_task_results=safe_results,
                all_ok=run_status == "COMPLETED",
                selection_mode=selection_mode,
            )
            if safe_results
            else {"ok": run_status == "COMPLETED", "reconciled": True}
        )
        await self._update_run(
            db,
            run_id,
            status=run_status,
            result_payload={"execution": execution_payload, "reconciled": True},
            finished=True,
        )
        await self.create_event(
            db,
            run_id=run_id,
            project_id=project_id,
            event_type="RUN_COMPLETED" if run_status == "COMPLETED" else "RUN_FAILED",
            event_order=None,
            payload={"status": run_status, "reconciled": True},
        )
        return {
            "ok": True,
            "run_id": run_id,
            "status": run_status,
            "reconciled_tasks": statuses,
        }

    async def cancel_run(self, db: DatabaseManager, *, project_id: int, run_id: int) -> Dict[str, Any]:
        run = await self.get_run(db, run_id=run_id)
        if not run or int(run.get("project_id") or 0) != project_id:
            return {"ok": False, "error": "Run not found"}
        task = self._active_tasks.get(run_id)
        if task and not task.done():
            task.cancel()
            await self.create_event(
                db,
                run_id=run_id,
                project_id=project_id,
                event_type="RUN_CANCEL_REQUESTED",
                event_order=None,
                payload={},
            )
            return {"ok": True, "status": "CANCEL_REQUESTED"}
        if str(run.get("status")) in {"COMPLETED", "FAILED", "CANCELLED"}:
            return {"ok": True, "status": run.get("status")}
        await self._update_run(db, run_id, status="CANCELLED", result_payload={"cancelled": True}, finished=True)
        await self.create_event(
            db,
            run_id=run_id,
            project_id=project_id,
            event_type="RUN_CANCELLED",
            event_order=None,
            payload={"reason": "marked cancelled without active task"},
        )
        return {"ok": True, "status": "CANCELLED"}

    async def _delete_run_records(self, db: DatabaseManager, *, run_id: int) -> Dict[str, int]:
        deleted = {"events": 0, "artifacts": 0, "git_changes": 0, "run": 0}
        if await schema_support.table_exists(db, "agent_event"):
            deleted["events"] = int(
                await db.fetch_val(
                    "SELECT COUNT(*) FROM main.agent_event WHERE agent_run_id = $1",
                    run_id,
                )
                or 0
            )
            if deleted["events"]:
                await db.execute("DELETE FROM main.agent_event WHERE agent_run_id = $1", run_id)
        if await schema_support.table_exists(db, "agent_artifact"):
            deleted["artifacts"] = int(
                await db.fetch_val(
                    "SELECT COUNT(*) FROM main.agent_artifact WHERE agent_run_id = $1",
                    run_id,
                )
                or 0
            )
            if deleted["artifacts"]:
                await db.execute("DELETE FROM main.agent_artifact WHERE agent_run_id = $1", run_id)
        if await schema_support.table_exists(db, "git_change"):
            deleted["git_changes"] = int(
                await db.fetch_val(
                    "SELECT COUNT(*) FROM main.git_change WHERE agent_run_id = $1",
                    run_id,
                )
                or 0
            )
            if deleted["git_changes"]:
                await db.execute("DELETE FROM main.git_change WHERE agent_run_id = $1", run_id)
        if await schema_support.table_exists(db, "agent_run"):
            exists = await db.fetch_val(
                "SELECT COUNT(*) FROM main.agent_run WHERE agent_run_id = $1",
                run_id,
            )
            if int(exists or 0):
                await db.execute("DELETE FROM main.agent_run WHERE agent_run_id = $1", run_id)
                deleted["run"] = 1
        return deleted

    async def cleanup_run(
        self,
        db: DatabaseManager,
        *,
        project_id: int,
        run_id: int,
        delete_record: bool = True,
        created_by: str = "dashboard",
    ) -> Dict[str, Any]:
        run = await self.get_run(db, run_id=run_id)
        if not run or int(run.get("project_id") or 0) != project_id:
            return {"ok": False, "error": "Run not found"}

        active = self._active_tasks.get(run_id)
        if active and not active.done():
            active.cancel()
            try:
                await active
            except asyncio.CancelledError:
                pass
            self._active_tasks.pop(run_id, None)

        metadata = await project_metadata_service.get_project_metadata(db, project_id)
        repo_path = self._resolve_project_repo_path(metadata) or ""
        git_summary: Dict[str, Any] = {"ok": True, "skipped": True, "reason": "no repository path"}
        branch_name = f"mas-quick-run/{run_id}"

        if repo_path:
            run_dir = str(self._resolve_run_artifact_dir(repo_path, run_id))
            git_summary = await git_worktree_service.cleanup_run_workspace(
                repo_path=repo_path,
                project_id=project_id,
                run_id=run_id,
                branch_name=branch_name,
                worktree_base_path=app_config.midnight_worktree_base_path or None,
                run_artifact_dir=run_dir,
            )

        deleted: Dict[str, int] = {}
        if delete_record:
            deleted = await self._delete_run_records(db, run_id=run_id)
        else:
            await self._update_run(
                db,
                run_id,
                status="CANCELLED",
                result_payload={"cleaned_up": True, "git": git_summary},
                finished=True,
            )

        await change_history_service.record_change(
            db,
            project_id=project_id,
            entity_type="agent_run",
            entity_id=run_id,
            source="dashboard.cleanup",
            change_type="RUN_CLEANED_UP",
            title=f"Run {run_id} cleaned up",
            summary="Removed worktree, branch, and run artifacts via git",
            payload={"git": git_summary, "deleted": deleted},
            created_by=created_by,
        )

        return {
            "ok": bool(git_summary.get("ok", True)),
            "run_id": run_id,
            "git": git_summary,
            "deleted": deleted,
            "delete_record": delete_record,
        }

    async def retry_run(
        self,
        db: DatabaseManager,
        *,
        project_id: int,
        run_id: int,
        created_by: str = "dashboard",
    ) -> Dict[str, Any]:
        run = await self.get_run(db, run_id=run_id)
        if not run or int(run.get("project_id") or 0) != project_id:
            return {"ok": False, "error": "Run not found"}
        request = run.get("request_payload") or {}
        async with _get_project_run_lock(project_id):
            await self._release_stale_running_runs(db)
            existing = await self._live_project_run(db, project_id)
            if existing and int(existing.get("agent_run_id") or 0) != run_id:
                return self._already_running_response(existing)
            if str(run.get("status") or "").upper() == "RUNNING":
                await self.cancel_run(db, project_id=project_id, run_id=run_id)
            await self.create_event(
                db,
                run_id=run_id,
                project_id=project_id,
                event_type="RUN_RETRY_REQUESTED",
                event_order=None,
                payload={
                    "source_run_id": run_id,
                    "message": f"Retry requested from run #{run_id}",
                },
            )
            project_tasks = await self._project_tasks(db, project_id)
            continue_from = self._first_incomplete_task(project_tasks)
            continue_index = None
            if continue_from:
                for idx, task in enumerate(project_tasks):
                    if int(task.get("task_id") or 0) == int(continue_from.get("task_id") or 0):
                        continue_index = idx + 1
                        break
            result = await self._create_quick_run_plan_unlocked(
                db,
                project_id=project_id,
                user_prompt=str(request.get("user_prompt") or ""),
                template_name=str(request.get("template_name") or "quick_run_system_prompt"),
                runtime_provider=str(run.get("runtime_provider") or app_config.midnight_default_runtime),
                model=request.get("model"),
                model_selection_mode=str(request.get("model_selection_mode") or MODEL_SELECTION_OPTIMIZED),
                include_change_history=bool(request.get("include_change_history", True)),
                include_document_versions=bool(request.get("include_document_versions", True)),
                use_worktree=bool(request.get("use_worktree", True)),
                dry_run=False,
                created_by=created_by,
                output_schema_name=request.get("output_schema_name"),
                source_run_id=run_id,
            )
            new_run = result.get("run") or {}
            new_run_id = int(new_run.get("agent_run_id") or 0)
            if continue_from:
                result["continue_from_task"] = {
                    "task_id": int(continue_from.get("task_id") or 0),
                    "task_name": continue_from.get("task_name"),
                    "task_index": continue_index,
                    "status": continue_from.get("status"),
                }
            if new_run_id > 0:
                task_label = str(continue_from.get("task_name") or "next task") if continue_from else "next task"
                index_label = f" (task {continue_index})" if continue_index else ""
                result["message"] = (
                    f"Retry started as run #{new_run_id}, continuing at{index_label}: {task_label}."
                )
                result["source_run_id"] = run_id
            return result

    async def stream_events(
        self,
        db: DatabaseManager,
        *,
        run_id: int,
        poll_seconds: float = 1.0,
    ) -> AsyncIterator[str]:
        if not await schema_support.table_exists(db, "agent_event"):
            yield "event: info\ndata: {\"message\":\"agent_event table unavailable\"}\n\n"
            return
        last_event_id = 0
        idle_ticks = 0
        while True:
            rows = await db.fetch_many(
                """
                SELECT *
                FROM main.agent_event
                WHERE agent_run_id = $1
                  AND agent_event_id > $2
                ORDER BY agent_event_id ASC
                LIMIT 200
                """,
                run_id,
                last_event_id,
            )
            if rows:
                idle_ticks = 0
                for row in rows:
                    payload = decode_jsonb_fields(dict(row), self._EVENT_JSON_FIELDS)
                    event_id = int(payload.get("agent_event_id") or 0)
                    last_event_id = max(last_event_id, event_id)
                    event_name = str(payload.get("event_type") or "event").lower()
                    data = json.dumps(payload, default=str)
                    yield f"id: {event_id}\nevent: {event_name}\ndata: {data}\n\n"
                continue

            run = await self.get_run(db, run_id=run_id)
            status = str(run.get("status") or "")
            if status in {"COMPLETED", "FAILED", "CANCELLED", "BLOCKED", "PLANNED"}:
                idle_ticks += 1
                if idle_ticks > 2:
                    break
            yield ": keep-alive\n\n"
            await asyncio.sleep(poll_seconds)


    async def recover_orphan_runs(
        self,
        db: DatabaseManager,
        *,
        grace_seconds: int = 30,
    ) -> Dict[str, Any]:
        """Mark in-flight runs as terminal when no asyncio task is active (e.g. after API restart)."""
        if not await schema_support.table_exists(db, "agent_run"):
            return {"ok": True, "recovered": []}

        rows = await db.fetch_many(
            """
            SELECT agent_run_id, project_id, started_at
            FROM main.agent_run
            WHERE UPPER(COALESCE(status, '')) IN ('RUNNING', 'PENDING', 'STARTED')
            ORDER BY agent_run_id
            """
        )
        recovered: List[Dict[str, Any]] = []
        for row in rows:
            run_id = int(row.get("agent_run_id") or 0)
            project_id = int(row.get("project_id") or 0)
            if run_id <= 0 or project_id <= 0:
                continue
            active = self._active_tasks.get(run_id)
            if active is not None and not active.done():
                continue

            result = await self.reconcile_run(db, project_id=project_id, run_id=run_id)
            if result.get("ok") and str(result.get("status") or "").upper() not in {"", "RUNNING"}:
                recovered.append({"run_id": run_id, "project_id": project_id, "status": result.get("status")})
                continue

            error_detail = "Run orphaned after API restart (no active executor)"
            await self._update_run(
                db,
                run_id,
                status="FAILED",
                result_payload={"error": error_detail, "orphaned_on_restart": True},
                finished=True,
            )
            await self.create_event(
                db,
                run_id=run_id,
                project_id=project_id,
                event_type="RUN_FAILED",
                event_order=None,
                payload={"error": error_detail, "orphaned_on_restart": True},
            )
            recovered.append({"run_id": run_id, "project_id": project_id, "status": "FAILED"})

        if recovered:
            logger.warning("recovered %s orphan run(s): %s", len(recovered), recovered)
        return {"ok": True, "recovered": recovered}


run_service = RunService()
