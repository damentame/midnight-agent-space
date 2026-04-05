"""API-related Temporal activities for Cursor API and local LLM."""
import logging
from typing import Dict, Any, Optional
import json

from temporalio import activity
from temporal.utils.activity_run import track_activity

# Config import is lazy to avoid file system operations in workflow sandbox

logger = logging.getLogger(__name__)


@activity.defn
@track_activity
async def create_cursor_agent_activity(
    agent_data: Dict[str, Any],
    prompt: str,
    execute_mode: str = "fast",
) -> Dict[str, Any]:
    """
    Create agent via Cursor API.
    
    POSTs to Cursor API to create/register an agent.
    """
    # Lazy import to avoid loading HTTP libraries in workflow sandbox
    import httpx
    # Lazy import config to avoid file system operations in workflow sandbox
    from temporal.config import config
    from temporal.utils.model_routing import resolve_serialization_model
    
    if not config.cursor_api.api_key:
        raise ValueError("Cursor API key not configured")
    
    try:
        from temporal.utils.db import get_connection

        agent_name = agent_data.get('agent_name', 'Unknown')
        api_url = config.cursor_api.api_url
        api_key = config.cursor_api.api_key
        
        logger.info(f"Creating Cursor agent: {agent_name}")
        logger.info(f"API URL: {api_url}/agents")
        logger.info(f"API Key configured: {'Yes' if api_key else 'No'}")
        logger.info(f"API Key prefix: {api_key[:10] if api_key and len(api_key) > 10 else 'N/A'}...")
        
        model_id = resolve_serialization_model(execute_mode)
        prompt_obj: Dict[str, Any] = {"text": prompt}
        if model_id:
            prompt_obj["model"] = model_id
        request_body: Dict[str, Any] = {"prompt": prompt_obj}

        logger.info(
            "Request body (model=%s): %s",
            model_id or "(default)",
            json.dumps(request_body, indent=2),
        )
        logger.info(f"Prompt length: {len(prompt)} characters")
        
        async with httpx.AsyncClient() as client:
            full_url = f"{api_url}/agents"
            logger.info(f"POSTing to: {full_url}")
            
            response = await client.post(
                full_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json=request_body,
                timeout=30.0
            )
            
            logger.info(f"Response status: {response.status_code}")
            logger.debug(f"Response headers: {dict(response.headers)}")
            
            response.raise_for_status()
            result = response.json()
            
            logger.info(f"Cursor agent created successfully: {result.get('id')}")
            logger.debug(f"Agent response: {json.dumps(result, indent=2)}")

        # Log Cursor agent creation event in DB
        try:
            import hashlib

            db_agent_id = agent_data.get("agent_id")
            agent_instance_id = agent_data.get("agent_instance_id")
            project_id = agent_data.get("project_id")
            cursor_agent_id = result.get("id")

            prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]

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
                                'prompt_length', %s,
                                'prompt_hash', %s,
                                'timestamp', now()
                            ),
                            'system'
                        )
                        """,
                        (
                            db_agent_id,
                            project_id,
                            db_agent_id,
                            agent_instance_id,
                            cursor_agent_id,
                            len(prompt),
                            prompt_hash,
                        ),
                    )
            logger.info(
                "Logged CURSOR_AGENT_CREATED event for cursor_agent_id=%s",
                cursor_agent_id,
            )
        except Exception as log_error:
            import traceback

            logger.warning(
                "Failed to log CURSOR_AGENT_CREATED event: %s", log_error
            )
            logger.debug("Event log traceback:\n%s", traceback.format_exc())

        return result
            
    except httpx.HTTPStatusError as e:
        import traceback
        logger.error(f"HTTP error creating Cursor agent: {e}")
        logger.error(f"Status code: {e.response.status_code}")
        logger.error(f"Request URL: {full_url}")
        logger.error(f"Request body: {json.dumps(request_body, indent=2)}")
        try:
            response_json = e.response.json()
            logger.error(f"Response JSON: {json.dumps(response_json, indent=2)}")
        except:
            logger.error(f"Response text: {e.response.text}")
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
        raise
    except Exception as e:
        import traceback
        logger.error(f"Error creating Cursor agent: {e}")
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
        raise


@activity.defn
@track_activity
async def poll_cursor_agent_status_activity(
    agent_id: str,
    max_wait_minutes: int = 30,
    poll_interval_seconds: int = 10
) -> Dict[str, Any]:
    """
    Poll Cursor agent status until it's ready or completed.
    
    The agent is created with status "CREATING" and needs time to initialize.
    This activity polls the agent status endpoint until the agent is ready.
    
    Args:
        agent_id: Cursor agent ID
        max_wait_minutes: Maximum time to wait for agent to be ready (default: 30 minutes)
        poll_interval_seconds: How often to poll status (default: 10 seconds)
        
    Returns:
        Agent status information
    """
    import httpx
    import asyncio
    from temporal.config import config
    
    if not config.cursor_api.api_key:
        raise ValueError("Cursor API key not configured")
    
    try:
        logger.info(f"Polling Cursor agent {agent_id} status (max wait: {max_wait_minutes} minutes)")
        
        max_polls = (max_wait_minutes * 60) // poll_interval_seconds
        api_url = config.cursor_api.api_url
        api_key = config.cursor_api.api_key
        
        async with httpx.AsyncClient() as client:
            for poll_count in range(max_polls):
                try:
                    response = await client.get(
                        f"{api_url}/agents/{agent_id}",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json"
                        },
                        timeout=30.0
                    )
                    
                    if response.status_code == 404:
                        logger.warning(f"Agent {agent_id} not found (404), may still be creating...")
                        await asyncio.sleep(poll_interval_seconds)
                        continue
                    
                    response.raise_for_status()
                    agent_status = response.json()
                    
                    status = agent_status.get("status", "UNKNOWN")
                    logger.info(f"Agent {agent_id} status: {status} (poll {poll_count + 1}/{max_polls})")
                    
                    # Agent is ready when status is not "CREATING"
                    if status not in ["CREATING", "PENDING"]:
                        logger.info(f"Agent {agent_id} is ready with status: {status}")
                        return agent_status
                    
                    # Wait before next poll
                    await asyncio.sleep(poll_interval_seconds)
                    
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 404:
                        logger.warning(f"Agent {agent_id} not found yet, waiting...")
                        await asyncio.sleep(poll_interval_seconds)
                        continue
                    raise
                except Exception as e:
                    logger.warning(f"Error polling agent status: {e}, retrying...")
                    await asyncio.sleep(poll_interval_seconds)
                    continue
            
            # Timeout reached
            raise TimeoutError(
                f"Agent {agent_id} did not become ready within {max_wait_minutes} minutes. "
                f"Last status check: poll {poll_count + 1}/{max_polls}"
            )
            
    except Exception as e:
        import traceback
        logger.error(f"Error polling Cursor agent status: {e}")
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
        raise


@activity.defn
@track_activity
async def get_cursor_agent_results_activity(
    agent_id: str,
    document_id: Optional[int] = None,
    project_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Get results from a completed Cursor agent and store in database.
    
    Polls the agent until it completes, then retrieves and stores the results.
    
    Args:
        agent_id: Cursor agent ID
        document_id: Optional document ID to associate results with
        project_id: Optional project ID to associate results with
        
    Returns:
        Agent results and status
    """
    import httpx
    import asyncio
    from temporal.config import config
    from temporal.utils.db import get_connection
    
    if not config.cursor_api.api_key:
        raise ValueError("Cursor API key not configured")
    
    try:
        logger.info(f"Waiting for Cursor agent {agent_id} to complete and retrieving results")
        
        api_url = config.cursor_api.api_url
        api_key = config.cursor_api.api_key
        poll_interval = 15  # Poll every 15 seconds
        max_wait_minutes = 60  # Wait up to 60 minutes
        max_polls = (max_wait_minutes * 60) // poll_interval
        
        async with httpx.AsyncClient() as client:
            for poll_count in range(max_polls):
                try:
                    # Get agent status
                    response = await client.get(
                        f"{api_url}/agents/{agent_id}",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json"
                        },
                        timeout=30.0
                    )
                    
                    if response.status_code == 404:
                        logger.warning(f"Agent {agent_id} not found, waiting...")
                        await asyncio.sleep(poll_interval)
                        continue
                    
                    response.raise_for_status()
                    agent_data = response.json()
                    
                    status = agent_data.get("status", "UNKNOWN")
                    logger.info(f"Agent {agent_id} status: {status} (poll {poll_count + 1}/{max_polls})")
                    
                    # Check if agent is completed (status could be "COMPLETED", "SUCCESS", "FAILED", etc.)
                    if status in ["COMPLETED", "SUCCESS", "DONE", "FINISHED"]:
                        logger.info(f"Agent {agent_id} completed successfully")
                        
                        # Try to get results/artifacts (Cursor GET /agents/{id} only has id, name, status, source, target, summary, createdAt)
                        results = agent_data.get("results") or agent_data.get("output") or agent_data.get("artifacts")
                        # Fallback: Cursor writes output in the conversation; fetch it so we can extract tasks
                        if not results:
                            try:
                                conv_response = await client.get(
                                    f"{api_url}/agents/{agent_id}/conversation",
                                    headers={
                                        "Authorization": f"Bearer {api_key}",
                                        "Content-Type": "application/json",
                                    },
                                    timeout=30.0,
                                )
                                if conv_response.status_code == 200:
                                    conv_data = conv_response.json()
                                    messages = conv_data.get("messages") or []
                                    assistant_texts = [
                                        m.get("text") or ""
                                        for m in messages
                                        if m.get("type") == "assistant_message"
                                    ]
                                    if assistant_texts:
                                        results = "\n\n".join(assistant_texts)
                                        logger.info(
                                            "Fetched agent output from conversation (%s assistant messages)",
                                            len(assistant_texts),
                                        )
                            except Exception as conv_err:
                                logger.warning(
                                    "Could not fetch agent conversation for %s: %s",
                                    agent_id,
                                    conv_err,
                                )
                        # Fallback: fetch artifacts (agent may write task JSON to repo files)
                        if isinstance(results, str):
                            try:
                                art_resp = await client.get(
                                    f"{api_url}/agents/{agent_id}/artifacts",
                                    headers={
                                        "Authorization": f"Bearer {api_key}",
                                        "Content-Type": "application/json",
                                    },
                                    timeout=15.0,
                                )
                                if art_resp.status_code == 200:
                                    art_data = art_resp.json()
                                    artifacts = art_data.get("artifacts") or []
                                    for art in artifacts:
                                        path = art.get("absolutePath") or ""
                                        if ".json" in path or "task" in path.lower():
                                            try:
                                                dl_resp = await client.get(
                                                    f"{api_url}/agents/{agent_id}/artifacts/download",
                                                    params={"path": path},
                                                    headers={
                                                        "Authorization": f"Bearer {api_key}",
                                                    },
                                                    timeout=15.0,
                                                )
                                                if dl_resp.status_code == 200:
                                                    dl_data = dl_resp.json()
                                                    url = dl_data.get("url")
                                                    if url:
                                                        fetch_resp = await client.get(url, timeout=30.0)
                                                        if fetch_resp.status_code == 200:
                                                            content = fetch_resp.text
                                                            results = (results or "") + "\n\n" + content
                                                            logger.info(
                                                                "Appended artifact %s to results",
                                                                path,
                                                            )
                                            except Exception as art_err:
                                                logger.debug(
                                                    "Could not download artifact %s: %s",
                                                    path,
                                                    art_err,
                                                )
                            except Exception as art_fetch_err:
                                logger.warning(
                                    "Could not fetch agent artifacts for %s: %s",
                                    agent_id,
                                    art_fetch_err,
                                )
                        
                        # Store results in database if document_id is provided
                        if document_id and results:
                            try:
                                with get_connection() as conn:
                                    with conn.cursor() as cur:
                                        serialized_data = {
                                            "cursor_agent_id": agent_id,
                                            "cursor_agent_status": status,
                                            "cursor_agent_results": results,
                                            "cursor_agent_completed_at": agent_data.get("completedAt") or agent_data.get("createdAt"),
                                            "agent_data": agent_data
                                        }
                                        cur.execute("""
                                            UPDATE main.project_document
                                            SET 
                                                serialized_payload = %s,
                                                serialization_status = 'COMPLETED',
                                                serialized_at = CURRENT_TIMESTAMP,
                                                structured_json = COALESCE(structured_json, '{}'::jsonb) || 
                                                    jsonb_build_object(
                                                        'cursor_agent_id', %s,
                                                        'cursor_agent_status', %s,
                                                        'cursor_agent_completed_at', CURRENT_TIMESTAMP
                                                    ),
                                                updated_at = CURRENT_TIMESTAMP
                                            WHERE document_id = %s
                                        """, (json.dumps(serialized_data), agent_id, status, document_id))
                                    logger.info(f"Stored Cursor agent results in serialized_payload for document {document_id}")
                            except Exception as db_error:
                                logger.warning(f"Could not store results in database: {db_error}")
                                import traceback
                                logger.warning(f"Database error traceback: {traceback.format_exc()}")
                        
                        # Log Cursor agent completion event in database
                        try:
                            from temporal.utils.db import get_connection as _get_conn_for_log

                            # Heuristic: detect whether results contain task JSON
                            has_tasks = False
                            if isinstance(results, dict) and "tasks" in results:
                                has_tasks = True
                            elif isinstance(results, list) and results:
                                first_item = results[0]
                                if isinstance(first_item, dict) and "tasks" in first_item:
                                    has_tasks = True

                            result_length = 0
                            if isinstance(results, list):
                                result_length = len(results)
                            elif results is not None:
                                result_length = 1

                            with _get_conn_for_log() as log_conn:
                                with log_conn.cursor() as log_cur:
                                    log_cur.execute(
                                        """
                                        INSERT INTO main.event_log (
                                            entity_type,
                                            entity_id,
                                            project_id,
                                            event_type,
                                            payload,
                                            created_by
                                        )
                                        VALUES (
                                            'CURSOR_AGENT',
                                            %s,
                                            %s,
                                            'CURSOR_AGENT_COMPLETED',
                                            jsonb_build_object(
                                                'provider', 'cursor',
                                                'cursor_agent_id', %s,
                                                'status', %s,
                                                'result_length', %s,
                                                'has_tasks', %s,
                                                'document_id', %s,
                                                'project_id', %s,
                                                'completed_at', %s
                                            ),
                                            'system'
                                        )
                                        """,
                                        (
                                            None,
                                            project_id,
                                            agent_id,
                                            status,
                                            result_length,
                                            has_tasks,
                                            document_id,
                                            project_id,
                                            agent_data.get("completedAt")
                                            or agent_data.get("createdAt"),
                                        ),
                                    )
                            logger.info(
                                "Logged CURSOR_AGENT_COMPLETED event for cursor_agent_id=%s",
                                agent_id,
                            )
                        except Exception as log_error:
                            import traceback

                            logger.warning(
                                "Failed to log CURSOR_AGENT_COMPLETED event: %s",
                                log_error,
                            )
                            logger.debug(
                                "Completion event traceback:\n%s",
                                traceback.format_exc(),
                            )

                        return {
                            "agent_id": agent_id,
                            "status": status,
                            "results": results,
                            "agent_data": agent_data
                        }
                    
                    # Check if agent failed
                    if status in ["FAILED", "ERROR", "CANCELLED"]:
                        error_msg = agent_data.get("error") or agent_data.get("message", "Unknown error")
                        logger.error(f"Agent {agent_id} failed with status {status}: {error_msg}")
                        raise RuntimeError(f"Cursor agent failed: {error_msg}")
                    
                    # Agent still processing, wait and poll again
                    await asyncio.sleep(poll_interval)
                    
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 404:
                        logger.warning(f"Agent {agent_id} not found yet, waiting...")
                        await asyncio.sleep(poll_interval)
                        continue
                    raise
                except RuntimeError:
                    # Re-raise agent failure errors
                    raise
                except Exception as e:
                    logger.warning(f"Error checking agent status: {e}, retrying...")
                    await asyncio.sleep(poll_interval)
                    continue
            
            # Timeout reached
            raise TimeoutError(
                f"Agent {agent_id} did not complete within {max_wait_minutes} minutes. "
                f"Last status: {agent_data.get('status', 'UNKNOWN')}"
            )
            
    except Exception as e:
        import traceback
        logger.error(f"Error getting Cursor agent results: {e}")
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
        raise


