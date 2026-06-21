#!/usr/bin/env python3
"""Compare Morning Glory project runs across V1/V2/V3."""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dashboard.backend.database import db_manager
from dashboard.backend.services.jsonb_utils import decode_jsonb_fields

PROJECT_IDS = [5, 7, 8]


def parse_ts(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def duration_minutes(start: Optional[datetime], end: Optional[datetime]) -> Optional[float]:
    if not start or not end:
        return None
    return round((end - start).total_seconds() / 60, 1)


async def analyze_run(db, run_id: int) -> Dict[str, Any]:
    run = await db.fetch_one("SELECT * FROM main.agent_run WHERE agent_run_id = $1", run_id)
    if not run:
        return {}
    run = decode_jsonb_fields(dict(run), ("request_payload", "context_pack", "result_payload"))
    events = await db.fetch_many(
        """
        SELECT event_type, event_payload, created_at
        FROM main.agent_event WHERE agent_run_id = $1 ORDER BY agent_event_id
        """,
        run_id,
    )
    task_started: Dict[int, datetime] = {}
    task_ended: Dict[int, datetime] = {}
    task_names: Dict[int, str] = {}
    batch_events: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    skips = 0
    for row in events:
        et = str(row["event_type"])
        payload = row["event_payload"]
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {}
        if not isinstance(payload, dict):
            payload = {}
        ts = parse_ts(row["created_at"])
        tid = int(payload.get("task_id") or 0)
        if tid > 0 and payload.get("task_name"):
            task_names[tid] = str(payload["task_name"])
        if et == "TASK_STARTED" and tid > 0 and tid not in task_started:
            task_started[tid] = ts
        if et in {"TASK_COMPLETED", "TASK_FAILED"} and tid > 0:
            task_ended[tid] = ts
        if et == "TASK_COMPLETED" and payload.get("skipped"):
            skips += 1
        if et == "TASK_FAILED":
            failures.append(
                {
                    "task_id": tid,
                    "task_name": payload.get("task_name"),
                    "message": payload.get("message") or payload.get("error"),
                    "skipped": payload.get("skipped"),
                }
            )
        if "BATCH" in et:
            batch_events.append({"type": et, "payload": payload, "at": str(row["created_at"])})

    run_started = parse_ts(
        await db.fetch_val(
            "SELECT MIN(created_at) FROM main.agent_event WHERE agent_run_id=$1 AND event_type='RUN_STARTED'",
            run_id,
        )
    )
    run_ended = parse_ts(
        await db.fetch_val(
            """
            SELECT MAX(created_at) FROM main.agent_event
            WHERE agent_run_id=$1 AND event_type IN ('RUN_COMPLETED','RUN_FAILED','RUN_CANCELLED')
            """,
            run_id,
        )
    )
    if not run_ended:
        run_ended = parse_ts(
            await db.fetch_val(
                "SELECT MAX(created_at) FROM main.agent_event WHERE agent_run_id=$1",
                run_id,
            )
        )

    task_durations = []
    for tid, start in task_started.items():
        end = task_ended.get(tid)
        if start and end:
            task_durations.append(
                {
                    "task_id": tid,
                    "task_name": task_names.get(tid, ""),
                    "minutes": round((end - start).total_seconds() / 60, 1),
                }
            )

    rp = run.get("result_payload") or {}
    worktree = (rp.get("worktree") or {}) if isinstance(rp, dict) else {}
    req = run.get("request_payload") or {}
    exec_params = req.get("execution_parameters") or {} if isinstance(req, dict) else {}

    return {
        "run_id": run_id,
        "status": run.get("status"),
        "runtime_provider": run.get("runtime_provider"),
        "event_count": len(events),
        "run_minutes": duration_minutes(run_started, run_ended),
        "run_started": str(run_started) if run_started else None,
        "run_ended": str(run_ended) if run_ended else None,
        "task_completed_events": sum(1 for e in events if e["event_type"] == "TASK_COMPLETED"),
        "task_failed_events": sum(1 for e in events if e["event_type"] == "TASK_FAILED"),
        "task_skipped": skips,
        "batch_events": batch_events,
        "failures": failures,
        "task_durations": sorted(task_durations, key=lambda x: x["minutes"], reverse=True),
        "execution_parameters": exec_params,
        "worktree": worktree,
        "result_warnings": rp.get("warnings") if isinstance(rp, dict) else None,
        "result_errors": rp.get("errors") if isinstance(rp, dict) else None,
        "review": (rp.get("review") or {}) if isinstance(rp, dict) else {},
    }


async def project_metadata(db, project_id: int) -> Dict[str, Any]:
    from dashboard.backend.services.project_metadata_service import project_metadata_service

    meta = await project_metadata_service.get_project_metadata(db, project_id)
    prefs = meta.get("runtime_preferences") or {}
    md = meta.get("metadata") or {}
    plan = md.get("last_analysis_plan") or {}
    batches = plan.get("execution_batches") or prefs.get("execution_parameters", {}).get("execution_batches")
    return {
        "execution_batches": batches,
        "execution_parameters": prefs.get("execution_parameters"),
        "design_asset_count": md.get("design_asset_count"),
        "rag_ready_document_count": md.get("rag_ready_document_count"),
    }


async def main() -> None:
    await db_manager.initialize()
    report: Dict[str, Any] = {"projects": {}}
    try:
        for pid in PROJECT_IDS:
            project = await db_manager.fetch_one(
                "SELECT project_id, project_name, created_at, updated_at FROM main.project WHERE project_id=$1",
                pid,
            )
            if not project:
                continue
            runs = await db_manager.fetch_many(
                """
                SELECT agent_run_id FROM main.agent_run WHERE project_id=$1 ORDER BY agent_run_id
                """,
                pid,
            )
            tasks = await db_manager.fetch_many(
                """
                SELECT task_id, task_name, status, priority, task_data
                FROM main.task WHERE project_id=$1 AND COALESCE(status,'') <> 'SUPERSEDED'
                ORDER BY priority, task_id
                """,
                pid,
            )
            analyzed_runs = []
            for row in runs:
                analyzed_runs.append(await analyze_run(db_manager, int(row["agent_run_id"])))
            report["projects"][str(pid)] = {
                "project": dict(project),
                "metadata": await project_metadata(db_manager, pid),
                "tasks": [
                    {
                        "task_id": t["task_id"],
                        "task_name": t["task_name"],
                        "status": t["status"],
                        "execution_mode": (
                            (json.loads(t["task_data"]) if isinstance(t["task_data"], str) else t["task_data"] or {})
                            .get("execution_mode")
                        ),
                        "parallel_group": (
                            (json.loads(t["task_data"]) if isinstance(t["task_data"], str) else t["task_data"] or {})
                            .get("parallel_group")
                        ),
                    }
                    for t in tasks
                ],
                "runs": analyzed_runs,
            }
        out = ROOT / "scripts" / "morningglory_comparison.json"
        out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(out.read_text(encoding="utf-8"))
    finally:
        await db_manager.close()


if __name__ == "__main__":
    asyncio.run(main())
