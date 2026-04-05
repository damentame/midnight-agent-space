#!/usr/bin/env python3
"""
Persist tasks from a JSON file to main.task and main.task_dependency.

Use for testing the executor flow or manual recovery when Cursor agent
task extraction fails. Expects JSON with {"tasks": [...]}.

Usage:
    python -m temporal.scripts.persist_tasks \
        --project-id 1 --document-id 1 --agent-id 2 --agent-instance-id 1 \
        --file tasks.json
"""
import argparse
import json
import logging
import sys
from pathlib import Path

# Ensure temporal package is importable when run as script
_temporal_root = Path(__file__).resolve().parent.parent
if str(_temporal_root.parent) not in sys.path:
    sys.path.insert(0, str(_temporal_root.parent))

from temporal.utils.db import get_connection, init_pool

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Persist tasks from JSON file to database")
    parser.add_argument("--project-id", type=int, required=True, help="Project ID")
    parser.add_argument("--document-id", type=int, required=True, help="Document ID")
    parser.add_argument("--agent-id", type=int, required=True, help="Agent ID")
    parser.add_argument("--agent-instance-id", type=int, required=True, help="Agent instance ID")
    parser.add_argument("--file", type=Path, required=True, help="Path to JSON file with {\"tasks\": [...]}")
    parser.add_argument("--batch-id", type=str, default=None, help="Optional batch ID for idempotency")
    args = parser.parse_args()

    path = args.file
    if not path.exists():
        logger.error("File not found: %s", path)
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        logger.error("JSON root must be an object, got %s", type(data).__name__)
        sys.exit(1)

    tasks_arr = data.get("tasks") or data.get("task_list") or data.get("items")
    if not isinstance(tasks_arr, list):
        logger.error("JSON must contain 'tasks', 'task_list', or 'items' array, got %s", type(tasks_arr).__name__)
        sys.exit(1)

    if not tasks_arr:
        logger.warning("Tasks array is empty, nothing to persist")
        sys.exit(0)

    tasks_json = {"tasks": tasks_arr}
    batch_id = args.batch_id

    init_pool()
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CALL main.sp_persist_generated_tasks(
                        %s, %s, %s, %s, %s::jsonb, %s, %s
                    )
                    """,
                    (
                        args.project_id,
                        args.document_id,
                        args.agent_id,
                        args.agent_instance_id,
                        json.dumps(tasks_json),
                        batch_id,
                        "system",
                    ),
                )
        logger.info(
            "Persisted %s tasks for project_id=%s, document_id=%s",
            len(tasks_arr),
            args.project_id,
            args.document_id,
        )
    except Exception as e:
        logger.error("Failed to persist tasks: %s", e)
        raise


if __name__ == "__main__":
    main()
