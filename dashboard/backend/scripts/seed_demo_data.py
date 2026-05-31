from __future__ import annotations

import asyncio
from pathlib import Path

import asyncpg

from dashboard.backend.config import get_database_dsn


async def seed_demo() -> None:
    root = Path(__file__).resolve().parents[3]
    sql_path = root / "MidnightAgentSpaceDB_dev" / "Tables" / "phase5_10_demo_seed.sql"
    sql_text = sql_path.read_text(encoding="utf-8")
    conn = await asyncpg.connect(get_database_dsn())
    try:
        await conn.execute(sql_text)
    finally:
        await conn.close()
    print(f"Seed complete using {sql_path}")


if __name__ == "__main__":
    asyncio.run(seed_demo())
