"""Task execution related Temporal activities."""
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from temporalio import activity

from temporal.utils.db import execute_function, get_connection
from temporal.utils.activity_run import track_activity

logger = logging.getLogger(__name__)


def _log_task_step_impl(
    project_id: int,
    step_name: str,
    summary: Dict[str, Any],
    task_id: Optional[int] = None,
    task_execution_id: Optional[int] = None,
    activity_run_id: Optional[int] = None,
) -> None:
    """Log a task execution step (shared with batch runner)."""
        payload = {
            "step_name": step_name,
            "task_id": task_id,
            "task_execution_id": task_execution_id,
            "activity_run_id": activity_run_id,
            **summary,
        }
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO main.event_log (
                        entity_type,
                        entity_id,
                        project_id,
                        event_type,
                        payload,
                        created_by
                    )
                    VALUES (%s, %s, %s, %s, %s::jsonb, %s)
                    """,
                    (
                        "TASK_EXECUTION",
                        task_execution_id,
                        project_id,
                        "TASK_STEP_LOGGED",
                        json.dumps(payload),
                        "system",
                    ),
                )
        logger.info(
            "Logged task step project_id=%s step_name=%s task_execution_id=%s",
            project_id,
            step_name,
            task_execution_id,
    )


@activity.defn
@track_activity
async def log_task_step_activity(
    project_id: int,
    step_name: str,
    summary: Dict[str, Any],
    task_id: Optional[int] = None,
    task_execution_id: Optional[int] = None,
    activity_run_id: Optional[int] = None,
) -> None:
    """
    Log a task execution step to main.event_log for traceability.
    Call this after every other activity in the task execution loop.
    """
    try:
        _log_task_step_impl(
            project_id,
            step_name,
            summary,
            task_id,
            task_execution_id,
            activity_run_id,
        )
    except Exception as e:
        import traceback
        logger.error("Error logging task step: %s", e)
        logger.error("Full traceback:\n%s", traceback.format_exc())
        raise


# Code file extensions to index for RAG context
_CODE_EXTENSIONS = frozenset(
    (".py", ".ts", ".tsx", ".js", ".jsx", ".sql", ".md", ".json", ".yml", ".yaml", ".html", ".css", ".sh", ".bat")
)
_SKIP_DIRS = frozenset((".git", "node_modules", "__pycache__", "venv", ".venv", "dist", "build", ".cursor"))


@activity.defn
@track_activity
async def index_code_context_activity(
    project_id: int,
    workspace_root: str,
    file_paths: Optional[list] = None,
    max_files: int = 500,
) -> Dict[str, Any]:
    """
    Index code files into document_chunk/document_embedding for RAG context.
    Uses fn_get_or_create_code_document(project_id) for a stable document_id.
    If file_paths is provided, only those files are indexed; else scans workspace_root.
    """
    import os
    from pathlib import Path

    from temporal.utils.chunking import chunk_document
    from temporal.utils.embeddings import generate_embedding
    from temporal.config import config

    try:
        document_id = execute_function("main.fn_get_or_create_code_document", (project_id,))
        if document_id is None:
            raise RuntimeError("fn_get_or_create_code_document returned None")
        document_id = int(document_id)

        root = Path(workspace_root).resolve()
        if not root.is_dir():
            logger.warning("Workspace root %s is not a directory, skipping index", workspace_root)
            return {"document_id": document_id, "files_indexed": 0, "chunks_stored": 0}

        if file_paths:
            paths = []
            for p in file_paths:
                path = Path(p)
                if not path.is_absolute():
                    path = root / path
                if path.exists() and path.is_file():
                    paths.append(path)
        else:
            paths = []
            for dirpath, _dirnames, filenames in os.walk(root, topdown=True):
                _dirnames[:] = [d for d in _dirnames if d not in _SKIP_DIRS]
                for name in filenames:
                    if Path(name).suffix.lower() in _CODE_EXTENSIONS:
                        paths.append(Path(dirpath) / name)
                        if len(paths) >= max_files:
                            break
                if len(paths) >= max_files:
                    break

        files_indexed = 0
        chunks_stored = 0

        with get_connection() as conn:
            for path in paths:
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except Exception as e:
                    logger.debug("Skip file %s: %s", path, e)
                    continue

                try:
                    rel_path = str(path.relative_to(root))
                except ValueError:
                    rel_path = os.path.relpath(str(path), str(root))
                doc_meta = {"document_name": "__codebase__", "document_type": "code", "file_path": rel_path}
                chunks = chunk_document(
                    text,
                    document_id,
                    project_id,
                    chunk_size=800,
                    chunk_overlap=100,
                    document_metadata=doc_meta,
                )
                if not chunks:
                    continue

                for c in chunks:
                    c["chunk_metadata"] = c.get("chunk_metadata") or {}
                    c["chunk_metadata"]["file_path"] = rel_path

                # Delete existing chunks for this document_id + file_path
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT chunk_id FROM main.document_chunk
                        WHERE document_id = %s AND chunk_metadata->>'file_path' = %s
                        """,
                        (document_id, rel_path),
                    )
                    old_ids = [row[0] for row in cur.fetchall()]
                    if old_ids:
                        cur.execute(
                            "DELETE FROM main.document_embedding WHERE chunk_id = ANY(%s)",
                            (old_ids,),
                        )
                        cur.execute(
                            "DELETE FROM main.document_chunk WHERE chunk_id = ANY(%s)",
                            (old_ids,),
                        )

                # Insert new chunks and embeddings
                for idx, chunk in enumerate(chunks):
                    chunk["chunk_index"] = idx
                    emb = generate_embedding(chunk["chunk_text"])
                    emb_str = "[" + ",".join(map(str, emb)) + "]"
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO main.document_chunk
                            (document_id, project_id, chunk_index, chunk_text, chunk_metadata)
                            VALUES (%s, %s, %s, %s, %s::jsonb)
                            RETURNING chunk_id
                            """,
                            (
                                document_id,
                                project_id,
                                chunk["chunk_index"],
                                chunk["chunk_text"],
                                json.dumps(chunk["chunk_metadata"]),
                            ),
                        )
                        row = cur.fetchone()
                        if not row:
                            continue
                        cid = row[0]
                        cur.execute(
                            """
                            INSERT INTO main.document_embedding
                            (chunk_id, document_id, project_id, embedding, embedding_model)
                            VALUES (%s, %s, %s, %s::vector, %s)
                            """,
                            (
                                cid,
                                document_id,
                                project_id,
                                emb_str,
                                config.openai.embedding_model,
                            ),
                        )
                    chunks_stored += 1
                files_indexed += 1
            conn.commit()

        logger.info(
            "index_code_context: project_id=%s document_id=%s files_indexed=%s chunks_stored=%s",
            project_id,
            document_id,
            files_indexed,
            chunks_stored,
        )
        return {
            "document_id": document_id,
            "files_indexed": files_indexed,
            "chunks_stored": chunks_stored,
        }
    except Exception as e:
        import traceback
        logger.error("Error indexing code context: %s", e)
        logger.error("Full traceback:\n%s", traceback.format_exc())
        raise


@activity.defn
@track_activity
async def ensure_workflow_develop_branch_activity(workflow_run_id: int) -> Dict[str, Any]:
    """
    Ensure that a per-workflow develop branch exists for the given workflow_run_id.

    When configuration is available, this uses the GitHub API to create a branch
    named "develop-{workflow_run_id}" from the configured default branch if it
    does not already exist.
    """
    import os
    from urllib.parse import urlparse
    import httpx

    from temporal.config import config

    repository_url = getattr(config.cursor_api, "repository_url", None)
    default_branch = getattr(config.cursor_api, "default_branch", "main")
    develop_branch = f"develop-{workflow_run_id}"

    if not repository_url:
        logger.warning(
            "ensure_workflow_develop_branch_activity: repository_url not configured; "
            "skipping branch ensure for workflow_run_id=%s",
            workflow_run_id,
        )
        return {"ensured": False, "reason": "no_repository_config"}

    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        logger.warning(
            "ensure_workflow_develop_branch_activity: GITHUB_TOKEN not set; "
            "skipping branch ensure for workflow_run_id=%s",
            workflow_run_id,
        )
        return {"ensured": False, "reason": "no_github_token"}

    parsed = urlparse(repository_url)
    path_parts = parsed.path.strip("/").split("/")
    if len(path_parts) < 2:
        raise ValueError(f"Unable to parse owner/repo from repository_url={repository_url}")
    owner, repo = path_parts[0], path_parts[1]

    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
    }

    api_base = "https://api.github.com"
    async with httpx.AsyncClient() as client:
        # Check if the develop branch already exists
        branch_url = f"{api_base}/repos/{owner}/{repo}/branches/{develop_branch}"
        resp = await client.get(branch_url, headers=headers, timeout=30.0)
        if resp.status_code == 200:
            logger.info(
                "Develop branch %s already exists for repo %s/%s",
                develop_branch,
                owner,
                repo,
            )
            return {"ensured": True, "already_existed": True, "branch": develop_branch}
        if resp.status_code not in (404,):
            resp.raise_for_status()

        # Look up the default branch's commit SHA
        default_branch_url = f"{api_base}/repos/{owner}/{repo}/branches/{default_branch}"
        resp = await client.get(default_branch_url, headers=headers, timeout=30.0)
        resp.raise_for_status()
        default_data = resp.json()
        sha = (default_data.get("commit") or {}).get("sha")
        if not sha:
            raise RuntimeError(
                f"Could not determine SHA for default branch {default_branch} in {owner}/{repo}"
            )

        # Create the new develop branch
        create_ref_url = f"{api_base}/repos/{owner}/{repo}/git/refs"
        payload = {"ref": f"refs/heads/{develop_branch}", "sha": sha}
        resp = await client.post(create_ref_url, headers=headers, json=payload, timeout=30.0)
        resp.raise_for_status()
        logger.info(
            "Created develop branch %s from %s for repo %s/%s",
            develop_branch,
            default_branch,
            owner,
            repo,
        )
        return {"ensured": True, "created": True, "branch": develop_branch}


@activity.defn
@track_activity
async def merge_task_branch_into_develop_activity(
    workflow_run_id: int,
    task_branch_name: str,
    develop_branch: str,
    require_human_review: bool,
) -> Dict[str, Any]:
    """
    Create a GitHub pull request from the task branch into the workflow's
    develop branch and optionally auto-merge it.
    
    When require_human_review is True, this activity creates the PR but does
    not merge it, leaving it for manual review.
    """
    import os
    from urllib.parse import urlparse
    import httpx
    
    from temporal.config import config
    
    repository_url = getattr(config.cursor_api, "repository_url", None)
    if not repository_url:
        logger.warning(
            "merge_task_branch_into_develop_activity: repository_url not configured; "
            "skipping PR creation for %s -> %s (workflow_run_id=%s)",
            task_branch_name,
            develop_branch,
            workflow_run_id,
        )
        return {"merged": False, "reason": "no_repository_config"}
    
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        logger.warning(
            "merge_task_branch_into_develop_activity: GITHUB_TOKEN not set; "
            "skipping PR creation for %s -> %s (workflow_run_id=%s)",
            task_branch_name,
            develop_branch,
            workflow_run_id,
        )
        return {"merged": False, "reason": "no_github_token"}
    
    parsed = urlparse(repository_url)
    path_parts = parsed.path.strip("/").split("/")
    if len(path_parts) < 2:
        raise ValueError(f"Unable to parse owner/repo from repository_url={repository_url}")
    owner, repo = path_parts[0], path_parts[1]
    
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
    }
    
    api_base = "https://api.github.com"
    async with httpx.AsyncClient() as client:
        # 1. Create the pull request
        pr_url = f"{api_base}/repos/{owner}/{repo}/pulls"
        pr_title = f"Workflow {workflow_run_id}: {task_branch_name} -> {develop_branch}"
        pr_body = (
            f"Automated task execution for workflow_run_id={workflow_run_id}.\n\n"
            f"Task branch: `{task_branch_name}`\n"
            f"Target develop branch: `{develop_branch}`\n"
        )
        pr_payload = {
            "title": pr_title,
            "head": task_branch_name,
            "base": develop_branch,
            "body": pr_body,
        }
        resp = await client.post(pr_url, headers=headers, json=pr_payload, timeout=60.0)
        resp.raise_for_status()
        pr_data = resp.json()
        number = pr_data.get("number")
        html_url = pr_data.get("html_url")
        logger.info(
            "Created PR #%s (%s) from %s to %s for workflow_run_id=%s",
            number,
            html_url,
            task_branch_name,
            develop_branch,
            workflow_run_id,
        )
        
        # 2. Optionally auto-merge the PR
        if require_human_review:
            logger.info(
                "merge_task_branch_into_develop_activity: require_human_review=True; "
                "leaving PR #%s open for manual review (workflow_run_id=%s)",
                number,
                workflow_run_id,
            )
            return {
                "merged": False,
                "reason": "human_review_required",
                "task_branch": task_branch_name,
                "develop_branch": develop_branch,
                "pr_number": number,
                "pr_url": html_url,
            }
        
        merge_url = f"{api_base}/repos/{owner}/{repo}/pulls/{number}/merge"
        merge_payload = {
            "commit_title": f"Auto-merge PR #{number} for workflow_run_id={workflow_run_id}",
            # default merge method; could be configured if needed
        }
        resp = await client.put(merge_url, headers=headers, json=merge_payload, timeout=60.0)
        if resp.status_code == 409:
            logger.warning(
                "Merge conflict when auto-merging PR #%s (%s) for workflow_run_id=%s",
                number,
                html_url,
                workflow_run_id,
            )
            return {
                "merged": False,
                "reason": "conflict",
                "task_branch": task_branch_name,
                "develop_branch": develop_branch,
                "pr_number": number,
                "pr_url": html_url,
            }
        resp.raise_for_status()
        logger.info(
            "Successfully auto-merged PR #%s (%s) for workflow_run_id=%s",
            number,
            html_url,
            workflow_run_id,
        )
        return {
            "merged": True,
            "task_branch": task_branch_name,
            "develop_branch": develop_branch,
            "pr_number": number,
            "pr_url": html_url,
        }


def _peek_ready_tasks_impl(
    project_id: int,
    workflow_run_id: Optional[int],
    limit: int,
) -> list:
    """
    Snapshot of up to `limit` next ready tasks (same order as get-next).
    Requires DB function main.fn_peek_ready_tasks (see schema).
    """
    import json

    try:
        raw = execute_function(
            "main.fn_peek_ready_tasks",
            (project_id, workflow_run_id, limit),
        )
    except Exception as e:
        logger.warning(
            "fn_peek_ready_tasks failed (apply migration if missing): %s",
            e,
        )
        return []
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _get_next_ready_task_impl(
    project_id: int,
    workflow_run_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Fetch the next ready task (shared by activity and batch execution)."""
        result = execute_function(
            "main.fn_get_next_ready_task",
            (project_id, workflow_run_id),
        )
        if result is None:
            logger.info("No ready tasks found for project_id=%s", project_id)
            return None
        logger.info(
            "Next ready task for project_id=%s is task_id=%s",
            project_id,
            result.get("task_id"),
        )
        return result


