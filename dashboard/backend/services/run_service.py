from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from ..config import app_config
from ..database import DatabaseManager
from .artifact_service import artifact_service
from .change_history_service import change_history_service
from .codex_cli_runner import CodexCliRunPlan, codex_cli_runner
from .context_pack_service import context_pack_service
from .git_change_service import git_change_service
from .git_worktree_service import git_worktree_service
from .jsonb_utils import decode_jsonb_fields, jsonb_dumps
from .prompt_template_service import prompt_template_service
from .project_metadata_service import project_metadata_service
from .review_check_service import review_check_service
from .runtime_check_service import runtime_check_service
from .schema_support import schema_support
from .verification_service import verification_service

logger = logging.getLogger(__name__)


class RunService:
    _RUN_JSON_FIELDS = ("request_payload", "context_pack", "result_payload")
    _EVENT_JSON_FIELDS = ("event_payload",)

    def __init__(self) -> None:
        self._active_tasks: Dict[int, asyncio.Task[None]] = {}

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

    async def list_run_events(
        self,
        db: DatabaseManager,
        run_id: int,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        if not await schema_support.table_exists(db, "agent_event"):
            return []
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

    async def _update_run(
        self,
        db: DatabaseManager,
        run_id: int,
        *,
        status: Optional[str] = None,
        command_preview: Optional[str] = None,
        result_payload: Optional[Dict[str, Any]] = None,
        finished: bool = False,
    ) -> Dict[str, Any]:
        fields: List[str] = []
        values: List[Any] = []
        idx = 1
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

    async def _prepare_quick_run(
        self,
        db: DatabaseManager,
        *,
        project_id: int,
        user_prompt: str,
        template_name: str,
        runtime_provider: str,
        model: Optional[str],
        include_change_history: bool,
        include_document_versions: bool,
        use_worktree: bool,
        dry_run: bool,
        created_by: str,
        output_schema_name: Optional[str] = None,
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

        selected_model = model or app_config.codex_cli_model
        full_prompt = (
            f"{template_text}\n\n"
            f"Project ID: {project_id}\n"
            f"User Prompt:\n{user_prompt}\n\n"
            f"Context Pack:\n{json.dumps(context_pack, default=str)}"
        )

        warnings = list(verification.warnings)
        errors: List[str] = []
        if runtime_provider != "codex-cli":
            warnings.append(f"runtime_provider '{runtime_provider}' is currently preview-only")
            if not dry_run:
                errors.append(f"runtime_provider '{runtime_provider}' is not executable yet")
        if runtime_provider == "codex-cli" and not runtime["codex_cli"]["found"]:
            warnings.append("codex cli binary not found on PATH; run can only be planned")
            if not dry_run:
                errors.append("codex cli binary not found on PATH")

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
        if not dry_run and self._active_task_count(self._active_tasks) >= app_config.midnight_max_concurrency:
            errors.append(
                f"max concurrency reached ({app_config.midnight_max_concurrency}); "
                "wait for active runs to complete"
            )

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
                    created_by
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7)
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
                        "model": selected_model,
                        "dry_run": dry_run,
                        "include_change_history": include_change_history,
                        "include_document_versions": include_document_versions,
                        "use_worktree": use_worktree,
                        "output_schema_name": output_schema_name,
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
        }
        if use_worktree and repo_path and run_id > 0:
            resolved_worktree_path = git_worktree_service.resolve_worktree_path(
                repo_path=repo_path,
                project_id=project_id,
                run_id=run_id,
                worktree_base_path=app_config.midnight_worktree_base_path or None,
            )
            if dry_run:
                worktree = {
                    "branch_name": f"mas/quick-run/{run_id}",
                    "worktree_path": resolved_worktree_path,
                    "base_branch": base_branch,
                    "reuse_existing_branch": False,
                }
            else:
                try:
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
                    }
                except Exception as exc:
                    warnings.append(f"worktree creation failed: {exc}")
                    worktree = {
                        "branch_name": None,
                        "worktree_path": execution_path,
                        "base_branch": base_branch,
                        "reuse_existing_branch": False,
                    }
        elif use_worktree and not repo_path:
            warnings.append("worktree planning skipped because project repository path is not configured")

        run_dir: Optional[Path] = None
        output_path: Optional[Path] = None
        output_schema_path: Optional[Path] = None
        if run_id > 0 and repo_path:
            run_dir = self._resolve_run_artifact_dir(repo_path, run_id)
            run_dir.mkdir(parents=True, exist_ok=True)
            output_path = run_dir / "codex-output.json"
            if output_schema_name:
                try:
                    schema = prompt_template_service.load_json_schema(output_schema_name)
                    output_schema_path = run_dir / f"{output_schema_name}.schema.json"
                    output_schema_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
                except FileNotFoundError:
                    warnings.append(f"json schema '{output_schema_name}' not found")

        plan = CodexCliRunPlan(
            prompt=full_prompt,
            model=selected_model,
            worktree_path=worktree.get("worktree_path"),
            output_json=True,
            output_schema_path=str(output_schema_path) if output_schema_path else None,
            output_path=str(output_path) if output_path else None,
            approval_mode=app_config.codex_approval_mode,
            sandbox_mode=app_config.codex_sandbox_mode,
        )

        if runtime_provider == "codex-cli":
            capabilities = await codex_cli_runner.detect_capabilities(app_config.codex_cli_bin)
            command = codex_cli_runner.build_command(app_config.codex_cli_bin, plan, capabilities)
        else:
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
        include_change_history: bool = True,
        include_document_versions: bool = True,
        use_worktree: bool = True,
        dry_run: bool = True,
        created_by: str = "dashboard",
        output_schema_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        prepared = await self._prepare_quick_run(
            db,
            project_id=project_id,
            user_prompt=user_prompt,
            template_name=template_name,
            runtime_provider=runtime_provider,
            model=model,
            include_change_history=include_change_history,
            include_document_versions=include_document_versions,
            use_worktree=use_worktree,
            dry_run=dry_run,
            created_by=created_by,
            output_schema_name=output_schema_name,
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
                command_preview=" ".join(command),
                result_payload={
                    "warnings": prepared.get("warnings", []),
                    "errors": prepared.get("errors", []),
                    "dry_run": dry_run,
                    "worktree": prepared.get("worktree"),
                    "preflight": prepared.get("preflight"),
                },
            )
            prepared["run"] = updated or run_row

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

    async def _execute_run(
        self,
        *,
        db: DatabaseManager,
        run_id: int,
        project_id: int,
        command_plan: CodexCliRunPlan,
        command: List[str],
        runtime_provider: str,
        worktree: Dict[str, Any],
        run_dir: Optional[str],
        output_path: Optional[str],
        repository_url: Optional[str],
        created_by: str,
    ) -> None:
        if runtime_provider != "codex-cli":
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
        diff_summary: Dict[str, Any] = {"inserted": 0}
        artifact_count = 0
        try:
            execution_result = await codex_cli_runner.execute_streaming(
                cli_binary=app_config.codex_cli_bin,
                plan=command_plan,
                timeout_seconds=app_config.codex_cli_timeout_seconds,
                event_callback=on_event,
            )
            run_status = "COMPLETED" if execution_result.get("ok") else "FAILED"

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
                        metadata={"source": "codex-cli"},
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

            review = review_check_service.build_review(
                run_status=run_status,
                execution_result=execution_result,
                diff_summary=diff_summary,
                artifact_count=artifact_count,
            )
            await self._update_run(
                db,
                run_id,
                status=run_status,
                command_preview=" ".join(command),
                result_payload={
                    "execution": execution_result,
                    "review": review,
                    "git_changes": diff_summary,
                },
                finished=True,
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
            await self._update_run(
                db,
                run_id,
                status="FAILED",
                result_payload={"error": str(exc), "execution": execution_result},
                finished=True,
            )
            await self.create_event(
                db,
                run_id=run_id,
                project_id=project_id,
                event_type="RUN_FAILED",
                event_order=None,
                payload={"error": str(exc)},
            )
        finally:
            self._active_tasks.pop(run_id, None)

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
        return await self.create_quick_run_plan(
            db,
            project_id=project_id,
            user_prompt=str(request.get("user_prompt") or ""),
            template_name=str(request.get("template_name") or "quick_run_system_prompt"),
            runtime_provider=str(run.get("runtime_provider") or app_config.midnight_default_runtime),
            model=request.get("model"),
            include_change_history=bool(request.get("include_change_history", True)),
            include_document_versions=bool(request.get("include_document_versions", True)),
            use_worktree=bool(request.get("use_worktree", True)),
            dry_run=False,
            created_by=created_by,
            output_schema_name=request.get("output_schema_name"),
        )

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


run_service = RunService()