def _normalize_tasks_obj(obj: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Convert dict with tasks/task_list/items key to {'tasks': [...]}."""
    if "tasks" in obj and isinstance(obj.get("tasks"), list):
        return obj
    for key in ("task_list", "items"):
        if key in obj and isinstance(obj.get(key), list):
            arr = obj[key]
            if arr and isinstance(arr[0], dict) and "task_name" in arr[0]:
                return {"tasks": arr}
    return None


def _extract_tasks_from_payload(payload: Any) -> Optional[Dict[str, Any]]:
    """Extract normalized {'tasks': [...]} from agent results (string, dict, or list)."""
    import re

    if payload is None:
        return None
    if isinstance(payload, dict):
        out = _normalize_tasks_obj(payload)
        if out:
            return out
    if isinstance(payload, list) and payload:
        for item in payload:
            if isinstance(item, dict):
                out = _normalize_tasks_obj(item)
                if out:
                    return out
    if isinstance(payload, str):
        s = payload.strip()
        try:
            parsed = json.loads(s)
            return _extract_tasks_from_payload(parsed)
        except json.JSONDecodeError:
            pass
        for match in re.finditer(r"```(?:json)?\s*([\s\S]*?)```", s):
            try:
                parsed = json.loads(match.group(1).strip())
                out = _extract_tasks_from_payload(parsed)
                if out:
                    return out
            except (json.JSONDecodeError, IndexError):
                continue
        m = re.search(r'\{\s*"tasks"\s*:', s)
        if m:
            start_idx = m.start()
            depth = 0
            for i, c in enumerate(s[start_idx:], start_idx):
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(s[start_idx : i + 1])
                        out = _normalize_tasks_obj(parsed) if isinstance(parsed, dict) else None
                        if out:
                            return out
                    except json.JSONDecodeError:
                        pass
                    break
    return None


async def _request_tasks_json_followup_and_collect(
    agent_id: str,
    document_id: Optional[int],
    project_id: Optional[int],
) -> Optional[Dict[str, Any]]:
    """
    Ask an already-finished Cursor agent to return strict JSON tasks and collect results.
    """
    import httpx
    from temporal.config import config

    api_url = config.cursor_api.api_url
    api_key = config.cursor_api.api_key
    if not api_key:
        return None

    followup_text = (
        "Return ONLY one markdown code block containing valid JSON with a top-level "
        "\"tasks\" array matching the required schema from earlier instructions. "
        "Do not include prose, summary, commits, push commands, PR links, or any text "
        "outside the single JSON code block."
    )
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{api_url}/agents/{agent_id}/followup",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={"prompt": {"text": followup_text}},
            timeout=30.0,
        )
        resp.raise_for_status()

    followup_results = await get_cursor_agent_results_activity(
        agent_id, document_id, project_id
    )
    extracted = _extract_tasks_from_payload(followup_results.get("results"))
    if extracted:
        return extracted
    return None


def _enrich_tasks_json_with_execution_complexity(
    tasks_json: Dict[str, Any], default_mode: str
) -> None:
    """Ensure each task has task_data.execution_complexity for downstream task executor routing."""
    from temporal.utils.model_routing import infer_execution_complexity

    tasks = tasks_json.get("tasks") or []
    for t in tasks:
        if not isinstance(t, dict):
            continue
        td = t.get("task_data")
        if not isinstance(td, dict):
            td = {}
        raw = td.get("execution_complexity") or t.get("execution_complexity")
        if isinstance(raw, str) and raw.strip().lower() in ("fast", "complex"):
            t["task_data"] = td
            continue
        inferred = infer_execution_complexity(t, default_mode)
        td["execution_complexity"] = inferred
        t["task_data"] = td


@activity.defn
@track_activity
async def persist_generated_tasks_activity(
    project_id: int,
    document_id: Optional[int],
    db_agent_id: int,
    agent_instance_id: int,
    cursor_response: Dict[str, Any],
    workflow_run_id: Optional[int] = None,
    execute_mode: str = "fast",
) -> Dict[str, Any]:
    """
    Extract tasks from Cursor agent response and persist to main.task / main.task_dependency.
    Called from the main document serialization workflow after serialize_document_cursor_activity.
    """
    from temporal.utils.db import get_connection

    results_payload = cursor_response.get("results")
    agent_data = cursor_response.get("agent_data") or {}
    if not results_payload and agent_data:
        results_payload = agent_data.get("results") or agent_data.get("output") or agent_data.get("artifacts")

    tasks_json = _extract_tasks_from_payload(results_payload)
    task_count = len(tasks_json.get("tasks", [])) if tasks_json else 0

    if tasks_json and task_count:
        _enrich_tasks_json_with_execution_complexity(tasks_json, execute_mode)

    if not tasks_json or task_count == 0 or project_id is None or document_id is None:
        payload_preview = ""
        if results_payload is not None and isinstance(results_payload, str):
            payload_preview = f" First 300 chars: {results_payload.strip()[:300]!r}"
        logger.warning(
            "persist_generated_tasks_activity: no tasks to persist; task_count=%s, project_id=%s, document_id=%s.%s",
            task_count,
            project_id,
            document_id,
            payload_preview,
        )
        return {"persisted": False, "task_count": 0}

    batch_id = str(cursor_response.get("agent_id") or "") or None
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CALL main.sp_persist_generated_tasks(
                        %s, %s, %s, %s, %s::jsonb, %s, %s, %s
                    )
                    """,
                    (
                        project_id,
                        document_id,
                        db_agent_id,
                        agent_instance_id,
                        json.dumps(tasks_json),
                        batch_id,
                        "system",
                        workflow_run_id,
                    ),
                )
        logger.info(
            "Persisted %s generated tasks for project_id=%s, document_id=%s "
            "(task execution will pick these up)",
            task_count,
            project_id,
            document_id,
        )
        return {"persisted": True, "task_count": task_count}
    except Exception as db_error:
        import traceback
        logger.error("Error calling sp_persist_generated_tasks: %s", db_error)
        logger.error("DB traceback:\n%s", traceback.format_exc())
        raise