@activity.defn
@track_activity
async def get_next_ready_task_activity(
    project_id: int,
    workflow_run_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """
    Fetch the next ready task for a project using fn_get_next_ready_task.
    """
    try:
        return _get_next_ready_task_impl(project_id, workflow_run_id)
    except Exception as e:
        import traceback
        logger.error("Error fetching next ready task: %s", e)
        logger.error("Full traceback:\n%s", traceback.format_exc())
        raise


def _start_task_execution_impl(
    task_id: int,
    agent_id: int,
    agent_instance_id: int,
) -> int:
    """Start a task execution and return task_execution_id (shared with batch runner)."""
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CALL main.sp_start_task_execution(
                        %s,
                        %s,
                        %s,
                        %s
                    )
                    """,
                    (task_id, agent_id, agent_instance_id, "system"),
                )
                cur.execute(
                    """
                    SELECT task_execution_id
                    FROM main.task_execution
                    WHERE task_id = %s
                    ORDER BY started_at DESC
                    LIMIT 1
                    """,
                    (task_id,),
                )
                row = cur.fetchone()
                if not row:
                    raise RuntimeError(
                        "Task execution row not found after sp_start_task_execution"
                    )
                task_execution_id = row[0]
    logger.info("Started task_execution_id=%s for task_id=%s", task_execution_id, task_id)
        return int(task_execution_id)


@activity.defn
@track_activity
async def start_task_execution_activity(
    task_id: int,
    agent_id: int,
    agent_instance_id: int,
) -> int:
    """
    Start a task execution and return task_execution_id.
    """
    try:
        return _start_task_execution_impl(task_id, agent_id, agent_instance_id)
    except Exception as e:
        import traceback
        logger.error("Error starting task execution: %s", e)
        logger.error("Full traceback:\n%s", traceback.format_exc())
        raise


def _finish_task_execution_impl(
    task_execution_id: int,
    status: str,
    result_json: Dict[str, Any],
    logs_text: str = "",
) -> None:
    """Finish a task execution (shared with batch runner)."""
    import json

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CALL main.sp_finish_task_execution(
                        %s,
                        %s,
                        %s::jsonb,
                        %s,
                        %s
                    )
                    """,
                    (
                        task_execution_id,
                        status,
                        json.dumps(result_json),
                        logs_text,
                        "system",
                    ),
                )
        logger.info(
            "Finished task_execution_id=%s with status=%s",
            task_execution_id,
            status,
        )


