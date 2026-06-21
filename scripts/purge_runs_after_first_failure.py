#!/usr/bin/env python3
"""Stop active runs and delete all runs after the first failed run for a project."""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dashboard.backend.database import db_manager
from dashboard.backend.services.run_service import run_service

_COMPLETED = frozenset({"COMPLETED", "DONE", "PASSED"})
_FAILED = frozenset({"FAILED", "CANCELLED"})


async def _task_statuses_from_run(db, run_id: int) -> dict[int, str]:
    events = await run_service.list_run_events(db, run_id=run_id, limit=5000)
    statuses: dict[int, str] = {}
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


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_id", type=int, nargs="?", default=8)
    args = parser.parse_args()
    project_id = args.project_id

    await db_manager.initialize()
    try:
        running = await db_manager.fetch_many(
            """
            SELECT agent_run_id, project_id
            FROM main.agent_run
            WHERE UPPER(COALESCE(status, '')) = 'RUNNING'
            ORDER BY agent_run_id
            """
        )
        if running:
            print(f"Stopping {len(running)} active run(s)...")
            for row in running:
                rid = int(row["agent_run_id"])
                pid = int(row["project_id"])
                result = await run_service.cancel_run(db_manager, project_id=pid, run_id=rid)
                print(f"  run #{rid} project {pid}: {result}")
        else:
            print("No RUNNING runs.")

        first_failed = await db_manager.fetch_one(
            """
            SELECT agent_run_id, status
            FROM main.agent_run
            WHERE project_id = $1
              AND UPPER(COALESCE(status, '')) = 'FAILED'
            ORDER BY agent_run_id ASC
            LIMIT 1
            """,
            project_id,
        )
        if not first_failed:
            first_failed = await db_manager.fetch_one(
                """
                SELECT agent_run_id, status
                FROM main.agent_run
                WHERE project_id = $1
                  AND UPPER(COALESCE(status, '')) IN ('FAILED', 'CANCELLED')
                ORDER BY agent_run_id ASC
                LIMIT 1
                """,
                project_id,
            )
        if not first_failed:
            print(f"No failed/cancelled runs for project {project_id}.")
            return

        anchor_id = int(first_failed["agent_run_id"])
        print(f"Anchor run (first failure): #{anchor_id} ({first_failed['status']})")

        subsequent = await db_manager.fetch_many(
            """
            SELECT agent_run_id, status
            FROM main.agent_run
            WHERE project_id = $1 AND agent_run_id > $2
            ORDER BY agent_run_id
            """,
            project_id,
            anchor_id,
        )
        if not subsequent:
            print("No subsequent runs to delete.")
        else:
            print(f"Deleting {len(subsequent)} subsequent run(s)...")
            for row in subsequent:
                rid = int(row["agent_run_id"])
                result = await run_service.cleanup_run(
                    db_manager,
                    project_id=project_id,
                    run_id=rid,
                    delete_record=True,
                    created_by="purge-script",
                )
                print(f"  run #{rid}: ok={result.get('ok')} deleted={result.get('deleted')}")

        anchor_statuses = await _task_statuses_from_run(db_manager, anchor_id)
        if anchor_statuses:
            print(f"Restoring {len(anchor_statuses)} task status(es) from run #{anchor_id}...")
            for task_id, status in anchor_statuses.items():
                await run_service._update_task_status(db_manager, task_id=task_id, status=status)
                print(f"  task {task_id}: {status}")

        remaining = await db_manager.fetch_many(
            "SELECT agent_run_id, status FROM main.agent_run WHERE project_id = $1 ORDER BY agent_run_id",
            project_id,
        )
        print("Remaining runs:", [dict(r) for r in remaining])
    finally:
        await db_manager.close()


if __name__ == "__main__":
    asyncio.run(main())
