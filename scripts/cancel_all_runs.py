#!/usr/bin/env python3
"""Cancel all RUNNING agent runs via the dashboard API."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dashboard.backend.database import db_manager


async def main() -> None:
    project_id = int(sys.argv[1]) if len(sys.argv) > 1 else None
    await db_manager.initialize()
    try:
        if project_id:
            rows = await db_manager.fetch_many(
                """
                SELECT agent_run_id, project_id, status
                FROM main.agent_run
                WHERE project_id = $1 AND UPPER(COALESCE(status, '')) = 'RUNNING'
                ORDER BY agent_run_id
                """,
                project_id,
            )
        else:
            rows = await db_manager.fetch_many(
                """
                SELECT agent_run_id, project_id, status
                FROM main.agent_run
                WHERE UPPER(COALESCE(status, '')) = 'RUNNING'
                ORDER BY agent_run_id
                """
            )
        if not rows:
            print("No RUNNING runs found.")
            return
        print(f"Marking {len(rows)} stale RUNNING run(s) as CANCELLED...")
        for row in rows:
            run_id = int(row["agent_run_id"])
            pid = int(row["project_id"])
            await db_manager.execute(
                """
                UPDATE main.agent_run
                SET status = 'CANCELLED',
                    result_payload = COALESCE(result_payload, '{}'::jsonb) || '{"cancelled": true}'::jsonb,
                    finished_at = NOW(),
                    updated_at = NOW()
                WHERE agent_run_id = $1
                """,
                run_id,
            )
            print(f"  run #{run_id} (project {pid}): CANCELLED")
    finally:
        await db_manager.close()


if __name__ == "__main__":
    asyncio.run(main())
