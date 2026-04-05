"""CLI script to print a detailed summary of a workflow_run.

Output includes workflow_run, events, activity_runs, and the full task list
for that run's project (task_list: id, name, type, status, priority, description, depends_on).

Usage:

  # Most recent workflow run (and its project's task list)
  python workflow_summary.py

  # Specific workflow_run_id
  python workflow_summary.py 123
"""

import json
import sys
from pathlib import Path

import psycopg2

# Ensure project root is on sys.path so `temporal.config` can be imported
parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

from temporal.config import config


def get_connection():
    db = config.database
    return psycopg2.connect(
        host=db.host,
        port=db.port,
        dbname=db.name,
        user=db.user,
        password=db.password,
    )


def get_latest_workflow_run_id(conn) -> int | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT workflow_run_id
            FROM main.workflow_run
            ORDER BY started_at DESC
            LIMIT 1
            """
        )
        row = cur.fetchone()
        return int(row[0]) if row else None


def get_workflow_run_summary(conn, workflow_run_id: int):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT main.fn_get_workflow_run_summary(%s);",
            (workflow_run_id,),
        )
        row = cur.fetchone()
        if not row or row[0] is None:
            return None
        return row[0]


def get_task_list_for_project(conn, project_id: int) -> list[dict]:
    """Return full task list (human-readable) for the given project_id."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                t.task_id,
                t.task_name,
                t.task_type,
                t.status,
                t.priority,
                t.description,
                t.created_at,
                (
                    SELECT string_agg(dep_task.task_name, ', ' ORDER BY dep_task.task_name)
                    FROM main.task_dependency td
                    JOIN main.task dep_task ON dep_task.task_id = td.depends_on_task_id
                    WHERE td.task_id = t.task_id
                ) AS depends_on
            FROM main.task t
            WHERE t.project_id = %s
            ORDER BY t.priority DESC NULLS LAST, t.created_at
            """,
            (project_id,),
        )
        columns = [d[0] for d in cur.description]
        rows = cur.fetchall()
    return [dict(zip(columns, row)) for row in rows]


def main(argv: list[str]) -> None:
    workflow_run_id: int | None = None

    if len(argv) > 1:
        try:
            workflow_run_id = int(argv[1])
        except ValueError:
            print(f"Invalid workflow_run_id: {argv[1]}")
            sys.exit(1)

    conn = get_connection()
    try:
        if workflow_run_id is None:
            workflow_run_id = get_latest_workflow_run_id(conn)
            if workflow_run_id is None:
                print("No workflow_run rows found in main.workflow_run")
                return

        summary = get_workflow_run_summary(conn, workflow_run_id)
        if summary is None:
            print(f"No summary found for workflow_run_id={workflow_run_id}")
            return

        # Attach full task list for this run's project (human-readable)
        project_id = summary.get("workflow_run", {}).get("project_id")
        if project_id is not None:
            summary["task_list"] = get_task_list_for_project(conn, project_id)
        else:
            summary["task_list"] = []

        print(
            json.dumps(
                summary,
                indent=2,
                default=str,
            )
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main(sys.argv)

