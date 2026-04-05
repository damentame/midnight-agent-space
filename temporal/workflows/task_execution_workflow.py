"""Temporal workflow for DB-driven task execution orchestration."""
import logging
from dataclasses import dataclass, asdict
from datetime import timedelta
from typing import Any, Dict, Optional

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError

logger = logging.getLogger(__name__)


@dataclass
class TaskExecutionInput:
    project_id: int
    agent_id: int
    agent_instance_id: int
    max_tasks: int = 50
    workspace_root: Optional[str] = None
    # Optional workflow_run_id from the parent DocumentSerializationWorkflow, used
    # for naming and managing per-run develop and task branches.
    branch_workflow_run_id: Optional[int] = None
    # Agent provider for task execution (\"cursor\" or \"codex\").
    agent_provider: str = "cursor"
    # When True, task branches are left unmerged for human review instead of being
    # auto-merged back into the workflow's develop branch.
    require_human_review: bool = False
    # When True, tasks that can be executed independently will be run concurrently
    # as separate child workflows. When False (default), tasks are executed
    # sequentially within this workflow.
    concurrent_tasks: bool = False
    # fast: quicker/cheaper models; complex: more capable models (see model_routing).
    execute_mode: str = "fast"
    # When True, run task execution phase as one batched activity (see execute_task_batch_activity).
    batch_tasks: bool = False


@dataclass
class TaskExecutionResult:
    project_id: int
    tasks_executed: int
    workflow_run_id: Optional[int] = None


@dataclass
class SingleTaskExecutionInput:
    """Input for executing a single task as a child workflow (used for concurrency)."""
    task: Dict[str, Any]
    project_id: int
    agent_id: int
    agent_instance_id: int
    workspace_root: Optional[str] = None
    branch_workflow_run_id: Optional[int] = None
    agent_provider: str = "cursor"
    require_human_review: bool = False
    execute_mode: str = "fast"


