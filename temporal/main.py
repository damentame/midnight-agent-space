"""Main entry point for Temporal document serialization."""
import sys
from pathlib import Path

# Add parent directory to path so we can import temporal module
parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

import asyncio
import argparse
import logging
from temporal.client import start_document_serialization, get_workflow_result
from temporal.config import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def run_workflow(
    agent_id: int,
    project_id: int,
    agent_provider: str = "cursor",
    concurrent_tasks: bool = False,
    execute_mode: str = "fast",
    batch_tasks: bool = False,
):
    """Run the document serialization workflow."""
    logger.info("Starting document serialization workflow")
    
    workflow_id = await start_document_serialization(
        agent_id=agent_id,
        project_id=project_id,
        agent_provider=agent_provider,
        concurrent_tasks=concurrent_tasks,
        execute_mode=execute_mode,
        batch_tasks=batch_tasks,
    )
    
    logger.info(f"Workflow started: {workflow_id}")
    logger.info("Waiting for workflow to complete...")
    
    result = await get_workflow_result(workflow_id)
    
    logger.info("Workflow completed!")
    logger.info(f"Results: {result}")
    
    return result


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Temporal Document Serialization Workflow"
    )
    parser.add_argument(
        "agent_id",
        type=int,
        help="Agent ID to use for serialization"
    )
    parser.add_argument(
        "project_id",
        type=int,
        help="Project ID to process documents for"
    )
    parser.add_argument(
        "--agent-provider",
        choices=["cursor", "codex", "claude-code"],
        default="cursor",
        help="Agent provider to use for task execution (default: cursor)"
    )
    parser.add_argument(
        "--concurrent-tasks",
        action="store_true",
        help="Enable concurrent task execution (default: off)",
    )
    parser.add_argument(
        "--execute-mode",
        choices=["fast", "complex"],
        default="fast",
        help="Model tier for serialization and task execution (default: fast)",
    )
    parser.add_argument(
        "--batch-tasks",
        "-b",
        action="store_true",
        dest="batch_tasks",
        help=(
            "After serialization, run task execution as one batched activity "
            "(fewer Temporal round-trips; not compatible with --concurrent-tasks)"
        ),
    )

    args = parser.parse_args()
    if args.concurrent_tasks and args.batch_tasks:
        parser.error("--concurrent-tasks and --batch-tasks cannot be used together")

    asyncio.run(
        run_workflow(
            args.agent_id,
            args.project_id,
            args.agent_provider,
            args.concurrent_tasks,
            args.execute_mode,
            args.batch_tasks,
        )
    )


if __name__ == "__main__":
    main()

