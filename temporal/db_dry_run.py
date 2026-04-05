import json
import sys
from pathlib import Path

# Ensure project root is on sys.path so `temporal.config` (and workflow_summary) can be imported
parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

from temporal.workflow_summary import get_connection


def main() -> None:
    conn = get_connection()
    conn.autocommit = False  # ensure we can roll back any changes
    cur = conn.cursor()

    print("=== Recent workflow_run rows (DocumentSerializationWorkflow + TaskExecutionWorkflow) ===")
    cur.execute(
        """
        SELECT workflow_run_id, workflow_name, project_id, agent_instance_id, status, started_at, finished_at
        FROM main.workflow_run
        WHERE workflow_name IN ('DocumentSerializationWorkflow', 'TaskExecutionWorkflow')
        ORDER BY workflow_run_id DESC
        LIMIT 10
        """
    )
    rows = cur.fetchall()
    print(json.dumps(rows, default=str, indent=2))

    print("\n=== Recent tasks for project_id=1 (including workflow_run_id in task_data) ===")
    cur.execute(
        """
        SELECT
          task_id,
          task_name,
          status,
          task_data->>'workflow_run_id' AS wf_run,
          task_data->>'batch_id' AS batch_id,
          created_at
        FROM main.task
        WHERE project_id = 1
        ORDER BY created_at DESC
        LIMIT 60
        """
    )
    rows = cur.fetchall()
    print(json.dumps(rows, default=str, indent=2))

    print("\n=== fn_get_next_ready_task(project_id=1, workflow_run_id) for workflow_run_ids present in task_data ===")
    cur.execute(
        """
        SELECT DISTINCT (task_data->>'workflow_run_id')::bigint AS wf_run
        FROM main.task
        WHERE project_id = 1
          AND task_data ? 'workflow_run_id'
          AND task_data->>'workflow_run_id' IS NOT NULL
        ORDER BY wf_run DESC
        LIMIT 10
        """
    )
    wf_runs = [r[0] for r in cur.fetchall() if r[0] is not None]
    print("workflow_run_ids found in task_data:", wf_runs)

    results_by_run: dict[int, object] = {}
    for wf_run in wf_runs:
        cur.execute(
            "SELECT main.fn_get_next_ready_task(%s, %s) AS result",
            (1, wf_run),
        )
        res = cur.fetchone()[0]
        results_by_run[int(wf_run)] = res

    print(json.dumps(results_by_run, default=str, indent=2))

    print("\n=== Dry-run simulation of sp_start_task_execution and sp_finish_task_execution ===")
    if wf_runs:
        newest = wf_runs[0]
        # Choose earliest created PENDING task for the newest workflow_run_id
        cur.execute(
            """
            SELECT task_id, task_name, status
            FROM main.task
            WHERE project_id = 1
              AND COALESCE(status, 'PENDING') = 'PENDING'
              AND (task_data->>'workflow_run_id')::bigint = %s
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (newest,),
        )
        row = cur.fetchone()
        if row:
            task_id, task_name, status = row
            print(f"\nCandidate task for wf_run_id={newest}: task_id={task_id}, name={task_name}, status={status}")

            # Show fn_get_next_ready_task result before any changes
            cur.execute(
                "SELECT main.fn_get_next_ready_task(%s, %s) AS result",
                (1, newest),
            )
            before_res = cur.fetchone()[0]
            print("fn_get_next_ready_task BEFORE start/finish:")
            print(json.dumps(before_res, default=str, indent=2))

            # Call sp_start_task_execution (dry run)
            print("\nCalling sp_start_task_execution (dry run)...")
            cur.execute(
                "CALL main.sp_start_task_execution(%s, %s, %s, %s)",
                (task_id, 2, 99999, "dry_run"),  # agent_id=2, fake agent_instance_id, created_by
            )
            cur.execute(
                "SELECT task_id, status, updated_at FROM main.task WHERE task_id = %s",
                (task_id,),
            )
            print("Task row AFTER sp_start_task_execution:")
            print(json.dumps(cur.fetchall(), default=str, indent=2))

            # Get the task_execution_id we just created
            cur.execute(
                """
                SELECT task_execution_id
                FROM main.task_execution
                WHERE task_id = %s
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (task_id,),
            )
            te_row = cur.fetchone()
            if te_row:
                te_id = te_row[0]
                print(f"\nCalling sp_finish_task_execution (dry run) for task_execution_id={te_id}...")
                cur.execute(
                    "CALL main.sp_finish_task_execution(%s, %s, %s::jsonb, %s, %s)",
                    (te_id, "COMPLETED", "{}", "dry_run logs", "dry_run"),
                )
                cur.execute(
                    "SELECT task_id, status, updated_at FROM main.task WHERE task_id = %s",
                    (task_id,),
                )
                print("Task row AFTER sp_finish_task_execution:")
                print(json.dumps(cur.fetchall(), default=str, indent=2))
            else:
                print("No task_execution row found after sp_start_task_execution; cannot test finish.")

            # Show fn_get_next_ready_task result after status changes (still in same transaction)
            cur.execute(
                "SELECT main.fn_get_next_ready_task(%s, %s) AS result",
                (1, newest),
            )
            after_res = cur.fetchone()[0]
            print("fn_get_next_ready_task AFTER start/finish (same transaction, before rollback):")
            print(json.dumps(after_res, default=str, indent=2))
        else:
            print("No PENDING tasks found for newest workflow_run_id in dry run.")
    else:
        print("No workflow_run_id values found in task_data for project 1.")

    print("\nRolling back dry-run transaction (no permanent changes).")
    conn.rollback()
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()

