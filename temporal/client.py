"""Temporal client for starting workflows."""
import sys
from pathlib import Path

# Add parent directory to path so we can import temporal module
parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

import asyncio
import logging
from temporalio.client import Client
from temporal.workflows.document_serialization_workflow import (
    DocumentSerializationWorkflow,
    DocumentSerializationInput,
)
from temporal.workflows.task_execution_workflow import (
    TaskExecutionWorkflow,
    TaskExecutionInput,
)
from temporal.config import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def start_document_serialization(
    agent_id: int,
    project_id: int,
    agent_provider: str = "cursor",
    require_human_review: bool = False,
    concurrent_tasks: bool = False,
    execute_mode: str = "fast",
    batch_tasks: bool = False,
) -> str:
    """
    Start a document serialization workflow.
    
    Args:
        agent_id: Agent ID to use
        project_id: Project ID to process documents for
        agent_provider: Which agent provider to use for task execution
                        (\"cursor\", \"codex\", or \"claude-code\")
        require_human_review: When True, leaves task branches unmerged for manual review.
        concurrent_tasks: When True, run task execution phase with concurrent per-task child workflows.
        execute_mode: "fast" or "complex" for model selection in serialization and task execution.
        batch_tasks: When True, run task execution as one batched activity (not with concurrent_tasks).
        
    Returns:
        Workflow run ID
    """
    logger.info(f"Connecting to Temporal at {config.temporal.address}")
    client = await Client.connect(
        target_host=config.temporal.address,
        namespace=config.temporal.namespace,
        tls=False  # Disable TLS for local development
    )
    
    workflow_input = DocumentSerializationInput(
        agent_id=agent_id,
        project_id=project_id,
        agent_provider=agent_provider,
        require_human_review=require_human_review,
        concurrent_tasks=concurrent_tasks,
        execute_mode=execute_mode,
        batch_tasks=batch_tasks,
    )
    
    logger.info(
        f"Starting workflow: agent_id={agent_id}, project_id={project_id}, "
        f"agent_provider={agent_provider}, require_human_review={require_human_review}"
    )
    
    handle = await client.start_workflow(
        DocumentSerializationWorkflow.run,
        workflow_input,
        id=f"document-serialization-{project_id}-{agent_id}",
        task_queue="document-serialization-queue",
    )
    
    logger.info(f"Workflow started: {handle.id}")
    return handle.id


async def start_task_execution_workflow(
    project_id: int,
    agent_id: int,
    agent_instance_id: int,
    max_tasks: int = 50,
    workspace_root: str | None = None,
    branch_workflow_run_id: int | None = None,
    require_human_review: bool = False,
    agent_provider: str = "cursor",
    concurrent_tasks: bool = False,
    execute_mode: str = "fast",
    batch_tasks: bool = False,
) -> str:
    """
    Start the Task Execution workflow (Task Executor builds the project from BA-defined tasks).

    Args:
        project_id: Project ID
        agent_id: Task Executor agent ID
        agent_instance_id: Agent instance ID
        max_tasks: Maximum tasks to execute in this run (default 50)
        workspace_root: Path to codebase (default from config.temporal.workspace_root)
        branch_workflow_run_id: Optional workflow_run_id to use for branch naming/merging.
        require_human_review: When True, leaves task branches unmerged for manual review.

    Returns:
        Workflow run ID
    """
    logger.info("Connecting to Temporal at %s", config.temporal.address)
    client = await Client.connect(
        target_host=config.temporal.address,
        namespace=config.temporal.namespace,
        tls=False,
    )
    root = workspace_root or config.temporal.workspace_root or ""
    workflow_input = TaskExecutionInput(
        project_id=project_id,
        agent_id=agent_id,
        agent_instance_id=agent_instance_id,
        max_tasks=max_tasks,
        workspace_root=root or None,
        branch_workflow_run_id=branch_workflow_run_id,
        require_human_review=require_human_review,
        agent_provider=agent_provider,
        concurrent_tasks=concurrent_tasks,
        execute_mode=execute_mode,
        batch_tasks=batch_tasks,
    )
    logger.info(
        "Starting TaskExecutionWorkflow: project_id=%s agent_id=%s agent_instance_id=%s max_tasks=%s",
        project_id,
        agent_id,
        agent_instance_id,
        max_tasks,
    )
    handle = await client.start_workflow(
        TaskExecutionWorkflow.run,
        workflow_input,
        id=f"task-execution-{project_id}-{agent_id}",
        task_queue="task-execution-queue",
    )
    logger.info("TaskExecutionWorkflow started: %s", handle.id)
    return handle.id


async def get_workflow_result(workflow_id: str):
    """Get the result of a workflow execution."""
    client = await Client.connect(
        target_host=config.temporal.address,
        namespace=config.temporal.namespace
    )
    
    handle = client.get_workflow_handle(workflow_id)
    result = await handle.result()
    
    return result


if __name__ == "__main__":
    # Example usage
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python client.py <agent_id> <project_id> [agent_provider] [require_human_review] [concurrent_tasks]")
        print("  agent_provider: cursor | codex | claude-code (default: cursor)")
        sys.exit(1)
    
    agent_id = int(sys.argv[1])
    project_id = int(sys.argv[2])
    agent_provider = sys.argv[3].lower() if len(sys.argv) > 3 else "cursor"
    require_human_review = sys.argv[4].lower() == "true" if len(sys.argv) > 4 else False
    concurrent_tasks = sys.argv[5].lower() == "true" if len(sys.argv) > 5 else False
    
    workflow_id = asyncio.run(
        start_document_serialization(
            agent_id,
            project_id,
            agent_provider,
            require_human_review,
            concurrent_tasks,
        )
    )
    print(f"Workflow started: {workflow_id}")