async def _decommission_cursor_agent(cursor_agent_id: str) -> Dict[str, Any]:
    """
    Best-effort decommission of a Cursor cloud agent to avoid hitting plan limits.

    Uses DELETE /v0/agents/{id} with basic auth (api_key:).
    """
    import httpx
    from temporal.config import config

    if not cursor_agent_id:
        logger.warning("decommission_cursor_agent called with empty id")
        return {"deleted": False, "reason": "empty_id"}

    api_key = config.cursor_api.api_key
    api_url = config.cursor_api.api_url
    if not api_key:
        raise ValueError("Cursor API key not configured")

    delete_url = f"{api_url}/agents/{cursor_agent_id}"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                delete_url,
                auth=(api_key, ""),  # Basic auth: api_key as username
                timeout=30.0,
            )
        if resp.status_code == 404:
            logger.info(
                "Cursor agent %s already deleted or not found when decommissioning",
                cursor_agent_id,
            )
            return {"deleted": False, "status_code": 404}
        resp.raise_for_status()
        logger.info("Decommissioned Cursor agent %s (status_code=%s)", cursor_agent_id, resp.status_code)
        return {"deleted": True, "status_code": resp.status_code}
    except Exception as e:
        import traceback

        logger.warning("Failed to decommission Cursor agent %s: %s", cursor_agent_id, e)
        logger.debug("Decommission traceback:\n%s", traceback.format_exc())
        return {"deleted": False, "error": str(e)}


