#!/usr/bin/env python3
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dashboard.backend.database import db_manager


async def main() -> None:
    project_id = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    await db_manager.initialize()
    try:
        run = await db_manager.fetch_one(
            """
            SELECT agent_run_id, project_id, status, started_at, request_payload
            FROM main.agent_run WHERE project_id=$1 ORDER BY agent_run_id DESC LIMIT 1
            """,
            project_id,
        )
        print("Latest run:", dict(run) if run else None)
        run_id = int(run["agent_run_id"]) if run else 0

        tasks = await db_manager.fetch_many(
            """
            SELECT task_id, task_name, status, priority, task_data
            FROM main.task WHERE project_id=$1 AND COALESCE(status,'') <> 'SUPERSEDED'
            ORDER BY priority, task_id
            """,
            project_id,
        )
        print("\nTasks:")
        parallel_count = 0
        for t in tasks:
            td = t["task_data"]
            if isinstance(td, str):
                try:
                    td = json.loads(td)
                except Exception:
                    td = {}
            pg = td.get("parallel_group") if isinstance(td, dict) else None
            if pg == "sections":
                parallel_count += 1
            print(f"  [{t['status']}] p{t['priority']} id={t['task_id']} {t['task_name']} parallel_group={pg}")

        print(f"\nSection tasks with parallel_group: {parallel_count}")

        if run_id:
            events = await db_manager.fetch_many(
                """
                SELECT event_type, event_payload, created_at
                FROM main.agent_run_event
                WHERE agent_run_id=$1
                ORDER BY agent_event_id
                """,
                run_id,
            )
            batch = [
                e
                for e in events
                if str(e["event_type"]) in {"TASK_BATCH_STARTED", "TASK_BATCH_COMPLETED", "TASK_BATCH_FAILED"}
            ]
            started = [e for e in events if e["event_type"] == "TASK_STARTED"]
            print(f"\nTASK_STARTED events: {len(started)}")
            print(f"Batch events: {len(batch)}")
            for e in batch:
                print(f"  {e['event_type']}: {e['event_payload']}")

            rp = run.get("request_payload")
            if isinstance(rp, str):
                rp = json.loads(rp)
            print("\nRun execution_parameters:", (rp or {}).get("execution_parameters") if isinstance(rp, dict) else None)
    finally:
        await db_manager.close()


if __name__ == "__main__":
    asyncio.run(main())
