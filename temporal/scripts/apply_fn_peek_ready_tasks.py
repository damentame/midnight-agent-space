"""Apply main.fn_peek_ready_tasks to PostgreSQL (uses temporal/.env or project .env)."""
import sys
from pathlib import Path

parent = Path(__file__).resolve().parent.parent.parent
if str(parent) not in sys.path:
    sys.path.insert(0, str(parent))

from dotenv import load_dotenv
import os

load_dotenv(parent / "temporal" / ".env")
load_dotenv(parent / ".env")


def main() -> None:
    import psycopg2

    sql_path = parent / "MidnightAgentSpaceDB_dev" / "Functions" / "fn_peek_ready_tasks.sql"
    if not sql_path.is_file():
        raise SystemExit(f"Missing SQL file: {sql_path}")

    sql = sql_path.read_text(encoding="utf-8")
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "midnight_agent_space_dev"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
    )
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute('SET search_path TO main, public')
        cur.execute(sql)
    finally:
        cur.close()
        conn.close()
    print(f"OK: applied {sql_path.name} -> main.fn_peek_ready_tasks(bigint, bigint, integer)")


if __name__ == "__main__":
    main()
