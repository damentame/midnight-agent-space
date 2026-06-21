#!/usr/bin/env python3
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dashboard.backend.database import db_manager


def payload_summary(payload) -> str:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            return payload[:500]
    if not isinstance(payload, dict):
        return str(payload)[:500]
    for key in ("message", "error", "detail", "reason", "stderr", "stdout_tail"):
        val = payload.get(key)
        if val:
            return str(val)[:500]
    slim = {k: v for k, v in payload.items() if k not in ("request_payload", "context_pack", "rag_ready_context")}
    return json.dumps(slim, default=str)[:500]


async def main() -> None:
    project_id = int(sys.argv[1]) if len(sys.argv) > 1 else None
    await db_manager.initialize()
    try:
        if project_id:
            run = await db_manager.fetch_one(
                """
                SELECT agent_run_id, project_id, status, started_at, result_payload
                FROM main.agent_run WHERE project_id=$1 ORDER BY agent_run_id DESC LIMIT 1
                """,
                project_id,
            )
        else:
            run = await db_manager.fetch_one(
                """
                SELECT agent_run_id, project_id, status, started_at, result_payload
                FROM main.agent_run ORDER BY agent_run_id DESC LIMIT 1
                """
            )
        if not run:
            print("No runs found")
            return
        rid = int(run["agent_run_id"])
        pid = int(run["project_id"])
        print(f"Latest run: id={rid} project={pid} status={run['status']}")

        tasks = await db_manager.fetch_many(
            """
            SELECT task_id, task_name, status, priority
            FROM main.task WHERE project_id=$1 AND COALESCE(status,'') <> 'SUPERSEDED'
            ORDER BY priority, task_id
            """,
            pid,
        )
        print("\nTasks:")
        for t in tasks:
            print(f"  [{t['status']}] id={t['task_id']} {t['task_name']}")

        events = await db_manager.fetch_many(
            """
            SELECT event_type, event_payload, created_at
            FROM main.agent_event WHERE agent_run_id=$1 ORDER BY agent_event_id
            """,
            rid,
        )
        print(f"\nTotal events: {len(events)}")

        for et in ("TASK_BATCH_STARTED", "TASK_BATCH_COMPLETED", "TASK_BATCH_PARTIAL", "TASK_BATCH_FAILED"):
            matches = [e for e in events if e["event_type"] == et]
            if matches:
                print(f"\n{et}:")
                for e in matches:
                    print(f"  {payload_summary(e['event_payload'])}")

        failed = [e for e in events if e["event_type"] in ("TASK_FAILED", "RUN_FAILED", "ERROR")]
        print(f"\nFailure events ({len(failed)}):")
        for e in failed:
            p = e["event_payload"]
            if isinstance(p, str):
                try:
                    p = json.loads(p)
                except Exception:
                    p = {}
            task_name = ""
            if isinstance(p, dict):
                task_name = str(p.get("task_name") or p.get("task_id") or "")
            print(f"  {e['event_type']} {task_name}: {payload_summary(p)}")

        rp = run.get("result_payload")
        if isinstance(rp, str):
            try:
                rp = json.loads(rp)
            except Exception:
                rp = {}
        if isinstance(rp, dict) and rp:
            print(f"\nResult payload summary: {payload_summary(rp)}")
    finally:
        await db_manager.close()


if __name__ == "__main__":
    asyncio.run(main())