@activity.defn
@track_activity
async def finish_task_execution_activity(
    task_execution_id: int,
    status: str,
    result_json: Dict[str, Any],
    logs_text: str = "",
) -> None:
    """
    Finish a task execution by updating status, result, and logs.
    """
    try:
        _finish_task_execution_impl(task_execution_id, status, result_json, logs_text)
    except Exception as e:
        import traceback
        logger.error("Error finishing task execution: %s", e)
        logger.error("Full traceback:\n%s", traceback.format_exc())
        raise


def _build_task_executor_prompt(
    task: Dict[str, Any],
    rag_context: Dict[str, Any],
    workspace_root: Optional[str] = None,
) -> str:
    """Build the prompt for the Task Executor (Cursor) agent, biased toward implementation."""
    task_name = task.get("task_name") or "Unnamed task"
    description = task.get("description") or ""
    task_data = task.get("task_data") or {}
    task_notes = task.get("task_notes") or ""
    constraints = task_data.get("constraints") or []
    success_criteria = task_data.get("success_criteria") or []
    deps = task_data.get("dependencies") or []

    sections = [
        (
            "You are the Task Executor. Execute the following single task by making concrete, "
            "technical changes to the codebase (source files, configuration, tests, and in-repo "
            "documentation), not high-level plans or strategy documents."
        ),
        "",
        f"TASK: {task_name}",
        "",
        "DESCRIPTION:",
        description,
        "",
    ]
    if task_notes:
        sections.extend(["NOTES:", task_notes, ""])
    if constraints:
        sections.extend(["CONSTRAINTS:", "\n".join(f"- {c}" for c in constraints), ""])
    if success_criteria:
        sections.extend(
            ["SUCCESS CRITERIA:", "\n".join(f"- {s}" for s in success_criteria), ""]
        )
    if deps:
        sections.extend(
            ["DEPENDENCIES (already done):", ", ".join(deps), ""]
        )
    if workspace_root:
        sections.extend(
            [
                f"WORKSPACE ROOT: {workspace_root}",
                "",
                "You have direct access to this workspace. Prefer implementing or updating code, "
                "types, API clients, CLI commands, configuration, and tests that satisfy the task.",
                "",
            ]
        )

    results = (rag_context or {}).get("results") or []
    if results:
        sections.append(
            "RELEVANT CONTEXT (requirements and/or existing code). Use this context to drive "
            "your implementation decisions and to locate the right places in the codebase to edit:"
        )
        for i, chunk in enumerate(results[:15]):
            text = chunk.get("chunk_text") or chunk.get("text") or str(chunk)
            fp = chunk.get("file_path") or chunk.get("chunk_metadata", {}).get("file_path")
            if fp:
                sections.append(f"\n--- {fp} ---\n{text[:2000]}")
            else:
                sections.append(f"\n--- Chunk {i + 1} ---\n{text[:2000]}")
        sections.append("")
    sections.append(
        "Complete this task by implementing or updating code and other in-repo artifacts needed "
        "to satisfy the description and success criteria. Avoid producing purely conceptual plans. "
        "Return a concise summary of the concrete changes you made."
    )
    return "\n".join(sections)


def _slugify_branch_component(value: str, max_length: int = 40) -> str:
    """Create a safe branch-name component from an arbitrary string."""
    import re

    value = value.lower()
    # Replace any sequence of non-alphanumeric characters with '-'
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")
    if not value:
        value = "task"
    if len(value) > max_length:
        value = value[:max_length].rstrip("-")
    return value or "task"


