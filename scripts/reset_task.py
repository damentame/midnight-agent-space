"""Reset a task status (dev utility)."""
import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dashboard.backend.database import db_manager


async def main() -> None:
    task_id = int(sys.argv[1])
    status = sys.argv[2] if len(sys.argv) > 2 else "QUEUED"
    await db_manager.execute(
        "UPDATE main.task SET status = $1, updated_at = NOW() WHERE task_id = $2",
        status,
        task_id,
    )
    print(f"task {task_id} -> {status}")


if __name__ == "__main__":
    asyncio.run(main())
