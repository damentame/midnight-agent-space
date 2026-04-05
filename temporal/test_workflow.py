"""Quick test script for the Temporal workflow."""
import asyncio
import sys
import os
from pathlib import Path

# Add parent directory to path so we can import temporal module
parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

from temporal.client import start_document_serialization, get_workflow_result
from temporal.config import config
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def test_workflow(
    agent_id: int,
    project_id: int,
    agent_provider: str = "cursor",
    require_human_review: bool = False,
):
    """Test the document serialization workflow."""
    logger.info("=" * 60)
    logger.info("TESTING TEMPORAL DOCUMENT SERIALIZATION WORKFLOW")
    logger.info("=" * 60)
    logger.info(f"Configuration:")
    logger.info(f"  - Temporal: {config.temporal.address}")
    logger.info(f"  - Database: {config.database.connection_string.split('@')[1] if '@' in config.database.connection_string else 'N/A'}")
    logger.info(f"  - OpenAI Model: {config.openai.embedding_model}")
    logger.info(f"  - Agent ID: {agent_id}")
    logger.info(f"  - Project ID: {project_id}")
    logger.info(f"  - Agent provider: {agent_provider}")
    logger.info(f"  - Require human review: {require_human_review}")
    logger.info("=" * 60)
    
    try:
        logger.info("Starting workflow...")
        workflow_id = await start_document_serialization(
            agent_id=agent_id,
            project_id=project_id,
            agent_provider=agent_provider,
            require_human_review=require_human_review,
        )
        
        logger.info(f"Workflow started with ID: {workflow_id}")
        logger.info("Waiting for workflow to complete...")
        
        result = await get_workflow_result(workflow_id)
        
        logger.info("=" * 60)
        logger.info("WORKFLOW COMPLETED SUCCESSFULLY!")
        logger.info("=" * 60)
        logger.info(f"Results:")
        logger.info(f"  - Documents processed: {result.get('documents_processed', 0)}")
        logger.info(f"  - Chunks created: {result.get('chunks_created', 0)}")
        logger.info(f"  - Tasks executed: {result.get('tasks_executed', 0)}")
        logger.info(f"  - Embeddings generated: {result.get('embeddings_generated', 0)}")
        logger.info(f"  - Status: {result.get('serialization_status', 'UNKNOWN')}")
        logger.info("=" * 60)
        
        return result
        
    except Exception as e:
        logger.error("=" * 60)
        logger.error("WORKFLOW FAILED!")
        logger.error("=" * 60)
        logger.error(f"Error Type: {type(e).__name__}")
        logger.error(f"Error Message: {str(e)}")
        
        # Extract nested error details from Temporal exceptions
        current_error = e
        depth = 0
        while current_error and depth < 5:
            if hasattr(current_error, '__cause__') and current_error.__cause__:
                current_error = current_error.__cause__
                depth += 1
                logger.error(f"  [{depth}] Caused by: {type(current_error).__name__}: {str(current_error)}")
                
                # If it's an ApplicationError, try to get the message
                if hasattr(current_error, 'message'):
                    logger.error(f"      Message: {current_error.message}")
                if hasattr(current_error, 'type'):
                    logger.error(f"      Type: {current_error.type}")
            else:
                break
        
        logger.error("")
        logger.error("Full traceback:")
        logger.error("=" * 60)
        import traceback
        logger.error(traceback.format_exc())
        logger.error("=" * 60)
        logger.error("")
        logger.error("IMPORTANT: To see the EXACT Python error with full traceback:")
        logger.error("  1. Make sure the worker is running: python worker.py")
        logger.error("  2. Check the worker terminal output - it shows the full")
        logger.error("     Python traceback from the activity that failed")
        logger.error("  3. The worker logs will show lines like:")
        logger.error("     'ERROR - Error storing vectors: ...'")
        logger.error("     'ERROR - Full traceback: ...'")
        logger.error("=" * 60)
        raise


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python test_workflow.py <agent_id> <project_id> [--agent-provider cursor|codex] [--require-human-review]")
        print("\nExample:")
        print("  python test_workflow.py 1 1")
        print("  python test_workflow.py 1 1 --agent-provider codex")
        sys.exit(1)
    
    agent_id = int(sys.argv[1])
    project_id = int(sys.argv[2])
    agent_provider = "codex" if "--agent-provider" in sys.argv and "codex" in " ".join(sys.argv) else "cursor"
    require_human_review = "--require-human-review" in sys.argv

    asyncio.run(
        test_workflow(
            agent_id,
            project_id,
            agent_provider,
            require_human_review,
        )
    )