def _build_feature_branch_name(
    workflow_run_id: int,
    task: Dict[str, Any],
    max_slug_length: int = 40,
) -> str:
    """
    Build a feature branch name for a given workflow_run_id and task.

    Pattern: "<workflow_run_id>-<task_name_slug>-<task_id>" (no feature/ prefix).
    """
    task_name = (task.get("task_name") or "task").strip()
    task_id = task.get("task_id")
    slug = _slugify_branch_component(task_name, max_length=max_slug_length)
    if task_id is not None:
        return f"{workflow_run_id}-{slug}-{task_id}"
    return f"{workflow_run_id}-{slug}"


async def _poll_cursor_agent_until_done(
    client: Any,
    api_url: str,
    api_key: str,
    cursor_agent_id: str,
) -> tuple[str, Dict[str, Any]]:
    import asyncio
    import time

    poll_interval = 15
    max_wait_minutes = 60
    max_polls = (max_wait_minutes * 60) // poll_interval
    agent_data_resp: Dict[str, Any] = {}
    started_at = time.time()
    for poll_count in range(max_polls):
        await asyncio.sleep(poll_interval)
        resp = await client.get(
            f"{api_url}/agents/{cursor_agent_id}",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
        if resp.status_code == 404:
            continue
        resp.raise_for_status()
        agent_data_resp = resp.json()
        status = agent_data_resp.get("status", "UNKNOWN")
        logger.info(
            "Cursor agent %s status %s (poll %s/%s)",
            cursor_agent_id,
            status,
            poll_count + 1,
            max_polls,
        )
        if status in ["COMPLETED", "SUCCESS", "DONE", "FINISHED"]:
            break
        if status in ["FAILED", "ERROR", "CANCELLED"]:
            err = agent_data_resp.get("error") or agent_data_resp.get("message", "Unknown")
            raise RuntimeError(f"Cursor agent failed: {err}")
    else:
        raise TimeoutError(
            f"Cursor agent {cursor_agent_id} did not complete within {max_wait_minutes} minutes"
        )

    total_seconds = time.time() - started_at
    logger.info(
        "Cursor agent %s completed with status=%s in %.1fs",
        cursor_agent_id,
        agent_data_resp.get("status", "UNKNOWN"),
        total_seconds,
    )
    return agent_data_resp.get("status", "UNKNOWN"), agent_data_resp


async def _async_execute_cursor_task(
    task: Dict[str, Any],
    project_id: int,
    agent_id: int,
    agent_instance_id: int,
    rag_context: Dict[str, Any],
    workspace_root: Optional[str],
    workflow_run_id: Optional[int],
    develop_branch: Optional[str],
    model: Optional[str] = None,
    follow_up_agent_id: Optional[str] = None,
    skip_decommission: bool = False,
) -> Dict[str, Any]:
    """
    Core Cursor task execution (create or follow-up). Shared by activity and batch runner.
    """
    import httpx

    from temporal.config import config

    if follow_up_agent_id and workflow_run_id is not None:
        raise ValueError(
            "Cursor follow-up cannot be used with per-workflow task branches (branch_workflow_run_id set)"
        )

    if not config.cursor_api.api_key:
        raise ValueError("Cursor API key not configured")

    prompt = _build_task_executor_prompt(task, rag_context, workspace_root)

    api_url = config.cursor_api.api_url
    api_key = config.cursor_api.api_key
    repository_url = getattr(config.cursor_api, "repository_url", None)
    chosen_task_branch: Optional[str] = None

    async with httpx.AsyncClient() as client:
        if follow_up_agent_id:
            logger.info(
                "Follow-up Cursor agent %s for task_id=%s",
                follow_up_agent_id,
                task.get("task_id"),
            )
            response = await client.post(
                f"{api_url}/agents/{follow_up_agent_id}/followup",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={"prompt": {"text": prompt}},
                timeout=30.0,
            )
            response.raise_for_status()
            cursor_agent_id = follow_up_agent_id
        else:
            prompt_body: Dict[str, Any] = {"text": prompt}
            if model and str(model).strip() and str(model).strip().lower() != "default":
                prompt_body["model"] = model.strip()
            request_body: Dict[str, Any] = {"prompt": prompt_body}

    if workflow_run_id is not None:
        chosen_task_branch = _build_feature_branch_name(workflow_run_id, task)
        request_body.setdefault("target", {})
        request_body["target"]["branchName"] = chosen_task_branch

    if repository_url:
        if develop_branch:
            request_body["source"] = {
                "repository": repository_url,
                "ref": develop_branch,
            }
        else:
            request_body["source"] = {
                "repository": repository_url,
            }

            logger.info(
                "Creating Cursor task executor agent for task_id=%s workflow_run_id=%s "
                "develop_branch=%s task_branch=%s model=%s",
                task.get("task_id"),
                workflow_run_id,
                develop_branch,
                chosen_task_branch,
                model,
            )
            response = await client.post(
                f"{api_url}/agents",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=request_body,
                timeout=30.0,
            )
            response.raise_for_status()
            result = response.json()
            cursor_agent_id = result.get("id")
            if not cursor_agent_id:
                raise RuntimeError("Cursor API did not return agent id")

            logger.info("Created Cursor agent %s for task_id=%s", cursor_agent_id, task.get("task_id"))

            if not follow_up_agent_id:
            try:
                with get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO main.event_log (
                                entity_type, entity_id, project_id, event_type, payload, created_by
                            )
                            VALUES (
                                'CURSOR_AGENT',
                                %s,
                                %s,
                                'CURSOR_AGENT_CREATED',
                                jsonb_build_object(
                                    'provider', 'cursor',
                                    'db_agent_id', %s,
                                    'agent_instance_id', %s,
                                    'cursor_agent_id', %s,
                                    'task_id', %s,
                                    'task_name', %s,
                                    'timestamp', now()
                                ),
                                'system'
                            )
                            """,
                            (
                                agent_id,
                                project_id,
                                agent_id,
                                agent_instance_id,
                                cursor_agent_id,
                                task.get("task_id"),
                                task.get("task_name"),
                            ),
                        )
            except Exception as log_err:
                logger.warning("Failed to log CURSOR_AGENT_CREATED: %s", log_err)

        status, agent_data_resp = await _poll_cursor_agent_until_done(
            client, api_url, api_key, cursor_agent_id
            )

            results = (
                agent_data_resp.get("results")
                or agent_data_resp.get("output")
                or agent_data_resp.get("artifacts")
            )
            result_summary = str(results)[:2000] if results else status
            files_modified: list[str] = []
            if isinstance(results, list):
                for item in results:
                    if isinstance(item, dict) and item.get("path"):
                        files_modified.append(item.get("path"))
            elif isinstance(results, dict) and results.get("files"):
                files_modified = list(results.get("files", []))

            target_info = agent_data_resp.get("target") or {}
            actual_branch_name = target_info.get("branchName") or chosen_task_branch

            try:
                with get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO main.event_log (
                                entity_type, entity_id, project_id, event_type, payload, created_by
                            )
                            VALUES (
                                'CURSOR_AGENT',
                                NULL,
                                %s,
                                'CURSOR_AGENT_COMPLETED',
                                jsonb_build_object(
                                    'provider', 'cursor',
                                    'cursor_agent_id', %s,
                                    'status', %s,
                                    'task_id', %s,
                                    'result_summary', %s,
                                    'files_modified', %s,
                                    'task_branch_name', %s,
                                    'timestamp', now()
                                ),
                                'system'
                            )
                            """,
                            (
                                project_id,
                                cursor_agent_id,
                                status,
                                task.get("task_id"),
                                result_summary[:500],
                                json.dumps(files_modified),
                                actual_branch_name,
                            ),
                        )
            except Exception as log_err:
                logger.warning("Failed to log CURSOR_AGENT_COMPLETED: %s", log_err)

            result_payload = {
                "status": status,
                "cursor_agent_id": cursor_agent_id,
                "result_summary": result_summary,
                "files_modified": files_modified,
                "task_branch_name": actual_branch_name,
            }

        if not skip_decommission:
            try:
                from temporal.activities.api_activities import _decommission_cursor_agent

                await _decommission_cursor_agent(cursor_agent_id)
            except Exception as dec_err:
                logger.warning(
                    "Failed to decommission task-executor Cursor agent %s: %s",
                    cursor_agent_id,
                    dec_err,
                )

            return result_payload


