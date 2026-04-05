"""
Temporal client helpers: fetch workflow history and normalize activity events for the dashboard.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from temporalio.api.enums.v1 import EventType
from temporalio.client import Client, WorkflowExecutionStatus

from .config import temporal_config

logger = logging.getLogger(__name__)

_client: Optional[Client] = None
_client_lock = asyncio.Lock()


async def get_temporal_client() -> Client:
    global _client
    async with _client_lock:
        if _client is None:
            _client = await Client.connect(
                target_host=temporal_config.host + ":" + str(temporal_config.port),
                namespace=temporal_config.namespace,
                tls=False,
            )
        return _client


def _decode_payload_data(data: bytes) -> str:
    if not data:
        return ""
    try:
        s = data.decode("utf-8", errors="replace")
    except Exception:
        return repr(data[:200])
    s = s.strip()
    if len(s) > 800:
        return s[:800] + "…"
    return s


def _summarize_payloads(payloads_container: Any) -> str:
    if not payloads_container or not getattr(payloads_container, "payloads", None):
        return ""
    parts: List[str] = []
    for p in payloads_container.payloads:
        parts.append(_decode_payload_data(bytes(p.data)))
    return " | ".join(parts) if parts else ""


def _status_name(status: WorkflowExecutionStatus) -> str:
    try:
        return status.name
    except Exception:
        return str(int(status))


def parse_history_to_activities(history: Any) -> List[Dict[str, Any]]:
    """
    Build a list of activity rows keyed by scheduled_event_id (Temporal history event id
    of EVENT_TYPE_ACTIVITY_TASK_SCHEDULED).
    """
    by_sched: Dict[int, Dict[str, Any]] = {}

    for e in history.events:
        et = e.event_type
        name = EventType.Name(et)

        if name == "EVENT_TYPE_ACTIVITY_TASK_SCHEDULED":
            sid = e.event_id
            attrs = e.activity_task_scheduled_event_attributes
            at = attrs.activity_type
            activity_name = at.name if at else "activity"
            row: Dict[str, Any] = {
                "scheduled_event_id": sid,
                "activity_name": activity_name,
                "activity_id": str(attrs.activity_id),
                "input_summary": _summarize_payloads(attrs.input),
                "status": "scheduled",
            }
            by_sched[sid] = row

        elif name == "EVENT_TYPE_ACTIVITY_TASK_STARTED":
            sid = e.activity_task_started_event_attributes.scheduled_event_id
            if sid in by_sched:
                by_sched[sid]["status"] = "running"

        elif name == "EVENT_TYPE_ACTIVITY_TASK_COMPLETED":
            attrs = e.activity_task_completed_event_attributes
            sid = attrs.scheduled_event_id
            if sid in by_sched:
                by_sched[sid]["status"] = "completed"
                by_sched[sid]["output_summary"] = _summarize_payloads(attrs.result)

        elif name == "EVENT_TYPE_ACTIVITY_TASK_FAILED":
            attrs = e.activity_task_failed_event_attributes
            sid = attrs.scheduled_event_id
            if sid in by_sched:
                by_sched[sid]["status"] = "failed"
                failure = attrs.failure
                msg = ""
                if failure:
                    msg = failure.message or str(failure)
                by_sched[sid]["error"] = msg[:2000]

        elif name == "EVENT_TYPE_ACTIVITY_TASK_TIMED_OUT":
            try:
                attrs = e.activity_task_timed_out_event_attributes
                sid = attrs.scheduled_event_id
                if sid in by_sched:
                    by_sched[sid]["status"] = "timed_out"
            except AttributeError:
                pass

    # Stable order by scheduled_event_id
    return [by_sched[k] for k in sorted(by_sched.keys())]


async def fetch_workflow_snapshot(workflow_id: str, run_id: Optional[str] = None) -> Dict[str, Any]:
    client = await get_temporal_client()
    handle = client.get_workflow_handle(workflow_id, run_id=run_id)
    desc = await handle.describe()
    hist = await handle.fetch_history()
    activities = parse_history_to_activities(hist)
    return {
        "workflow_id": desc.id,
        "run_id": desc.run_id,
        "workflow_type": desc.workflow_type,
        "status": _status_name(desc.status),
        "task_queue": desc.task_queue,
        "history_event_count": len(hist.events),
        "activities": activities,
    }


async def list_recent_workflows(page_size: int = 50) -> List[Dict[str, Any]]:
    client = await get_temporal_client()
    out: List[Dict[str, Any]] = []
    async for we in client.list_workflows(page_size=page_size):
        st = we.status if we.status is not None else None
        out.append(
            {
                "workflow_id": we.id,
                "run_id": we.run_id,
                "workflow_type": we.workflow_type or "",
                "status": _status_name(st) if st is not None else "",
                "start_time": we.start_time.isoformat() if we.start_time else None,
                "close_time": we.close_time.isoformat() if we.close_time else None,
                "task_queue": we.task_queue or "",
            }
        )
    return out
