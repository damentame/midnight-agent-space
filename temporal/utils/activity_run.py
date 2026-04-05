"""Helpers for logging activity executions to main.activity_run."""
import json
import logging
from functools import wraps
from typing import Any, Awaitable, Callable, Dict

from temporalio import activity

from temporal.utils.db import get_connection

logger = logging.getLogger(__name__)


def _insert_activity_run(
    workflow_id: str,
    run_id: str,
    activity_type: str,
    activity_id: str,
    status: str,
    input_data: Dict[str, Any] | None,
) -> int:
    """Insert a new row into main.activity_run and return activity_run_id."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO main.activity_run (
                    workflow_id,
                    run_id,
                    activity_type,
                    activity_id,
                    status,
                    input_data
                )
                VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                RETURNING activity_run_id
                """,
                (
                    workflow_id,
                    run_id,
                    activity_type,
                    activity_id,
                    status,
                    json.dumps(input_data or {}),
                ),
            )
            row = cur.fetchone()
            if not row:
                raise RuntimeError(
                    "Failed to insert activity_run row (no id returned)"
                )
            return int(row[0])


def _update_activity_run(
    activity_run_id: int,
    status: str,
    result_data: Dict[str, Any] | None = None,
    error_message: str | None = None,
) -> None:
    """Update an existing activity_run row with result or error."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE main.activity_run
                SET
                    status       = %s,
                    result_data  = %s::jsonb,
                    error_message = %s,
                    finished_at  = now(),
                    updated_at   = now()
                WHERE activity_run_id = %s
                """,
                (
                    status,
                    json.dumps(result_data or {}),
                    error_message,
                    activity_run_id,
                ),
            )


def track_activity(
    fn: Callable[..., Awaitable[Any]]
) -> Callable[..., Awaitable[Any]]:
    """
    Decorator for @activity.defn functions to log executions in activity_run.

    It records:
    - Temporal workflow_id and run_id
    - activity_type and activity_id
    - status: STARTED, COMPLETED, FAILED
    - full input arguments and returned result (as JSON)
    - error_message on failure
    """

    @wraps(fn)
    async def wrapper(*args, **kwargs):
        info = activity.info()
        workflow_id = info.workflow_id
        run_id = info.workflow_run_id
        activity_type = info.activity_type
        activity_id = info.activity_id

        # Serialize input as best-effort JSON
        try:
            input_data = {
                "args": args,
                "kwargs": kwargs,
            }
        except Exception:
            input_data = {"args": ["<unserializable>"], "kwargs": {}}

        activity_run_id = None
        try:
            activity_run_id = _insert_activity_run(
                workflow_id=workflow_id,
                run_id=run_id,
                activity_type=activity_type,
                activity_id=activity_id,
                status="STARTED",
                input_data=input_data,
            )
        except Exception as e:
            logger.warning(
                "Failed to insert activity_run row for %s: %s", activity_type, e
            )

        try:
            result = await fn(*args, **kwargs)

            if activity_run_id is not None:
                try:
                    _update_activity_run(
                        activity_run_id=activity_run_id,
                        status="COMPLETED",
                        result_data=result if isinstance(result, dict) else {"result": result},
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to update activity_run_id=%s as COMPLETED: %s",
                        activity_run_id,
                        e,
                    )

            return result

        except Exception as exc:
            if activity_run_id is not None:
                try:
                    _update_activity_run(
                        activity_run_id=activity_run_id,
                        status="FAILED",
                        error_message=str(exc),
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to update activity_run_id=%s as FAILED: %s",
                        activity_run_id,
                        e,
                    )
            raise

    return wrapper

