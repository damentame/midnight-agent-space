"""CLI to run the Task Execution workflow (build project from BA-defined tasks)."""
import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to path
parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

from temporal.client import start_task_execution_workflow
from temporal.config import config


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run TaskExecutionWorkflow against DB-backed tasks."
    )
    parser.add_argument("project_id", type=int)
    parser.add_argument("agent_id", type=int, help="Task Executor agent id")
    parser.add_argument("agent_instance_id", type=int)
    parser.add_argument(
        "max_tasks",
        type=int,
        nargs="?",
        default=50,
        help="Maximum tasks to run (default 50)",
    )
    parser.add_argument(
        "--workspace-root",
        default=None,
        help="Workspace root; defaults to WORKSPACE_ROOT env or config",
    )
    parser.add_argument(
        "--agent-provider",
        choices=["cursor", "codex", "claude-code"],
        default="cursor",
    )
    parser.add_argument(
        "--require-human-review",
        action="store_true",
        help="Leave task branches unmerged for manual review",
    )
    parser.add_argument(
        "--concurrent-tasks",
        action="store_true",
        help="Run tasks as concurrent child workflows (default: off)",
    )
    parser.add_argument(
        "--execute-mode",
        choices=["fast", "complex"],
        default="fast",
    )
    parser.add_argument(
        "--batch-tasks",
        action="store_true",
        help="Run task execution as one batched activity",
    )
    args = parser.parse_args()
    if args.concurrent_tasks and args.batch_tasks:
        parser.error("--concurrent-tasks and --batch-tasks cannot be used together")

    workspace_root = args.workspace_root or (config.temporal.workspace_root or None)

    workflow_id = asyncio.run(
        start_task_execution_workflow(
            project_id=args.project_id,
            agent_id=args.agent_id,
            agent_instance_id=args.agent_instance_id,
            max_tasks=args.max_tasks,
            workspace_root=workspace_root,
            require_human_review=args.require_human_review,
            agent_provider=args.agent_provider,
            concurrent_tasks=args.concurrent_tasks,
            execute_mode=args.execute_mode,
            batch_tasks=args.batch_tasks,
        )
    )
    print(f"TaskExecutionWorkflow started: {workflow_id}")
    print("Monitor in Temporal UI (e.g. http://localhost:8080) or use workflow_summary.py for DB summary.")


if __name__ == "__main__":
    main()
