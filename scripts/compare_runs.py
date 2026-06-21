#!/usr/bin/env python3
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dashboard.backend.database import db_manager


async def main() -> None:
    run_ids = [int(x) for x in sys.argv[1:]]
    await db_manager.initialize()
    try:
        for rid in run_ids:
            st = await db_manager.fetch_val(
                "SELECT status FROM main.agent_run WHERE agent_run_id = $1", rid
            )
            count = await db_manager.fetch_val(
                "SELECT COUNT(*) FROM main.agent_event WHERE agent_run_id = $1", rid
            )
            last = await db_manager.fetch_one(
                """
                SELECT event_type, created_at
                FROM main.agent_event WHERE agent_run_id = $1
                ORDER BY agent_event_id DESC LIMIT 1
                """,
                rid,
            )
            print(
                f"run {rid}: status={st} events={count} "
                f"last={last['event_type'] if last else None} at {last['created_at'] if last else None}"
            )
    finally:
        await db_manager.close()


if __name__ == "__main__":
    asyncio.run(main())
