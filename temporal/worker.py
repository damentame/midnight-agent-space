"""Temporal worker for document serialization workflows."""
import sys
import os
from pathlib import Path

# Add parent directory to path so we can import temporal module
parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

# Load .env file BEFORE importing config to ensure environment variables are set
# This must happen outside the workflow sandbox
from dotenv import load_dotenv
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path, override=True)
else:
    load_dotenv(override=True)

import asyncio
import logging
from temporalio.client import Client
from temporalio.worker import Worker
from temporalio.worker import UnsandboxedWorkflowRunner

from temporal.workflows.document_serialization_workflow import DocumentSerializationWorkflow
from temporal.workflows.task_execution_workflow import (
    TaskExecutionWorkflow,
    SingleTaskExecutionWorkflow,
)
from temporal.activities.agent_activities import (
    spin_up_agent_activity,
    prepare_agent_prompt_activity,
    prepare_agent_prompt_with_rag_activity,
    ensure_agents_from_roles_activity,
    start_workflow_run_activity,
    finish_workflow_run_activity,
)
from temporal.activities.document_activities import (
    get_project_documents_activity,
    chunk_document_activity,
    generate_embeddings_activity,
    store_vectors_activity,
    update_document_serialization_activity,
    retrieve_rag_context_activity,
)
from temporal.activities.api_activities import (
    create_cursor_agent_activity,
    serialize_document_cursor_activity,
    serialize_document_codex_activity,
    serialize_document_local_activity,
    poll_cursor_agent_status_activity,
    get_cursor_agent_results_activity,
    persist_generated_tasks_activity,
    decommission_cursor_agent_activity,
)
from temporal.activities.task_execution_activities import (
    get_next_ready_task_activity,
    start_task_execution_activity,
    finish_task_execution_activity,
    log_task_step_activity,
    execute_task_with_agent_activity,
    execute_task_with_cursor_activity,
    execute_task_batch_activity,
    execute_tasks_concurrent_claude_code_activity,
    index_code_context_activity,
    ensure_workflow_develop_branch_activity,
    merge_task_branch_into_develop_activity,
)
from temporal.utils.db import init_pool, close_pool
from temporal.config import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    force=True  # Override any existing configuration
)

# Set activity loggers to show full tracebacks
logging.getLogger("temporal.activities").setLevel(logging.DEBUG)
logger = logging.getLogger(__name__)


async def main():
    """Run the Temporal worker."""
    logger.info("Initializing database connection pool")
    init_pool()
    
    logger.info(f"Connecting to Temporal at {config.temporal.address}")
    logger.info("Waiting 5 seconds for Temporal server to be fully ready...")
    await asyncio.sleep(5)  # Give Temporal server time to fully initialize
    
    # Retry connection with exponential backoff
    # Temporal server may need time to fully initialize
    max_retries = 10
    retry_delay = 3
    
    client = None
    for attempt in range(max_retries):
        try:
            logger.info(f"Connection attempt {attempt + 1}/{max_retries}...")
            # Connect to Temporal (no TLS for local development)
            client = await Client.connect(
                target_host=config.temporal.address,
                namespace=config.temporal.namespace,
                tls=False  # Disable TLS for local development
            )
            logger.info("Successfully connected to Temporal!")
            break
        except Exception as e:
            error_msg = str(e)
            if len(error_msg) > 200:
                error_msg = error_msg[:200] + "..."
            
            if attempt < max_retries - 1:
                logger.warning(f"Connection attempt {attempt + 1} failed: {error_msg}")
                logger.info(f"Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
                retry_delay = min(int(retry_delay * 1.5), 10)  # Cap at 10 seconds
            else:
                logger.error(f"Failed to connect to Temporal after {max_retries} attempts")
                logger.error("Troubleshooting steps:")
                logger.error("  1. Check Temporal is running: docker ps | findstr temporal")
                logger.error("  2. Check Temporal logs: docker logs temporal-server")
                logger.error("  3. Wait 30-60 seconds after starting Temporal for full initialization")
                logger.error("  4. Verify port 7233 is accessible")
                logger.error("  5. Try restarting Temporal: docker-compose -f temporal/docker-compose.temporal.yml restart")
                raise
    
    if not client:
        raise RuntimeError("Failed to establish Temporal connection")
    
    logger.info("Starting Temporal workers (document-serialization + task-execution)")
    all_activities = [
        spin_up_agent_activity,
        prepare_agent_prompt_activity,
        prepare_agent_prompt_with_rag_activity,
        ensure_agents_from_roles_activity,
        start_workflow_run_activity,
        finish_workflow_run_activity,
        get_project_documents_activity,
        chunk_document_activity,
        generate_embeddings_activity,
        store_vectors_activity,
        update_document_serialization_activity,
        retrieve_rag_context_activity,
        create_cursor_agent_activity,
        serialize_document_cursor_activity,
        serialize_document_codex_activity,
        serialize_document_local_activity,
        poll_cursor_agent_status_activity,
        get_cursor_agent_results_activity,
        persist_generated_tasks_activity,
        decommission_cursor_agent_activity,
        get_next_ready_task_activity,
        start_task_execution_activity,
        finish_task_execution_activity,
        log_task_step_activity,
        execute_task_with_agent_activity,
        execute_task_with_cursor_activity,
        execute_task_batch_activity,
        execute_tasks_concurrent_claude_code_activity,
        index_code_context_activity,
        ensure_workflow_develop_branch_activity,
        merge_task_branch_into_develop_activity,
    ]
    # UnsandboxedWorkflowRunner avoids "Cannot access os.stat from inside a workflow"
    # when the SDK logs workflow exceptions (traceback formatting uses linecache -> os.stat).
    workflow_runner = UnsandboxedWorkflowRunner()
    worker_doc = Worker(
        client,
        task_queue="document-serialization-queue",
        workflows=[DocumentSerializationWorkflow],
        activities=all_activities,
        workflow_runner=workflow_runner,
    )
    worker_task = Worker(
        client,
        task_queue="task-execution-queue",
        workflows=[TaskExecutionWorkflow, SingleTaskExecutionWorkflow],
        activities=all_activities,
        workflow_runner=workflow_runner,
    )
    
    logger.info("Workers started, waiting for tasks...")
    try:
        await asyncio.gather(worker_doc.run(), worker_task.run())
    except KeyboardInterrupt:
        logger.info("Worker shutting down...")
    finally:
        close_pool()
        logger.info("Worker stopped")


if __name__ == "__main__":
    asyncio.run(main())