@workflow.defn
class SingleTaskExecutionWorkflow:
    """Child workflow to execute a single task, reusing the same activities as the main workflow."""

    @workflow.run
    async def run(self, input: SingleTaskExecutionInput) -> Dict[str, Any]:
        with workflow.unsafe.imports_passed_through():
            from temporal.activities.task_execution_activities import (
                start_task_execution_activity,
                finish_task_execution_activity,
                log_task_step_activity,
                execute_task_with_agent_activity,
                index_code_context_activity,
                ensure_workflow_develop_branch_activity,
                merge_task_branch_into_develop_activity,
            )
            from temporal.activities.document_activities import (
                retrieve_rag_context_activity,
            )
            from temporal.activities.api_activities import (
                decommission_cursor_agent_activity,
            )

        workspace_root = input.workspace_root or ""
        develop_branch_name: Optional[str] = None

        if input.branch_workflow_run_id is not None:
            develop_branch_name = f"develop-{input.branch_workflow_run_id}"
            try:
                await workflow.execute_activity(
                    ensure_workflow_develop_branch_activity,
                    args=[input.branch_workflow_run_id],
                    start_to_close_timeout=timedelta(seconds=60),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
            except Exception as ensure_err:
                workflow.logger.warning(
                    "SingleTaskExecutionWorkflow: failed to ensure develop branch for workflow_run_id=%s: %s",
                    input.branch_workflow_run_id,
                    ensure_err,
                )

        task = input.task
        task_id = task.get("task_id")
        task_name = task.get("task_name")

        # Log start
        await workflow.execute_activity(
            log_task_step_activity,
            args=[
                input.project_id,
                "single_task_start",
                {"task_id": task_id, "task_name": task_name},
                task_id,
                None,
                None,
            ],
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )

        task_execution_id = await workflow.execute_activity(
            start_task_execution_activity,
            args=[task_id, input.agent_id, input.agent_instance_id],
            start_to_close_timeout=timedelta(seconds=15),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        await workflow.execute_activity(
            log_task_step_activity,
            args=[
                input.project_id,
                "start_task_execution",
                {"task_execution_id": task_execution_id},
                task_id,
                task_execution_id,
                None,
            ],
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )

        # RAG context
        try:
            query_text = (task.get("description") or "") or (task.get("task_name") or "")
            rag_context = await workflow.execute_activity(
                retrieve_rag_context_activity,
                args=[query_text, input.project_id],
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )
        except Exception as rag_err:
            workflow.logger.warning(
                "SingleTaskExecutionWorkflow: RAG retrieval failed for task_id=%s: %s",
                task_id,
                rag_err,
            )
            rag_context = {}

        # Execute task via selected agent provider
        try:
            exec_result = await workflow.execute_activity(
                execute_task_with_agent_activity,
                args=[
                    task,
                    input.project_id,
                    input.agent_id,
                    input.agent_instance_id,
                    rag_context,
                    workspace_root,
                    input.branch_workflow_run_id,
                    develop_branch_name,
                    input.agent_provider,
                    input.execute_mode,
                    None,
                    None,
                    False,
                ],
                start_to_close_timeout=timedelta(minutes=65),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        except Exception as exec_err:
            workflow.logger.error(
                "SingleTaskExecutionWorkflow: task execution failed for task_id=%s: %s",
                task_id,
                exec_err,
            )
            await workflow.execute_activity(
                finish_task_execution_activity,
                args=[
                    task_execution_id,
                    "FAILED",
                    {"error": str(exec_err), "status": "FAILED"},
                    str(exec_err),
                ],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            await workflow.execute_activity(
                log_task_step_activity,
                args=[
                    input.project_id,
                    "execute_task_failed",
                    {"error": str(exec_err)},
                    task_id,
                    task_execution_id,
                    None,
                ],
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )
            raise

        # Decommission Cursor agent if present
        cursor_agent_id = exec_result.get("cursor_agent_id")
        if cursor_agent_id:
            try:
                await workflow.execute_activity(
                    decommission_cursor_agent_activity,
                    args=[cursor_agent_id],
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
            except Exception as dec_err:
                workflow.logger.warning(
                    "SingleTaskExecutionWorkflow: failed to decommission Cursor agent %s: %s",
                    cursor_agent_id,
                    dec_err,
                )

        # Merge branch if applicable
        task_branch_name = exec_result.get("task_branch_name")
        if (
            input.branch_workflow_run_id is not None
            and develop_branch_name
            and task_branch_name
            and not input.require_human_review
        ):
            try:
                await workflow.execute_activity(
                    merge_task_branch_into_develop_activity,
                    args=[
                        input.branch_workflow_run_id,
                        task_branch_name,
                        develop_branch_name,
                        input.require_human_review,
                    ],
                    start_to_close_timeout=timedelta(minutes=5),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
            except Exception as merge_err:
                workflow.logger.warning(
                    "SingleTaskExecutionWorkflow: failed to merge task branch %s into %s: %s",
                    task_branch_name,
                    develop_branch_name,
                    merge_err,
                )

        await workflow.execute_activity(
            log_task_step_activity,
            args=[
                input.project_id,
                "execute_task",
                {"status": exec_result.get("status"), "cursor_agent_id": exec_result.get("cursor_agent_id")},
                task_id,
                task_execution_id,
                None,
            ],
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )

        # Re-index changed files
        try:
            await workflow.execute_activity(
                index_code_context_activity,
                args=[
                    input.project_id,
                    workspace_root,
                    exec_result.get("files_modified"),
                ],
                start_to_close_timeout=timedelta(minutes=10),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )
        except Exception as idx_err:
            workflow.logger.warning(
                "SingleTaskExecutionWorkflow: index_code_context failed for task_id=%s: %s",
                task_id,
                idx_err,
            )

        await workflow.execute_activity(
            log_task_step_activity,
            args=[
                input.project_id,
                "index_code_context",
                {},
                task_id,
                task_execution_id,
                None,
            ],
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )

        await workflow.execute_activity(
            finish_task_execution_activity,
            args=[
                task_execution_id,
                "COMPLETED",
                exec_result,
                f"Task {task_id} ({task_name}) completed by Task Executor",
            ],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        await workflow.execute_activity(
            log_task_step_activity,
            args=[
                input.project_id,
                "finish_task_execution",
                {"status": "COMPLETED"},
                task_id,
                task_execution_id,
                None,
            ],
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )

        return {"task_id": task_id, "status": "COMPLETED"}


@workflow.defn
class TaskExecutionWorkflow:
    """
    Workflow that repeatedly asks the database for the next ready task,
    executes it via the Task Executor (Cursor) agent, indexes code context for RAG,
    and logs every step to event_log. Full traceability via activity_run and event_log.
    """

    @workflow.run
    async def run(self, input: TaskExecutionInput) -> TaskExecutionResult:
        with workflow.unsafe.imports_passed_through():
            from temporal.activities.task_execution_activities import (
                get_next_ready_task_activity,
                start_task_execution_activity,
                finish_task_execution_activity,
                log_task_step_activity,
                execute_task_with_agent_activity,
                execute_task_batch_activity,
                execute_tasks_concurrent_claude_code_activity,
                index_code_context_activity,
                ensure_workflow_develop_branch_activity,
                merge_task_branch_into_develop_activity,
            )
            from temporal.activities.document_activities import (
                retrieve_rag_context_activity,
            )
            from temporal.activities.agent_activities import (
                start_workflow_run_activity,
                finish_workflow_run_activity,
            )
            from temporal.activities.api_activities import (
                decommission_cursor_agent_activity,
            )

        workflow_run_id: Optional[int] = None
        try:
            workflow_run_id = await workflow.execute_activity(
                start_workflow_run_activity,
                args=[
                    "TaskExecutionWorkflow",
                    input.project_id,
                    input.agent_instance_id,
                    asdict(input),
                ],
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
        except Exception as e:
            workflow.logger.warning("Could not start workflow_run row: %s", e)

        executed_count = 0
        workspace_root = input.workspace_root or ""
        develop_branch_name: Optional[str] = None

        # If a parent workflow_run_id was provided, compute the per-run develop
        # branch name following the develop-<workflow_run_id> convention and
        # ensure it exists before executing any tasks.
        if input.branch_workflow_run_id is not None:
            develop_branch_name = f"develop-{input.branch_workflow_run_id}"
            try:
                await workflow.execute_activity(
                    ensure_workflow_develop_branch_activity,
                    args=[input.branch_workflow_run_id],
                    start_to_close_timeout=timedelta(seconds=60),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
            except Exception as ensure_err:
                workflow.logger.warning(
                    "Failed to ensure develop branch for workflow_run_id=%s: %s",
                    input.branch_workflow_run_id,
                    ensure_err,
                )

        try:
            if input.concurrent_tasks and input.batch_tasks:
                raise ApplicationError(
                    "concurrent_tasks and batch_tasks cannot both be true",
                    non_retryable=True,
                )

            if input.batch_tasks and not input.concurrent_tasks:
                batch_result = await workflow.execute_activity(
                    execute_task_batch_activity,
                    args=[
                        input.project_id,
                        input.agent_id,
                        input.agent_instance_id,
                        input.max_tasks,
                        workspace_root or None,
                        input.branch_workflow_run_id,
                        develop_branch_name,
                        input.agent_provider,
                        input.execute_mode,
                        input.require_human_review,
                    ],
                    start_to_close_timeout=timedelta(hours=6),
                    retry_policy=RetryPolicy(maximum_attempts=1),
                )
                executed_count = int(batch_result.get("tasks_executed", 0))
            elif not input.concurrent_tasks:
                while executed_count < input.max_tasks:
                    next_task: Optional[Dict[str, Any]] = await workflow.execute_activity(
                        get_next_ready_task_activity,
                        args=[input.project_id, input.branch_workflow_run_id],
                        start_to_close_timeout=timedelta(seconds=15),
                        retry_policy=RetryPolicy(maximum_attempts=3),
                    )

                    await workflow.execute_activity(
                        log_task_step_activity,
                        args=[
                            input.project_id,
                            "next_task_fetched",
                            {"task_id": next_task.get("task_id") if next_task else None, "has_task": next_task is not None},
                            next_task.get("task_id") if next_task else None,
                            None,
                            None,
                        ],
                        start_to_close_timeout=timedelta(seconds=10),
                        retry_policy=RetryPolicy(maximum_attempts=2),
                    )

                    if not next_task or not next_task.get("task_id"):
                        workflow.logger.info(
                            "No more ready tasks for project_id=%s", input.project_id
                        )
                        break

                    task_id = next_task.get("task_id")
                    task_name = next_task.get("task_name")
                    workflow.logger.info(
                        "Starting execution for task_id=%s (%s)", task_id, task_name
                    )

                    task_execution_id = await workflow.execute_activity(
                        start_task_execution_activity,
                        args=[task_id, input.agent_id, input.agent_instance_id],
                        start_to_close_timeout=timedelta(seconds=15),
                        retry_policy=RetryPolicy(maximum_attempts=3),
                    )

                    await workflow.execute_activity(
                        log_task_step_activity,
                        args=[
                            input.project_id,
                            "start_task_execution",
                            {"task_execution_id": task_execution_id},
                            task_id,
                            task_execution_id,
                            None,
                        ],
                        start_to_close_timeout=timedelta(seconds=10),
                        retry_policy=RetryPolicy(maximum_attempts=2),
                    )

                    try:
                        query_text = (next_task.get("description") or "") or (next_task.get("task_name") or "")
                        rag_context = await workflow.execute_activity(
                            retrieve_rag_context_activity,
                            args=[query_text, input.project_id],
                            start_to_close_timeout=timedelta(seconds=60),
                            retry_policy=RetryPolicy(maximum_attempts=2),
                        )
                    except Exception as rag_err:
                        workflow.logger.warning("RAG retrieval failed, continuing without context: %s", rag_err)
                        rag_context = {}

                    try:
                        exec_result = await workflow.execute_activity(
                            execute_task_with_agent_activity,
                            args=[
                                next_task,
                                input.project_id,
                                input.agent_id,
                                input.agent_instance_id,
                                rag_context,
                                workspace_root,
                                input.branch_workflow_run_id,
                                develop_branch_name,
                                input.agent_provider,
                                input.execute_mode,
                                None,
                                None,
                                False,
                            ],
                            start_to_close_timeout=timedelta(minutes=65),
                            retry_policy=RetryPolicy(maximum_attempts=1),
                        )
                    except Exception as exec_err:
                        workflow.logger.error("Task execution failed: %s", exec_err)
                        await workflow.execute_activity(
                            finish_task_execution_activity,
                            args=[
                                task_execution_id,
                                "FAILED",
                                {"error": str(exec_err), "status": "FAILED"},
                                str(exec_err),
                            ],
                            start_to_close_timeout=timedelta(seconds=30),
                            retry_policy=RetryPolicy(maximum_attempts=3),
                        )
                        await workflow.execute_activity(
                            log_task_step_activity,
                            args=[
                                input.project_id,
                                "execute_task_failed",
                                {"error": str(exec_err)},
                                task_id,
                                task_execution_id,
                                None,
                            ],
                            start_to_close_timeout=timedelta(seconds=10),
                            retry_policy=RetryPolicy(maximum_attempts=2),
                        )
                        raise

                    # Decommission the per-task Cursor agent once execution is complete
                    cursor_agent_id = exec_result.get("cursor_agent_id")
                    if cursor_agent_id:
                        try:
                            await workflow.execute_activity(
                                decommission_cursor_agent_activity,
                                args=[cursor_agent_id],
                                start_to_close_timeout=timedelta(seconds=30),
                                retry_policy=RetryPolicy(maximum_attempts=3),
                            )
                        except Exception as dec_err:
                            workflow.logger.warning(
                                "Failed to decommission Cursor agent %s from workflow: %s",
                                cursor_agent_id,
                                dec_err,
                            )

                    # If branching is enabled for this run and human review is not required,
                    # merge the task branch back into the workflow's develop branch.
                    task_branch_name = exec_result.get("task_branch_name")
                    if (
                        input.branch_workflow_run_id is not None
                        and develop_branch_name
                        and task_branch_name
                        and not input.require_human_review
                    ):
                        try:
                            await workflow.execute_activity(
                                merge_task_branch_into_develop_activity,
                                args=[
                                    input.branch_workflow_run_id,
                                    task_branch_name,
                                    develop_branch_name,
                                    input.require_human_review,
                                ],
                                start_to_close_timeout=timedelta(minutes=5),
                                retry_policy=RetryPolicy(maximum_attempts=3),
                            )
                        except Exception as merge_err:
                            workflow.logger.warning(
                                "Failed to merge task branch %s into %s: %s",
                                task_branch_name,
                                develop_branch_name,
                                merge_err,
                            )

                    await workflow.execute_activity(
                        log_task_step_activity,
                        args=[
                            input.project_id,
                            "execute_task",
                            {"status": exec_result.get("status"), "cursor_agent_id": exec_result.get("cursor_agent_id")},
                            task_id,
                            task_execution_id,
                            None,
                        ],
                        start_to_close_timeout=timedelta(seconds=10),
                        retry_policy=RetryPolicy(maximum_attempts=2),
                    )

                    try:
                        await workflow.execute_activity(
                            index_code_context_activity,
                            args=[
                                input.project_id,
                                workspace_root,
                                exec_result.get("files_modified"),
                            ],
                            start_to_close_timeout=timedelta(minutes=10),
                            retry_policy=RetryPolicy(maximum_attempts=2),
                        )
                    except Exception as idx_err:
                        workflow.logger.warning("Index code context failed: %s", idx_err)

                    await workflow.execute_activity(
                        log_task_step_activity,
                        args=[
                            input.project_id,
                            "index_code_context",
                            {},
                            task_id,
                            task_execution_id,
                            None,
                        ],
                        start_to_close_timeout=timedelta(seconds=10),
                        retry_policy=RetryPolicy(maximum_attempts=2),
                    )

                    await workflow.execute_activity(
                        finish_task_execution_activity,
                        args=[
                            task_execution_id,
                            "COMPLETED",
                            exec_result,
                            f"Task {task_id} ({task_name}) completed by Task Executor",
                        ],
                        start_to_close_timeout=timedelta(seconds=30),
                        retry_policy=RetryPolicy(maximum_attempts=3),
                    )

                    await workflow.execute_activity(
                        log_task_step_activity,
                        args=[
                            input.project_id,
                            "finish_task_execution",
                            {"status": "COMPLETED"},
                            task_id,
                            task_execution_id,
                            None,
                        ],
                        start_to_close_timeout=timedelta(seconds=10),
                        retry_policy=RetryPolicy(maximum_attempts=2),
                    )

                    executed_count += 1
            elif (input.agent_provider or "cursor").lower() == "claude-code":
                # Claude Code optimized concurrent path: parallel sessions inside
                # a single activity (avoids child-workflow overhead).
                cc_result = await workflow.execute_activity(
                    execute_tasks_concurrent_claude_code_activity,
                    args=[
                        input.project_id,
                        input.agent_id,
                        input.agent_instance_id,
                        input.max_tasks,
                        workspace_root or None,
                        input.branch_workflow_run_id,
                        develop_branch_name,
                        input.execute_mode,
                        input.require_human_review,
                    ],
                    start_to_close_timeout=timedelta(hours=6),
                    retry_policy=RetryPolicy(maximum_attempts=1),
                )
                executed_count = int(cc_result.get("tasks_executed", 0))
            else:
                # Concurrent mode (cursor/codex): start a child workflow per task.
                child_handles = []
                while executed_count < input.max_tasks:
                    next_task: Optional[Dict[str, Any]] = await workflow.execute_activity(
                        get_next_ready_task_activity,
                        args=[input.project_id, input.branch_workflow_run_id],
                        start_to_close_timeout=timedelta(seconds=15),
                        retry_policy=RetryPolicy(maximum_attempts=3),
                    )

                    await workflow.execute_activity(
                        log_task_step_activity,
                        args=[
                            input.project_id,
                            "next_task_fetched",
                            {"task_id": next_task.get("task_id") if next_task else None, "has_task": next_task is not None},
                            next_task.get("task_id") if next_task else None,
                            None,
                            None,
                        ],
                        start_to_close_timeout=timedelta(seconds=10),
                        retry_policy=RetryPolicy(maximum_attempts=2),
                    )

                    if not next_task or not next_task.get("task_id"):
                        workflow.logger.info(
                            "No more ready tasks for project_id=%s (concurrent mode)", input.project_id
                        )
                        break

                    # Start a child workflow to execute this task
                    handle = await workflow.start_child_workflow(
                        SingleTaskExecutionWorkflow.run,
                        SingleTaskExecutionInput(
                            task=next_task,
                            project_id=input.project_id,
                            agent_id=input.agent_id,
                            agent_instance_id=input.agent_instance_id,
                            workspace_root=workspace_root or None,
                            branch_workflow_run_id=input.branch_workflow_run_id,
                            agent_provider=input.agent_provider,
                            require_human_review=input.require_human_review,
                            execute_mode=input.execute_mode,
                        ),
                        id=f"task-exec-single-{input.project_id}-{next_task.get('task_id')}-{workflow.info().run_id}",
                        task_queue="task-execution-queue",
                        execution_timeout=timedelta(hours=2),
                    )
                    child_handles.append(handle)
                    executed_count += 1

                # Wait for all child workflows to complete
                for h in child_handles:
                    try:
                        await h.result()
                    except Exception as child_err:
                        workflow.logger.error(
                            "Child SingleTaskExecutionWorkflow failed: %s", child_err
                        )

            result = TaskExecutionResult(
                project_id=input.project_id,
                tasks_executed=executed_count,
                workflow_run_id=workflow_run_id,
            )
            if workflow_run_id is not None:
                await workflow.execute_activity(
                    finish_workflow_run_activity,
                    args=[workflow_run_id, "COMPLETED", asdict(result)],
                    start_to_close_timeout=timedelta(seconds=15),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
            return result
        except Exception as e:
            if workflow_run_id is not None:
                try:
                    await workflow.execute_activity(
                        finish_workflow_run_activity,
                        args=[
                            workflow_run_id,
                            "FAILED",
                            {"error": str(e), "tasks_executed": executed_count},
                        ],
                        start_to_close_timeout=timedelta(seconds=15),
                        retry_policy=RetryPolicy(maximum_attempts=3),
                    )
                except Exception:
                    pass
            raise