@activity.defn
@track_activity
async def execute_task_with_cursor_activity(
    task: Dict[str, Any],
    project_id: int,
    agent_id: int,
    agent_instance_id: int,
    rag_context: Dict[str, Any],
    workspace_root: Optional[str] = None,
    workflow_run_id: Optional[int] = None,
    develop_branch: Optional[str] = None,
    model: Optional[str] = None,
    follow_up_agent_id: Optional[str] = None,
    skip_decommission: bool = False,
) -> Dict[str, Any]:
    """
    Execute a single task using the Cursor API (Task Executor agent).
    Builds prompt from task + RAG context, creates Cursor agent, polls until done.
    Returns result dict for task_execution_result (status, cursor_agent_id, result_summary, files_modified).
    """
    try:
        return await _async_execute_cursor_task(
            task,
            project_id,
            agent_id,
            agent_instance_id,
            rag_context,
            workspace_root,
            workflow_run_id,
            develop_branch,
            model,
            follow_up_agent_id,
            skip_decommission,
        )
    except Exception as e:
        import traceback

        logger.error("Error in execute_task_with_cursor_activity: %s", e)
        logger.error("Full traceback:\n%s", traceback.format_exc())
        raise


async def _execute_task_with_codex_agent(
    task: Dict[str, Any],
    project_id: int,
    agent_id: int,
    agent_instance_id: int,
    rag_context: Dict[str, Any],
    workspace_root: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute a single task using a Codex/OpenAI-based agent.

    This implementation focuses on returning an implementation-focused summary of
    the work that should be done. It does not directly modify the repository; it
    is intended primarily for diagnosing latency differences between providers.
    """
    import httpx
    from temporal.config import config

    # Prefer explicit Codex API key, fall back to general OpenAI key
    api_key = config.codex_api.api_key or config.openai.api_key
    if not api_key:
        raise ValueError("Codex/OpenAI API key not configured")

    api_url = config.codex_api.api_url.rstrip("/")
    resolved_model = (model or "").strip() or config.codex_api.model

    prompt = _build_task_executor_prompt(task, rag_context, workspace_root)

    system_msg = (
        "You are a senior software engineer acting as a task executor. "
        "Given the task description and context, produce a precise, "
        "implementation-focused description of the code changes that should be made "
        "to complete the task (files, functions, signatures, and example snippets), "
        "without actually applying them."
    )

    request_body: Dict[str, Any] = {
        "model": resolved_model,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{api_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=request_body,
            timeout=180.0,
        )
        resp.raise_for_status()
        data = resp.json()

    choices = data.get("choices") or []
    content = ""
    if choices:
        message = choices[0].get("message") or {}
        content = message.get("content") or ""

    status = "COMPLETED"
    result_summary = content[:2000] if content else status

    return {
        "status": status,
        "cursor_agent_id": None,
        "result_summary": result_summary,
        "files_modified": [],
        "task_branch_name": None,
    }


async def _execute_task_with_claude_code(
    task: Dict[str, Any],
    project_id: int,
    agent_id: int,
    agent_instance_id: int,
    rag_context: Dict[str, Any],
    workspace_root: Optional[str] = None,
    model: Optional[str] = None,
    session_id_resume: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute a single task using Claude Code via the claude-agent-sdk.

    Unlike Cursor (cloud API + polling) or Codex (chat completions only), Claude
    Code runs a full agentic loop locally: it can read, edit, and create files,
    run shell commands, and manage git -- all within the worker's filesystem.

    When *session_id_resume* is provided the SDK resumes an existing session
    (used by batch mode to accumulate context across tasks).
    """
    from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage, AssistantMessage, TextBlock
    from temporal.config import config

    if not config.claude_code.api_key:
        raise ValueError(
            "Claude Code API key not configured (set ANTHROPIC_API_KEY)"
        )

    prompt = _build_task_executor_prompt(task, rag_context, workspace_root)
    resolved_model = (model or "").strip() or config.claude_code.model
    cwd = workspace_root or None

    opts = ClaudeAgentOptions(
        model=resolved_model,
        cwd=cwd,
        permission_mode=config.claude_code.permission_mode,
        allowed_tools=["Read", "Edit", "Write", "Glob", "Grep", "Bash"],
        max_turns=config.claude_code.max_turns,
    )
    if session_id_resume:
        opts.resume = session_id_resume

    # Ensure the subprocess does not think it is running inside another Claude
    # Code session (known SDK issue with CLAUDECODE env var inheritance).
    if not hasattr(opts, "env") or opts.env is None:
        opts.env = {}
    opts.env["CLAUDECODE"] = ""

    result_text_parts: list[str] = []
    session_id: Optional[str] = None
    total_cost: Optional[float] = None
    files_modified: list[str] = []

    async for message in query(prompt=prompt, options=opts):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    result_text_parts.append(block.text)
                elif hasattr(block, "name") and hasattr(block, "input"):
                    # ToolUseBlock -- capture file paths from Edit/Write calls
                    if block.name in ("Edit", "Write") and isinstance(block.input, dict):
                        fp = block.input.get("file_path") or block.input.get("path")
                        if fp and fp not in files_modified:
                            files_modified.append(fp)
        elif isinstance(message, ResultMessage):
            session_id = getattr(message, "session_id", None)
            total_cost = getattr(message, "total_cost_usd", None)

    result_summary = "\n".join(result_text_parts)[:2000] or "COMPLETED"

    logger.info(
        "Claude Code session completed: session_id=%s cost=$%s files_modified=%d task_id=%s",
        session_id,
        f"{total_cost:.4f}" if total_cost is not None else "N/A",
        len(files_modified),
        task.get("task_id"),
    )

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO main.event_log (
                        entity_type, entity_id, project_id, event_type, payload, created_by
                    )
                    VALUES (
                        'CLAUDE_CODE_SESSION',
                        %s,
                        %s,
                        'CLAUDE_CODE_SESSION_COMPLETED',
                        jsonb_build_object(
                            'provider', 'claude-code',
                            'session_id', %s,
                            'model', %s,
                            'total_cost_usd', %s,
                            'task_id', %s,
                            'task_name', %s,
                            'files_modified_count', %s,
                            'timestamp', now()
                        ),
                        'system'
                    )
                    """,
                    (
                        agent_id,
                        project_id,
                        session_id,
                        resolved_model,
                        total_cost,
                        task.get("task_id"),
                        task.get("task_name"),
                        len(files_modified),
                    ),
                )
    except Exception as log_err:
        logger.warning("Failed to log CLAUDE_CODE_SESSION_COMPLETED: %s", log_err)

    return {
        "status": "COMPLETED",
        "cursor_agent_id": session_id,
        "result_summary": result_summary,
        "files_modified": files_modified,
        "task_branch_name": None,
    }


@activity.defn
@track_activity
async def execute_task_with_agent_activity(
    task: Dict[str, Any],
    project_id: int,
    agent_id: int,
    agent_instance_id: int,
    rag_context: Dict[str, Any],
    workspace_root: Optional[str] = None,
    workflow_run_id: Optional[int] = None,
    develop_branch: Optional[str] = None,
    agent_provider: str = "cursor",
    execute_mode: str = "fast",
    model: Optional[str] = None,
    follow_up_agent_id: Optional[str] = None,
    skip_decommission: bool = False,
) -> Dict[str, Any]:
    """
    Provider-agnostic task execution activity.

    Routes execution to either the existing Cursor-based Task Executor agent
    or a Codex/OpenAI-backed agent based on the agent_provider parameter.
    """
    from temporal.utils.model_routing import resolve_executor_model

    resolved: Optional[str] = (
        model.strip()
        if model and str(model).strip()
        else resolve_executor_model(execute_mode, agent_provider, task)
    )
    provider = (agent_provider or "cursor").lower()
    if provider == "codex":
        return await _execute_task_with_codex_agent(
            task,
            project_id,
            agent_id,
            agent_instance_id,
            rag_context,
            workspace_root,
            resolved,
        )
    if provider == "claude-code":
        return await _execute_task_with_claude_code(
            task,
            project_id,
            agent_id,
            agent_instance_id,
            rag_context,
            workspace_root,
            resolved,
            session_id_resume=follow_up_agent_id,
        )
    return await execute_task_with_cursor_activity(
        task,
        project_id,
        agent_id,
        agent_instance_id,
        rag_context,
        workspace_root,
        workflow_run_id,
        develop_branch,
        resolved,
        follow_up_agent_id,
        skip_decommission,
    )


@activity.defn
@track_activity
async def execute_task_batch_activity(
    project_id: int,
    agent_id: int,
    agent_instance_id: int,
    max_tasks: int,
    workspace_root: Optional[str],
    branch_workflow_run_id: Optional[int],
    develop_branch_name: Optional[str],
    agent_provider: str,
    execute_mode: str,
    require_human_review: bool,
) -> Dict[str, Any]:
    """
    Run up to max_tasks ready tasks inside a single activity (reduces Temporal scheduling).

    Provider-specific session reuse:
    * Cursor: follow-up API on the same cloud agent when branch_workflow_run_id is None.
    * Claude Code: ClaudeSDKClient keeps a persistent session across tasks.
    * Codex / others: no session reuse; each task is independent.
    """
    from temporal.activities.document_activities import retrieve_rag_context_impl
    from temporal.activities.api_activities import _decommission_cursor_agent
    from temporal.utils.model_routing import effective_batch_chain_execute_mode

    executed_count = 0
    workspace_root = workspace_root or ""
    provider = (agent_provider or "cursor").lower()
    can_cursor_chain = provider == "cursor" and branch_workflow_run_id is None
    can_claude_code_chain = provider == "claude-code"
    pending_follow_cursor_id: Optional[str] = None

    peeked = _peek_ready_tasks_impl(project_id, branch_workflow_run_id, max_tasks)
    chain_execute_mode = (
        effective_batch_chain_execute_mode(peeked, execute_mode)
        if (can_cursor_chain or can_claude_code_chain)
        else execute_mode
    )
    forced_chain_model: Optional[str] = None
    if can_cursor_chain or can_claude_code_chain:
        from temporal.utils.model_routing import resolve_executor_model

        forced_chain_model = resolve_executor_model(
            chain_execute_mode, agent_provider, None
        )
        if peeked:
            logger.info(
                "Batch follow-up chain (%s): workflow_execute_mode=%s effective_chain_mode=%s "
                "model=%s (single model for all follow-ups)",
                provider,
                execute_mode,
                chain_execute_mode,
                forced_chain_model,
            )

    # Claude Code batch: use ClaudeSDKClient for persistent session reuse
    if can_claude_code_chain:
        return await _execute_batch_claude_code(
            project_id=project_id,
            agent_id=agent_id,
            agent_instance_id=agent_instance_id,
            max_tasks=max_tasks,
            workspace_root=workspace_root,
            branch_workflow_run_id=branch_workflow_run_id,
            develop_branch_name=develop_branch_name,
            execute_mode=chain_execute_mode,
            model=forced_chain_model,
            require_human_review=require_human_review,
        )

    while executed_count < max_tasks:
        next_task = _get_next_ready_task_impl(project_id, branch_workflow_run_id)
        _log_task_step_impl(
            project_id,
            "next_task_fetched",
            {
                "task_id": next_task.get("task_id") if next_task else None,
                "has_task": next_task is not None,
            },
            next_task.get("task_id") if next_task else None,
            None,
            None,
        )

        if not next_task or not next_task.get("task_id"):
            logger.info("Batch: no more ready tasks for project_id=%s", project_id)
            break

        task_id = next_task.get("task_id")
        task_name = next_task.get("task_name")
        logger.info("Batch: starting task_id=%s (%s)", task_id, task_name)

        task_execution_id = _start_task_execution_impl(task_id, agent_id, agent_instance_id)
        _log_task_step_impl(
            project_id,
            "start_task_execution",
            {"task_execution_id": task_execution_id},
            task_id,
            task_execution_id,
            None,
        )

        query_text = (next_task.get("description") or "") or (
            next_task.get("task_name") or ""
        )
        try:
            rag_context = await retrieve_rag_context_impl(query_text, project_id)
        except Exception as rag_err:
            logger.warning("RAG retrieval failed, continuing without context: %s", rag_err)
            rag_context = {}

        try:
            per_task_execute_mode = (
                chain_execute_mode if can_cursor_chain else execute_mode
            )
            model_for_call = forced_chain_model if can_cursor_chain else None
            exec_result = await execute_task_with_agent_activity(
                next_task,
                project_id,
                agent_id,
                agent_instance_id,
                rag_context,
                workspace_root,
                branch_workflow_run_id,
                develop_branch_name,
                agent_provider,
                per_task_execute_mode,
                model_for_call,
                pending_follow_cursor_id if can_cursor_chain else None,
                can_cursor_chain,
            )
        except Exception as exec_err:
            logger.error("Batch task execution failed: %s", exec_err)
            _finish_task_execution_impl(
                task_execution_id,
                "FAILED",
                {"error": str(exec_err), "status": "FAILED"},
                str(exec_err),
            )
            _log_task_step_impl(
                project_id,
                "execute_task_failed",
                {"error": str(exec_err)},
                task_id,
                task_execution_id,
                None,
            )
            if can_cursor_chain and pending_follow_cursor_id:
                try:
                    await _decommission_cursor_agent(pending_follow_cursor_id)
                except Exception:
                    pass
            raise

        cid = exec_result.get("cursor_agent_id")
        if can_cursor_chain and cid:
            pending_follow_cursor_id = cid

        task_branch_name = exec_result.get("task_branch_name")
        if (
            branch_workflow_run_id is not None
            and develop_branch_name
            and task_branch_name
            and not require_human_review
        ):
            try:
                await merge_task_branch_into_develop_activity(
                    branch_workflow_run_id,
                    task_branch_name,
                    develop_branch_name,
                    require_human_review,
                )
            except Exception as merge_err:
                logger.warning(
                    "Failed to merge task branch %s into %s: %s",
                    task_branch_name,
                    develop_branch_name,
                    merge_err,
                )

        _log_task_step_impl(
            project_id,
            "execute_task",
            {
                "status": exec_result.get("status"),
                "cursor_agent_id": exec_result.get("cursor_agent_id"),
            },
            task_id,
            task_execution_id,
            None,
        )

        try:
            await index_code_context_activity(
                project_id,
                workspace_root,
                exec_result.get("files_modified"),
            )
        except Exception as idx_err:
            logger.warning("Index code context failed: %s", idx_err)

        _log_task_step_impl(
            project_id,
            "index_code_context",
            {},
            task_id,
            task_execution_id,
            None,
        )

        _finish_task_execution_impl(
            task_execution_id,
            "COMPLETED",
            exec_result,
            f"Task {task_id} ({task_name}) completed by Task Executor (batch)",
        )
        _log_task_step_impl(
            project_id,
            "finish_task_execution",
            {"status": "COMPLETED"},
            task_id,
            task_execution_id,
            None,
        )

        executed_count += 1

    if can_cursor_chain and pending_follow_cursor_id:
        try:
            await _decommission_cursor_agent(pending_follow_cursor_id)
        except Exception as dec_err:
            logger.warning(
                "Failed to decommission batched Cursor agent %s: %s",
                pending_follow_cursor_id,
                dec_err,
            )

    return {"tasks_executed": executed_count, "project_id": project_id}


# ---------------------------------------------------------------------------
# Claude Code batch: persistent session via ClaudeSDKClient
# ---------------------------------------------------------------------------

async def _execute_batch_claude_code(
    project_id: int,
    agent_id: int,
    agent_instance_id: int,
    max_tasks: int,
    workspace_root: str,
    branch_workflow_run_id: Optional[int],
    develop_branch_name: Optional[str],
    execute_mode: str,
    model: Optional[str],
    require_human_review: bool,
) -> Dict[str, Any]:
    """Run up to *max_tasks* via a single persistent Claude Code session (ClaudeSDKClient)."""
    from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions, ResultMessage, AssistantMessage, TextBlock
    from temporal.activities.document_activities import retrieve_rag_context_impl
    from temporal.config import config

    resolved_model = (model or "").strip() or config.claude_code.model
    cwd = workspace_root or None
    opts = ClaudeAgentOptions(
        model=resolved_model,
        cwd=cwd,
        permission_mode=config.claude_code.permission_mode,
        allowed_tools=["Read", "Edit", "Write", "Glob", "Grep", "Bash"],
        max_turns=config.claude_code.max_turns,
    )
    if not hasattr(opts, "env") or opts.env is None:
        opts.env = {}
    opts.env["CLAUDECODE"] = ""

    executed_count = 0

    async with ClaudeSDKClient(options=opts) as client:
        while executed_count < max_tasks:
            next_task = _get_next_ready_task_impl(project_id, branch_workflow_run_id)
            _log_task_step_impl(
                project_id,
                "next_task_fetched",
                {
                    "task_id": next_task.get("task_id") if next_task else None,
                    "has_task": next_task is not None,
                },
                next_task.get("task_id") if next_task else None,
                None,
                None,
            )

            if not next_task or not next_task.get("task_id"):
                logger.info("Batch (claude-code): no more ready tasks for project_id=%s", project_id)
                break

            task_id = next_task.get("task_id")
            task_name = next_task.get("task_name")
            logger.info("Batch (claude-code): starting task_id=%s (%s)", task_id, task_name)

            task_execution_id = _start_task_execution_impl(task_id, agent_id, agent_instance_id)
            _log_task_step_impl(
                project_id,
                "start_task_execution",
                {"task_execution_id": task_execution_id},
                task_id,
                task_execution_id,
                None,
            )

            query_text = (next_task.get("description") or "") or (next_task.get("task_name") or "")
            try:
                rag_context = await retrieve_rag_context_impl(query_text, project_id)
            except Exception as rag_err:
                logger.warning("RAG retrieval failed, continuing without context: %s", rag_err)
                rag_context = {}

            prompt = _build_task_executor_prompt(next_task, rag_context, workspace_root or None)

            try:
                result_text_parts: list[str] = []
                files_modified: list[str] = []
                session_id: Optional[str] = None
                total_cost: Optional[float] = None

                await client.query(prompt)
                async for message in client.receive_response():
                    if isinstance(message, AssistantMessage):
                        for block in message.content:
                            if isinstance(block, TextBlock):
                                result_text_parts.append(block.text)
                            elif hasattr(block, "name") and hasattr(block, "input"):
                                if block.name in ("Edit", "Write") and isinstance(block.input, dict):
                                    fp = block.input.get("file_path") or block.input.get("path")
                                    if fp and fp not in files_modified:
                                        files_modified.append(fp)
                    elif isinstance(message, ResultMessage):
                        session_id = getattr(message, "session_id", None)
                        total_cost = getattr(message, "total_cost_usd", None)

                result_summary = "\n".join(result_text_parts)[:2000] or "COMPLETED"
                exec_result = {
                    "status": "COMPLETED",
                    "cursor_agent_id": session_id,
                    "result_summary": result_summary,
                    "files_modified": files_modified,
                    "task_branch_name": None,
                }
            except Exception as exec_err:
                logger.error("Batch (claude-code) task execution failed: %s", exec_err)
                _finish_task_execution_impl(
                    task_execution_id,
                    "FAILED",
                    {"error": str(exec_err), "status": "FAILED"},
                    str(exec_err),
                )
                _log_task_step_impl(
                    project_id,
                    "execute_task_failed",
                    {"error": str(exec_err)},
                    task_id,
                    task_execution_id,
                    None,
                )
                raise

            _log_task_step_impl(
                project_id,
                "execute_task",
                {"status": exec_result.get("status"), "cursor_agent_id": session_id},
                task_id,
                task_execution_id,
                None,
            )

            try:
                await index_code_context_activity(
                    project_id,
                    workspace_root,
                    exec_result.get("files_modified"),
                )
            except Exception as idx_err:
                logger.warning("Index code context failed: %s", idx_err)

            _log_task_step_impl(project_id, "index_code_context", {}, task_id, task_execution_id, None)

            _finish_task_execution_impl(
                task_execution_id,
                "COMPLETED",
                exec_result,
                f"Task {task_id} ({task_name}) completed by Claude Code (batch session)",
            )
            _log_task_step_impl(
                project_id,
                "finish_task_execution",
                {"status": "COMPLETED"},
                task_id,
                task_execution_id,
                None,
            )

            executed_count += 1

    return {"tasks_executed": executed_count, "project_id": project_id}


# ---------------------------------------------------------------------------
# Claude Code concurrent: parallel sessions with optional git-worktree isolation
# ---------------------------------------------------------------------------

async def _run_single_claude_code_task(
    task: Dict[str, Any],
    project_id: int,
    agent_id: int,
    agent_instance_id: int,
    workspace_root: str,
    model: Optional[str],
    worktree_path: Optional[str],
) -> Dict[str, Any]:
    """
    Run one task in a Claude Code session.  Used as a unit of work by the
    concurrent activity below.  Returns a dict with task_id, exec_result, and
    optional worktree_path for cleanup.
    """
    from temporal.activities.document_activities import retrieve_rag_context_impl

    task_id = task.get("task_id")
    task_name = task.get("task_name")

    task_execution_id = _start_task_execution_impl(task_id, agent_id, agent_instance_id)
    _log_task_step_impl(
        project_id, "start_task_execution",
        {"task_execution_id": task_execution_id}, task_id, task_execution_id, None,
    )

    query_text = (task.get("description") or "") or (task.get("task_name") or "")
    try:
        rag_context = await retrieve_rag_context_impl(query_text, project_id)
    except Exception:
        rag_context = {}

    cwd = worktree_path or workspace_root or None
    try:
        exec_result = await _execute_task_with_claude_code(
            task, project_id, agent_id, agent_instance_id,
            rag_context, cwd, model,
        )
    except Exception as err:
        _finish_task_execution_impl(
            task_execution_id, "FAILED",
            {"error": str(err), "status": "FAILED"}, str(err),
        )
        _log_task_step_impl(
            project_id, "execute_task_failed", {"error": str(err)},
            task_id, task_execution_id, None,
        )
        return {"task_id": task_id, "status": "FAILED", "error": str(err)}

    _log_task_step_impl(
        project_id, "execute_task",
        {"status": exec_result.get("status"), "cursor_agent_id": exec_result.get("cursor_agent_id")},
        task_id, task_execution_id, None,
    )

    try:
        await index_code_context_activity(project_id, cwd or "", exec_result.get("files_modified"))
    except Exception as idx_err:
        logger.warning("Index code context failed for task_id=%s: %s", task_id, idx_err)

    _log_task_step_impl(project_id, "index_code_context", {}, task_id, task_execution_id, None)

    _finish_task_execution_impl(
        task_execution_id, "COMPLETED", exec_result,
        f"Task {task_id} ({task_name}) completed by Claude Code (concurrent)",
    )
    _log_task_step_impl(
        project_id, "finish_task_execution", {"status": "COMPLETED"},
        task_id, task_execution_id, None,
    )

    return {
        "task_id": task_id,
        "status": "COMPLETED",
        "worktree_path": worktree_path,
        "task_branch_name": exec_result.get("task_branch_name"),
    }


@activity.defn
@track_activity
async def execute_tasks_concurrent_claude_code_activity(
    project_id: int,
    agent_id: int,
    agent_instance_id: int,
    max_tasks: int,
    workspace_root: Optional[str],
    branch_workflow_run_id: Optional[int],
    develop_branch_name: Optional[str],
    execute_mode: str,
    require_human_review: bool,
) -> Dict[str, Any]:
    """
    Execute up to *max_tasks* in parallel Claude Code sessions (one session per
    task).  When *branch_workflow_run_id* is set, each session runs in its own
    git worktree for file-system isolation; otherwise all sessions share the
    workspace root.

    Concurrency is capped by config.claude_code.max_concurrent_sessions.
    """
    import asyncio
    import subprocess
    import shutil
    import tempfile
    from temporal.config import config
    from temporal.utils.model_routing import resolve_executor_model, effective_batch_chain_execute_mode

    workspace_root = workspace_root or ""
    max_concurrent = config.claude_code.max_concurrent_sessions

    # Collect ready tasks up front
    tasks: list[Dict[str, Any]] = []
    while len(tasks) < max_tasks:
        t = _get_next_ready_task_impl(project_id, branch_workflow_run_id)
        if not t or not t.get("task_id"):
            break
        tasks.append(t)

    if not tasks:
        logger.info("Concurrent (claude-code): no ready tasks for project_id=%s", project_id)
        return {"tasks_executed": 0, "project_id": project_id}

    chain_mode = effective_batch_chain_execute_mode(tasks, execute_mode)
    model = resolve_executor_model(chain_mode, "claude-code", None)

    use_worktrees = branch_workflow_run_id is not None and bool(workspace_root)
    worktree_base = tempfile.mkdtemp(prefix="cc_worktrees_") if use_worktrees else None
    worktree_paths: list[str] = []

    # Create git worktrees for isolation when branching is enabled
    if use_worktrees and worktree_base:
        for t in tasks:
            branch_name = _build_feature_branch_name(branch_workflow_run_id, t)
            wt_path = str(Path(worktree_base) / f"task-{t.get('task_id')}")
            try:
                subprocess.run(
                    ["git", "worktree", "add", wt_path, "-b", branch_name],
                    cwd=workspace_root,
                    check=True,
                    capture_output=True,
                    timeout=30,
                )
                worktree_paths.append(wt_path)
            except Exception as wt_err:
                logger.warning(
                    "Failed to create worktree for task_id=%s, will share workspace: %s",
                    t.get("task_id"), wt_err,
                )
                worktree_paths.append("")
    else:
        worktree_paths = [""] * len(tasks)

    # Semaphore to cap parallelism
    sem = asyncio.Semaphore(max_concurrent)

    async def _guarded(task: Dict[str, Any], wt_path: str) -> Dict[str, Any]:
        async with sem:
            return await _run_single_claude_code_task(
                task, project_id, agent_id, agent_instance_id,
                workspace_root, model, wt_path or None,
            )

    results = await asyncio.gather(
        *[_guarded(t, wp) for t, wp in zip(tasks, worktree_paths)],
        return_exceptions=True,
    )

    executed_count = 0
    for r in results:
        if isinstance(r, dict) and r.get("status") == "COMPLETED":
            executed_count += 1
            # Merge task branch if applicable
            tb = r.get("task_branch_name")
            if branch_workflow_run_id and develop_branch_name and tb and not require_human_review:
                try:
                    await merge_task_branch_into_develop_activity(
                        branch_workflow_run_id, tb, develop_branch_name, require_human_review,
                    )
                except Exception as merge_err:
                    logger.warning("Failed to merge task branch %s: %s", tb, merge_err)
        elif isinstance(r, Exception):
            logger.error("Concurrent claude-code task raised: %s", r)

    # Cleanup worktrees
    if use_worktrees and worktree_base:
        for wt_path in worktree_paths:
            if wt_path:
                try:
                    subprocess.run(
                        ["git", "worktree", "remove", "--force", wt_path],
                        cwd=workspace_root,
                        capture_output=True,
                        timeout=15,
                    )
                except Exception:
                    pass
        try:
            shutil.rmtree(worktree_base, ignore_errors=True)
        except Exception:
            pass

    return {"tasks_executed": executed_count, "project_id": project_id}