@activity.defn
@track_activity
async def decommission_cursor_agent_activity(cursor_agent_id: str) -> Dict[str, Any]:
    """Temporal activity wrapper to decommission a Cursor cloud agent."""
    return await _decommission_cursor_agent(cursor_agent_id)


async def _wait_for_cursor_agent_terminal_state(
    agent_id: str,
    max_wait_minutes: int = 60,
    poll_interval_seconds: int = 15,
) -> Dict[str, Any]:
    """
    Poll Cursor agent until it reaches a terminal state (FINISHED, COMPLETED, FAILED, etc.).
    Used so we only create the task-generation agent after the BRA agent is done,
    staying within single-agent plan limits.
    """
    import httpx
    import asyncio
    from temporal.config import config

    api_url = config.cursor_api.api_url
    api_key = config.cursor_api.api_key
    max_polls = (max_wait_minutes * 60) // poll_interval_seconds
    terminal_ok = ["COMPLETED", "SUCCESS", "DONE", "FINISHED"]
    terminal_fail = ["FAILED", "ERROR", "CANCELLED"]

    async with httpx.AsyncClient() as client:
        for poll_count in range(max_polls):
            try:
                response = await client.get(
                    f"{api_url}/agents/{agent_id}",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=30.0,
                )
                if response.status_code == 404:
                    await asyncio.sleep(poll_interval_seconds)
                    continue
                response.raise_for_status()
                agent_data = response.json()
                status = agent_data.get("status", "UNKNOWN")
                logger.info(
                    f"BRA agent {agent_id} status: {status} (poll {poll_count + 1}/{max_polls})"
                )
                if status in terminal_ok:
                    logger.info(f"BRA agent {agent_id} completed; creating task-generation agent next")
                    return agent_data
                if status in terminal_fail:
                    logger.warning(
                        f"BRA agent {agent_id} ended with status {status}; "
                        "creating task-generation agent to free slot"
                    )
                    return agent_data
                await asyncio.sleep(poll_interval_seconds)
            except Exception as e:
                logger.warning(f"Error polling BRA agent status: {e}, retrying...")
                await asyncio.sleep(poll_interval_seconds)
                continue
        raise TimeoutError(
            f"BRA agent {agent_id} did not reach terminal state within {max_wait_minutes} minutes"
        )


@activity.defn
@track_activity
async def serialize_document_cursor_activity(
    rag_context: Dict[str, Any],
    agent_id: str,
    task_query: Optional[str] = None,
    document_id: Optional[int] = None,
    project_id: Optional[int] = None,
    db_agent_id: Optional[int] = None,
    agent_instance_id: Optional[int] = None,
    execute_mode: str = "fast",
) -> Dict[str, Any]:
    """
    Send enriched RAG context to Cursor agent for deep task generation,
    then wait for the agent to complete and retrieve results.
    
    The agent is already created with a base prompt. This activity:
    1. Waits for the BRA agent to reach a terminal state (so only one agent runs at a time)
    2. Sends a second, task-generation request that includes:
       - RAG chunks derived from main.project_document content
       - Strict task generation instructions aligned to DB schema
       - Emphasis on constraints and success criteria
    3. Polls until the agent completes and stores results in the database
    
    Args:
        rag_context: RAG retrieval results (for logging/context)
        agent_id: Cursor agent ID
        task_query: Optional high-level task query text (will be
            embedded into a richer instruction prompt)
        document_id: Optional document ID to store results with
        project_id: Optional project ID to store results with
        db_agent_id: Optional DB agent_id for traceability in task records
        agent_instance_id: Optional agent_instance_id used during planning
        
    Returns:
        Agent results and completion status, including any generated tasks.
    """
    # Lazy imports to keep workflow sandbox clean
    import httpx
    from temporal.config import config

    try:
        results_list = rag_context.get("results", []) or []
        logger.info(
            f"Starting task-generation phase for Cursor agent {agent_id} "
            f"with {len(results_list)} RAG chunks"
        )

        # ------------------------------------------------------------------
        # 1. Wait for BRA agent to reach a terminal state before creating
        #    the task-generation agent (avoids exceeding single-agent plan).
        # ------------------------------------------------------------------
        try:
            bra_final = await _wait_for_cursor_agent_terminal_state(
                agent_id,
                max_wait_minutes=60,
                poll_interval_seconds=15,
            )
            logger.info(
                f"BRA agent {agent_id} is done (status={bra_final.get('status')}); "
                "creating task-generation agent"
            )
        except Exception as e:
            logger.warning(
                f"Could not wait for BRA agent to finish before task generation: {e}"
            )
            raise

        # ------------------------------------------------------------------
        # 2. Build strict, DB-aligned task generation instructions
        #    and embed RAG chunks directly into a new agent prompt
        # ------------------------------------------------------------------
        default_objective = (
            "Generate an exhaustive, implementation-ready task list for this project "
            "based strictly on the provided project_document requirements and context."
        )
        high_level_query = task_query or default_objective

        # Format RAG chunks as contextual sections the agent can reference.
        # We include IDs so the model can map tasks back to project_document
        # rows and RAG chunk records.
        rag_sections = []
        for chunk in results_list[:10]:  # Top 10 enriched chunks
            chunk_text = chunk.get("chunk_text", "")
            document_name = chunk.get("document_name", "Unknown")
            document_type = chunk.get("document_type", "N/A")
            requirement_type = chunk.get("requirement_type", "general")
            similarity_score = chunk.get("similarity_score", 0)
            has_constraints = chunk.get("has_constraints", False)
            has_success_criteria = chunk.get("has_success_criteria", False)
            chunk_id = chunk.get("chunk_id")
            document_id_val = chunk.get("document_id")

            rag_sections.append(
                f"""
--- REQUIREMENT CHUNK ---
document_name: {document_name}
document_type: {document_type}
document_id: {document_id_val}
chunk_id: {chunk_id}
requirement_type: {requirement_type}
similarity: {similarity_score:.2f}
has_constraints: {has_constraints}
has_success_criteria: {has_success_criteria}

TEXT:
{chunk_text}
"""
            )

        rag_context_text = "\n".join(rag_sections) if rag_sections else "NO RELEVANT REQUIREMENT CHUNKS FOUND."

        # This block is what the agent should use to shape each task. It is
        # deliberately explicit about how tasks map to the main.task schema
        # and how constraints / success criteria must be enforced.
        task_instruction_prompt = f"""
You are generating a detailed task plan for project_id={project_id or 'UNKNOWN'} based ONLY on the requirements and context provided in the RAG chunks.

PRIMARY OBJECTIVE:
- {high_level_query}

STRICT REQUIREMENT SOURCE:
- Every task MUST be directly justified by one or more requirement snippets taken from the project_document content represented in the RAG chunks.
- Do NOT invent requirements, constraints, or success criteria that are not explicitly present or clearly implied by that content.

STRICT ADHERENCE TO CONSTRAINTS AND SUCCESS CRITERIA:
- If a chunk is marked has_constraints=true, you MUST capture those constraints explicitly in the task.
- If a chunk is marked has_success_criteria=true, you MUST extract those success / acceptance criteria sentences and attach them to the relevant tasks.
- When a requirement contains acceptance or validation language (e.g. "must pass", "validate", "verify", "acceptance criteria"), treat those as success_criteria for the task and preserve the wording as much as possible.

TASK SCHEMA (MIRRORS DB main.task AND RELATED JSON FIELDS):
- Each task MUST be returned as a JSON object with:
  - task_name: string, short imperative title (e.g. "Implement authentication middleware")
  - task_type: string, high-level category (e.g. "implementation", "design", "testing", "research", "migration")
  - description: string, multi-paragraph explanation that:
    - references the specific requirement text it implements
    - explains the intent, scope, and any important edge cases
  - parameters: object, containing any structured inputs or configuration that engineers or tools will need
  - status: string, initial status; use "PENDING" for all newly created tasks
  - priority: integer, where 1 is highest priority and larger numbers are lower priority.
    - Derive this from priority indicators in the text (e.g. "critical", "high", "low") when present.
    - If no priority indicators are present, default to 3.
  - task_notes: string, additional free-form notes (risks, open questions, trade-offs)
  - task_data: object, used to capture rich, requirement-level metadata:
    - requirement_snippets: array of strings; each is a verbatim snippet from the project_document text that justifies this task
    - requirement_type: string; use the requirement_type field from the chunk when available (e.g. "functional", "constraint", "acceptance_criteria", "general")
    - constraints: array of strings; explicit constraints extracted from the requirement text
    - success_criteria: array of strings; explicit success / acceptance criteria sentences
    - execution_complexity: string, REQUIRED: either "fast" or "complex". Use "fast" for small/local edits, trivial wiring, simple documentation updates. Use "complex" for large refactors, cross-cutting design, security-sensitive work, performance, research, migration, or ambiguous scope.
    - project_id: integer; {project_id if project_id is not None else "use the project_id from the RAG chunks"}
    - document_ids: array of integers; all document_id values from chunks that informed this task
    - chunk_ids: array of integers; all chunk_id values from chunks that informed this task
    - dependencies: array of strings; each entry is the task_name of another task that must be completed first

OUTPUT FORMAT:
- CRITICAL: Your response MUST include exactly one markdown code block containing only the JSON, e.g. ```json followed by the JSON and ```. This ensures reliable parsing.
- The JSON object MUST have a top-level key "tasks" (array). Use this exact shape:
  {{
    "tasks": [{{ ... task objects as described above ... }}]
  }}
- Do NOT return any additional commentary or fields outside the code block.
- Do NOT run git commands, create commits, push branches, or open pull requests.
""".strip()

        # ------------------------------------------------------------------
        # 3. Build and send a SECOND agent prompt (new agent) to Cursor API
        #    using the enriched RAG context as plain text.
        #
        #    NOTE: Cursor's public /v0 API supports:
        #      - POST {api_url}/agents        (create agent with prompt)
        #      - GET  {api_url}/agents/{id}   (poll for results)
        #    There is no /agents/{id}/tasks subresource, so we create a
        #    dedicated "task-generation" agent instead of calling a tasks
        #    endpoint that would 404.
        # ------------------------------------------------------------------
        if not config.cursor_api.api_key:
            raise ValueError("Cursor API key not configured")

        # Combine RAG requirement sections + strict instructions into a
        # single prompt text for the task-generation agent.
        full_task_prompt = (
            "REQUIREMENT CONTEXT (from project_document via RAG):\n"
            f"{rag_context_text}\n\n"
            "TASK GENERATION SPECIFICATION:\n"
            f"{task_instruction_prompt}"
        )

        from temporal.utils.model_routing import resolve_serialization_model

        model_id = resolve_serialization_model(execute_mode)
        prompt_obj: Dict[str, Any] = {"text": full_task_prompt}
        if model_id:
            prompt_obj["model"] = model_id
        request_body = {"prompt": prompt_obj}

        api_url = config.cursor_api.api_url
        async with httpx.AsyncClient() as client:
            create_url = f"{api_url}/agents"
            logger.info(
                f"Creating dedicated task-generation Cursor agent for "
                f"project_id={project_id}, document_id={document_id} at {create_url}"
            )
            logger.info(
                f"Task-generation agent prompt length: {len(full_task_prompt)} characters"
            )

            try:
                response = await client.post(
                    create_url,
                    headers={
                        "Authorization": f"Bearer {config.cursor_api.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=request_body,
                    timeout=60.0,
                )
                logger.info(
                    f"Task-generation agent create status: {response.status_code}"
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                # Log detailed error information from Cursor for easier debugging
                logger.error(
                    f"HTTP error creating task-generation Cursor agent: "
                    f"status={e.response.status_code}, url={e.request.url}"
                )
                try:
                    err_json = e.response.json()
                    logger.error(f"Cursor error response JSON: {json.dumps(err_json, indent=2)}")
                except Exception:
                    logger.error(f"Cursor error response text: {e.response.text}")
                raise

            task_agent_data = response.json()
            task_agent_id = task_agent_data.get("id")

        if not task_agent_id:
            raise ValueError(
                "Cursor task-generation agent did not return an 'id' field"
            )

        logger.info(
            f"Task-generation Cursor agent created successfully: {task_agent_id} "
            f"(original agent_id for serialization was {agent_id})"
        )

        # ------------------------------------------------------------------
        # 4. Wait for task-generation agent to complete and retrieve results
        # ------------------------------------------------------------------
        logger.info(
            f"Waiting for Cursor task-generation agent {task_agent_id} to "
            f"finish task generation"
        )
        final_results = await get_cursor_agent_results_activity(
            task_agent_id, document_id, project_id
        )
        extracted_tasks = _extract_tasks_from_payload(final_results.get("results"))
        if not extracted_tasks:
            logger.warning(
                "Task-generation output had no extractable tasks; sending strict JSON follow-up to agent %s",
                task_agent_id,
            )
            try:
                recovered = await _request_tasks_json_followup_and_collect(
                    task_agent_id, document_id, project_id
                )
                if recovered:
                    final_results["results"] = recovered
                    logger.info(
                        "Recovered %s tasks from follow-up output for agent %s",
                        len(recovered.get("tasks", [])),
                        task_agent_id,
                    )
            except Exception as followup_err:
                logger.warning(
                    "Follow-up task recovery failed for agent %s: %s",
                    task_agent_id,
                    followup_err,
                )

        # Task persistence is performed by the main workflow via
        # persist_generated_tasks_activity (Step 8) so it is explicit in the workflow.

        # Best-effort decommission of both the BRA and task-generation agents to
        # avoid hitting the max concurrent cloud agents limit.
        try:
            await _decommission_cursor_agent(task_agent_id)
        except Exception as dec_err:
            logger.warning(
                "Failed to decommission task-generation agent %s: %s",
                task_agent_id,
                dec_err,
            )
        try:
            await _decommission_cursor_agent(agent_id)
        except Exception as dec_err:
            logger.warning(
                "Failed to decommission BRA agent %s: %s",
                agent_id,
                dec_err,
            )

        logger.info(
            f"Cursor task-generation agent {task_agent_id} completed with status "
            f"{final_results.get('status')}"
        )
        return final_results
        
    except Exception as e:
        import traceback
        logger.error(f"Error during Cursor agent task generation: {e}")
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
        raise


def _build_task_generation_prompt_from_rag(
    rag_context: Dict[str, Any],
    task_query: Optional[str],
    project_id: Optional[int],
) -> str:
    """Build task-generation prompt from RAG context (shared by Cursor and Codex paths)."""
    results_list = rag_context.get("results", []) or []
    rag_sections = []
    for chunk in results_list[:10]:
        chunk_text = chunk.get("chunk_text", "")
        document_name = chunk.get("document_name", "Unknown")
        document_type = chunk.get("document_type", "N/A")
        requirement_type = chunk.get("requirement_type", "general")
        similarity_score = chunk.get("similarity_score", 0)
        has_constraints = chunk.get("has_constraints", False)
        has_success_criteria = chunk.get("has_success_criteria", False)
        chunk_id = chunk.get("chunk_id")
        document_id_val = chunk.get("document_id")
        rag_sections.append(
            f"""
--- REQUIREMENT CHUNK ---
document_name: {document_name}
document_type: {document_type}
document_id: {document_id_val}
chunk_id: {chunk_id}
requirement_type: {requirement_type}
similarity: {similarity_score:.2f}
has_constraints: {has_constraints}
has_success_criteria: {has_success_criteria}

TEXT:
{chunk_text}
"""
        )
    rag_context_text = "\n".join(rag_sections) if rag_sections else "NO RELEVANT REQUIREMENT CHUNKS FOUND."
    default_objective = (
        "Generate an exhaustive, implementation-ready task list for this project "
        "based strictly on the provided project_document requirements and context."
    )
    high_level_query = task_query or default_objective
    task_instruction_prompt = f"""
You are generating a detailed task plan for project_id={project_id or 'UNKNOWN'} based ONLY on the requirements and context provided in the RAG chunks.

PRIMARY OBJECTIVE:
- {high_level_query}

STRICT REQUIREMENT SOURCE:
- Every task MUST be directly justified by one or more requirement snippets taken from the project_document content represented in the RAG chunks.
- Do NOT invent requirements, constraints, or success criteria that are not explicitly present or clearly implied by that content.

STRICT ADHERENCE TO CONSTRAINTS AND SUCCESS CRITERIA:
- If a chunk is marked has_constraints=true, you MUST capture those constraints explicitly in the task.
- If a chunk is marked has_success_criteria=true, you MUST extract those success / acceptance criteria sentences and attach them to the relevant tasks.
- When a requirement contains acceptance or validation language (e.g. "must pass", "validate", "verify", "acceptance criteria"), treat those as success_criteria for the task and preserve the wording as much as possible.

TASK SCHEMA (MIRRORS DB main.task AND RELATED JSON FIELDS):
- Each task MUST be returned as a JSON object with:
  - task_name: string, short imperative title (e.g. "Implement authentication middleware")
  - task_type: string, high-level category (e.g. "implementation", "design", "testing", "research", "migration")
  - description: string, multi-paragraph explanation that references the specific requirement text it implements
  - parameters: object, containing any structured inputs or configuration
  - status: string, use "PENDING" for all newly created tasks
  - priority: integer, 1 is highest; default 3 if not specified in text
  - task_notes: string, additional free-form notes
  - task_data: object with: requirement_snippets, requirement_type, constraints, success_criteria, execution_complexity ("fast" or "complex", see above), project_id, document_ids, chunk_ids, dependencies

OUTPUT FORMAT:
- CRITICAL: Your response MUST include exactly one markdown code block containing only the JSON, e.g. ```json followed by the JSON and ```.
- The JSON object MUST have a top-level key "tasks" (array). Use this exact shape: {{"tasks": [...]}}
- Do NOT return any additional commentary or fields outside the code block.
- Do NOT run git commands, create commits, push branches, or open pull requests.
""".strip()
    return (
        "REQUIREMENT CONTEXT (from project_document via RAG):\n"
        f"{rag_context_text}\n\n"
        "TASK GENERATION SPECIFICATION:\n"
        f"{task_instruction_prompt}"
    )


@activity.defn
@track_activity
async def serialize_document_codex_activity(
    rag_context: Dict[str, Any],
    task_query: Optional[str],
    document_id: Optional[int],
    project_id: int,
    db_agent_id: int,
    agent_instance_id: int,
) -> Dict[str, Any]:
    """
    Generate tasks from RAG context using Codex/OpenAI chat completions.

    Returns a response in the same shape expected by persist_generated_tasks_activity
    (results, status, agent_id for batch).
    """
    import httpx
    import uuid
    from temporal.config import config

    api_key = config.codex_api.api_key or config.openai.api_key
    if not api_key:
        raise ValueError("Codex/OpenAI API key not configured")

    api_url = config.codex_api.api_url.rstrip("/")
    model = config.codex_api.model
    results_list = rag_context.get("results", []) or []
    logger.info(
        f"serialize_document_codex_activity: generating tasks from {len(results_list)} RAG chunks "
        f"for project_id={project_id}, document_id={document_id}"
    )

    full_prompt = _build_task_generation_prompt_from_rag(rag_context, task_query, project_id)

    request_body: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a senior software engineer generating implementation-ready task plans from project requirements. Output only valid JSON in a markdown code block."},
            {"role": "user", "content": full_prompt},
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
            timeout=300.0,
        )
        resp.raise_for_status()
        data = resp.json()

    choices = data.get("choices") or []
    content = ""
    if choices:
        msg = choices[0].get("message") or {}
        content = msg.get("content") or ""

    tasks_json = _extract_tasks_from_payload(content)
    if tasks_json:
        logger.info(
            f"Codex task generation: extracted {len(tasks_json.get('tasks', []))} tasks "
            f"for project_id={project_id}, document_id={document_id}"
        )
    else:
        logger.warning(
            f"Codex task generation: could not extract tasks from response; "
            f"content length={len(content)}"
        )

    batch_id = str(uuid.uuid4())
    return {
        "results": tasks_json or {"tasks": []},
        "status": "COMPLETED",
        "agent_id": batch_id,
        "agent_data": {},
    }


@activity.defn
@track_activity
async def serialize_document_local_activity(
    document_data: Dict[str, Any],
    model_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Serialize document using local LLM (e.g., Ollama).
    
    Alternative to Cursor API for local development/testing.
    """
    # Lazy import to avoid loading HTTP libraries in workflow sandbox
    import httpx
    # Lazy import config to avoid file system operations in workflow sandbox
    from temporal.config import config
    
    if not config.local_llm.enabled:
        raise ValueError("Local LLM not enabled in configuration")
    
    try:
        document_id = document_data.get("document_id")
        logger.info(f"Serializing document {document_id} via local LLM")
        
        model = model_config.get("model") if model_config else config.local_llm.model
        url = config.local_llm.url
        
        # Build prompt for serialization
        content = document_data.get("content", "")
        prompt = f"""Please serialize and structure the following document content into a JSON format suitable for agent context:

{content}

Provide a structured JSON representation that includes:
- Key concepts and topics
- Important details and specifications
- Relationships between elements
- Any actionable items or requirements"""
        
        request_body = {
            "model": model,
            "prompt": prompt,
            "stream": False
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{url}/api/generate",
                json=request_body,
                timeout=120.0
            )
            response.raise_for_status()
            result = response.json()
            
            # Parse response
            serialized_text = result.get("response", "")
            try:
                serialized_data = json.loads(serialized_text)
            except json.JSONDecodeError:
                # If not JSON, wrap in object
                serialized_data = {"raw_serialization": serialized_text}
            
            logger.info(f"Document {document_id} serialized via local LLM")
            return {"serialized": serialized_data}
            
    except Exception as e:
        logger.error(f"Error serializing document via local LLM: {e}")
        raise

