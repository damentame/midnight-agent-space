"""Main Temporal workflow for document serialization with RAG."""
import logging
from typing import Dict, Any, List
from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError

# Don't import activities at module level - import them lazily inside the workflow method
# This prevents activity modules from being loaded during module import, which could trigger
# restricted operations. Activities are imported with imports_passed_through() when needed.

logger = logging.getLogger(__name__)


@dataclass
class DocumentSerializationInput:
    """Input for document serialization workflow."""
    agent_id: int
    project_id: int
    # Agent provider to use for document serialization and task generation.
    # Supported values:
    # - "cursor": use Cursor cloud agents (current default/behavior)
    # - "codex":  use Codex/OpenAI-based agents
    agent_provider: str = "cursor"
    # When True, task branches created during this workflow will be left unmerged
    # for human review instead of being auto-merged back into the workflow's
    # per-run develop branch.
    require_human_review: bool = False
    # When True, the task execution phase will run tasks concurrently (when possible)
    # via per-task child workflows. When False (default), tasks are executed sequentially.
    concurrent_tasks: bool = False
    # fast vs complex models for serialization and task execution (see model_routing).
    execute_mode: str = "fast"
    # When True, task execution runs as one batched activity (cannot combine with concurrent_tasks).
    batch_tasks: bool = False


@dataclass
class DocumentSerializationResult:
    """Result of document serialization workflow (includes task execution when use_cursor_api)."""
    project_id: int
    agent_instance_id: int
    documents_processed: int
    chunks_created: int
    serialization_results: List[Dict[str, Any]]
    tasks_executed: int = 0  # Set after task execution child workflow completes


@workflow.defn  # Sandboxing re-enabled - timeout issue fixed
class DocumentSerializationWorkflow:
    """
    Workflow that serializes project documents with RAG capabilities.
    
    Process:
    1. Spin up agent instance
    2. Get project documents
    3. For each document:
       a. Chunk document semantically
       b. Generate embeddings for chunks
       c. Store chunks and vectors in database
       d. Serialize document (Cursor API or local LLM)
       e. Update document with serialization
    """
    
    @workflow.run
    async def run(self, input: DocumentSerializationInput) -> DocumentSerializationResult:
        """Execute the document serialization workflow."""
        # Lazy import activities and config inside workflow method to avoid file system operations during module import
        # Import with imports_passed_through() to avoid sandbox restrictions
        with workflow.unsafe.imports_passed_through():
            from temporal.config import config
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
                retrieve_rag_context_activity
            )
            from temporal.activities.api_activities import (
                create_cursor_agent_activity,
                serialize_document_cursor_activity,
                serialize_document_local_activity,
                persist_generated_tasks_activity,
            )
            from temporal.workflows.task_execution_workflow import (
                TaskExecutionWorkflow,
                TaskExecutionInput,
            )
        
        # #region agent log
        try:
            with open(r'c:\Users\tipod\Documents\Midnight\MidnightAgentSpace\.cursor\debug.log', 'a') as f:
                import json
                f.write(json.dumps({"runId":"init","hypothesisId":"A","location":"workflow.py:72","message":"Workflow run started","data":{"agent_id":input.agent_id,"project_id":input.project_id},"timestamp":__import__('time').time()*1000})+'\n')
        except: pass
        # #endregion
        
        if input.concurrent_tasks and input.batch_tasks:
            raise ApplicationError(
                "concurrent_tasks and batch_tasks cannot both be true",
                non_retryable=True,
            )

        workflow.logger.info(
            f"Starting document serialization workflow: "
            f"agent_id={input.agent_id}, project_id={input.project_id}"
        )
        
        # #region agent log
        try:
            with open(r'c:\Users\tipod\Documents\Midnight\MidnightAgentSpace\.cursor\debug.log', 'a') as f:
                import json
                f.write(json.dumps({"runId":"init","hypothesisId":"B","location":"workflow.py:82","message":"Before config access","data":{},"timestamp":__import__('time').time()*1000})+'\n')
        except: pass
        # #endregion
        
        workflow_run_id = None
        
        # Step 1: Spin up agent
        workflow.logger.info("Step 1: Spinning up agent")
        
        # #region agent log
        try:
            with open(r'c:\Users\tipod\Documents\Midnight\MidnightAgentSpace\.cursor\debug.log', 'a') as f:
                import json
                f.write(json.dumps({"runId":"init","hypothesisId":"C","location":"workflow.py:90","message":"Before execute_activity","data":{},"timestamp":__import__('time').time()*1000})+'\n')
        except: pass
        # #endregion
        
        # Store activity function reference to ensure it's accessible
        activity_func = spin_up_agent_activity
        
        # Log activity function reference info before calling
        workflow.logger.info(f"Activity function: {activity_func}")
        workflow.logger.info(f"Activity function name: {getattr(activity_func, '__name__', 'unknown')}")
        workflow.logger.info(f"Activity function module: {getattr(activity_func, '__module__', 'unknown')}")
        workflow.logger.info(f"Activity function qualname: {getattr(activity_func, '__qualname__', 'unknown')}")
        
        try:
            workflow.logger.info("About to call execute_activity")
            workflow.logger.info(f"Activity function type: {type(activity_func)}")
            workflow.logger.info(f"Activity function repr: {repr(activity_func)}")
            
            # Try to get activity name from the function
            try:
                activity_name = activity_func._name if hasattr(activity_func, '_name') else getattr(activity_func, '__name__', 'unknown')
                workflow.logger.info(f"Activity name from function: {activity_name}")
            except Exception as name_err:
                workflow.logger.warning(f"Could not get activity name: {name_err}")
            
            # Call execute_activity directly without sandbox_unrestricted since sandboxing is disabled
            agent_data = await workflow.execute_activity(
                activity_func,
                args=[input.agent_id, input.project_id],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=3)
            )
            workflow.logger.info("execute_activity completed successfully")
        except Exception as e:
            # Log error details using workflow logger (sandbox-safe)
            # Capture error info as simple strings to avoid traceback formatting
            error_type = type(e).__name__
            error_msg = str(e)[:1000]  # Increased limit to capture more details
            
            # Log error details using workflow logger (file I/O is restricted in sandbox)
            workflow.logger.error("=" * 80)
            workflow.logger.error(f"ACTIVITY_ERROR_TYPE: {error_type}")
            workflow.logger.error(f"ACTIVITY_ERROR_MSG: {error_msg}")
            workflow.logger.error(f"Activity error: {error_type}: {error_msg}")
            workflow.logger.error("=" * 80)
            
            # Log to debug file using sandbox_unrestricted context (for debugging only)
            # #region agent log
            try:
                with workflow.unsafe.sandbox_unrestricted():
                    with open(r'c:\Users\tipod\Documents\Midnight\MidnightAgentSpace\.cursor\debug.log', 'a') as f:
                        import json
                        f.write(json.dumps({"runId":"error","hypothesisId":"J","location":"workflow.py:125","message":"Activity execution error","data":{"error_type":error_type,"error_msg":error_msg[:500]},"timestamp":__import__('time').time()*1000})+'\n')
            except Exception as file_err:
                workflow.logger.warning(f"Could not write error to file: {file_err}")
            # #endregion
            
            # Re-raise the original error
            raise
        
        agent_instance_id = agent_data.get("agent_instance_id")
        workflow.logger.info(f"Agent instance created: {agent_instance_id}")
        
        # Record workflow_run in DB for this execution
        workflow_run_input = {
            "agent_id": input.agent_id,
            "project_id": input.project_id,
            "agent_provider": input.agent_provider,
            "require_human_review": input.require_human_review,
            "concurrent_tasks": input.concurrent_tasks,
            "execute_mode": input.execute_mode,
            "batch_tasks": input.batch_tasks,
        }
        workflow_run_id = await workflow.execute_activity(
            start_workflow_run_activity,
            args=[
                "DocumentSerializationWorkflow",
                input.project_id,
                agent_instance_id,
                workflow_run_input,
            ],
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        
        # Step 2: Prepare agent prompt
        workflow.logger.info("Step 2: Preparing agent prompt")
        prompt = await workflow.execute_activity(
            prepare_agent_prompt_activity,
            args=[agent_data],
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=RetryPolicy(maximum_attempts=2)
        )
        
        # Step 3: Create agent via API (depending on agent provider)
        agent_response = None
        
        # #region agent log
        try:
            with open(r'c:\Users\tipod\Documents\Midnight\MidnightAgentSpace\.cursor\debug.log', 'a') as f:
                import json
                f.write(json.dumps({"runId":"init","hypothesisId":"E","location":"workflow.py:105","message":"Before config.cursor_api access","data":{"agent_provider":input.agent_provider},"timestamp":__import__('time').time()*1000})+'\n')
        except: pass
        # #endregion
        
        try:
            api_key_value = config.cursor_api.api_key
            # #region agent log
            try:
                with open(r'c:\Users\tipod\Documents\Midnight\MidnightAgentSpace\.cursor\debug.log', 'a') as f:
                    import json
                    f.write(json.dumps({"runId":"init","hypothesisId":"E","location":"workflow.py:111","message":"After config.cursor_api access","data":{"api_key_present":api_key_value is not None},"timestamp":__import__('time').time()*1000})+'\n')
            except: pass
            # #endregion
        except Exception as e:
            # #region agent log
            try:
                with open(r'c:\Users\tipod\Documents\Midnight\MidnightAgentSpace\.cursor\debug.log', 'a') as f:
                    import json
                    f.write(json.dumps({"runId":"init","hypothesisId":"E","location":"workflow.py:117","message":"Config access error","data":{"error_type":type(e).__name__,"error_msg":str(e)[:200]},"timestamp":__import__('time').time()*1000})+'\n')
            except: pass
            # #endregion
            raise
        
        # Step 3: Always create Cursor agent for document serialization/task generation when API key is set.
        # This runs the same activities for both Cursor and Codex providers so tasks are created identically.
        # agent_provider only affects task execution (Codex vs Cursor) in the child TaskExecutionWorkflow.
        if config.cursor_api.api_key:
            workflow.logger.info("Step 3: Creating agent via Cursor API")
            workflow.logger.info(f"  - agent_provider: {input.agent_provider}")
            workflow.logger.info(f"  - API key configured: Yes")
            workflow.logger.info(f"  - API URL: {config.cursor_api.api_url}")
            agent_response = await workflow.execute_activity(
                create_cursor_agent_activity,
                args=[agent_data, prompt, input.execute_mode],
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=RetryPolicy(maximum_attempts=3)
            )
        else:
            workflow.logger.info("Step 3: Skipping Cursor API (no API key)")
            workflow.logger.info(f"  - agent_provider: {input.agent_provider}")
            agent_response = None
        
        # Step 4: Get project documents
        workflow.logger.info("Step 4: Fetching project documents")
        documents_result = await workflow.execute_activity(
            get_project_documents_activity,
            args=[input.project_id],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3)
        )
        
        documents = documents_result.get("documents", [])
        workflow.logger.info(f"Found {len(documents)} documents to process")
        
        serialization_results = []
        total_chunks = 0
        
        if not documents:
            workflow.logger.info("No documents to process; will still run task execution for project")
        else:
            # Step 5: Process each document
            for document in documents:
                document_id = document.get("document_id")
                workflow.logger.info(f"Processing document {document_id}")
                
                try:
                    # 5a: Chunk document
                    chunks = await workflow.execute_activity(
                        chunk_document_activity,
                        args=[document],
                        start_to_close_timeout=timedelta(seconds=60),
                        retry_policy=RetryPolicy(maximum_attempts=2)
                    )
                    
                    if not chunks:
                        workflow.logger.warning(f"No chunks created for document {document_id}")
                        continue
                    
                    # 5b: Generate embeddings
                    chunks_with_embeddings = await workflow.execute_activity(
                        generate_embeddings_activity,
                        args=[chunks],
                        start_to_close_timeout=timedelta(seconds=300),  # 5 minutes for embeddings
                        retry_policy=RetryPolicy(
                            maximum_attempts=5,
                            initial_interval=timedelta(seconds=2),
                            backoff_coefficient=2.0
                        )
                    )
                    
                    # 5c: Store vectors
                    chunk_ids = await workflow.execute_activity(
                        store_vectors_activity,
                        args=[chunks_with_embeddings],
                        start_to_close_timeout=timedelta(seconds=120),
                        retry_policy=RetryPolicy(maximum_attempts=3)
                    )
                    
                    total_chunks += len(chunk_ids)
                    workflow.logger.info(
                        f"Document {document_id}: Created {len(chunk_ids)} chunks with embeddings"
                    )
                    
                    serialization_results.append({
                        "document_id": document_id,
                        "chunks_created": len(chunk_ids),
                        "status": "chunked_and_stored"
                    })
                    
                    workflow.logger.info(f"Document {document_id} chunked and stored successfully")
                    
                except Exception as e:
                    workflow.logger.error(f"Error processing document {document_id}: {e}")
                    serialization_results.append({
                        "document_id": document_id,
                        "status": "error",
                        "error": str(e)
                    })
        
        # Preserve agent mapping (set in Step 6 when roles are ensured; used for reporting only)
        last_agent_mapping = None
        
        # Step 6: After all documents are chunked and stored, retrieve RAG context and generate tasks.
        # Always use the same Cursor activities (serialize_document_cursor_activity) for both Cursor and Codex
        # so tasks are created identically. agent_provider only affects task execution in the child workflow.
        if total_chunks > 0 and agent_response is not None:
            workflow.logger.info("Step 6: Retrieving RAG context for task generation")
            
            task_query = "Project requirements and specifications for task generation and implementation"
            
            rag_context = await workflow.execute_activity(
                retrieve_rag_context_activity,
                args=[task_query, input.project_id, 10, 0.3, None],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=3)
            )
            
            first_document_id = documents[0].get("document_id") if documents else None
            
            workflow.logger.info("Step 7: Waiting for Cursor agent to complete and retrieving results")
            cursor_response = await workflow.execute_activity(
                serialize_document_cursor_activity,
                args=[
                    rag_context,
                    agent_response.get("id"),
                    task_query,
                    first_document_id,
                    input.project_id,
                    input.agent_id,
                    agent_instance_id,
                    input.execute_mode,
                ],
                start_to_close_timeout=timedelta(minutes=130),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
            
            workflow.logger.info(
                f"Cursor agent completed. Status: {cursor_response.get('status')}, "
                f"RAG chunks retrieved: {rag_context.get('count', 0)}"
            )

            # Step 8: Persist generated tasks to DB (extract from cursor response and call sp_persist_generated_tasks)
            workflow.logger.info("Step 8: Persisting generated tasks to database")
            persist_result = await workflow.execute_activity(
                persist_generated_tasks_activity,
                args=[
                    input.project_id,
                    first_document_id,
                    input.agent_id,
                    agent_instance_id,
                    cursor_response,
                    workflow_run_id,
                    input.execute_mode,
                ],
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            if persist_result.get("persisted"):
                workflow.logger.info(
                    "Persisted %s tasks for task execution",
                    persist_result.get("task_count", 0),
                )
            else:
                workflow.logger.info(
                    "No tasks persisted (extraction yielded none or persist skipped)"
                )
            
            rag_task_result = {
                "status": cursor_response.get("status", "unknown"),
                "chunks_retrieved": rag_context.get("count", 0),
                "cursor_agent_id": cursor_response.get("agent_id"),
                "cursor_results": cursor_response.get("results"),
                "completed_at": cursor_response.get("agent_data", {}).get("completedAt"),
            }

            serialization_results.append({
                "rag_task_generation": rag_task_result
            })

            # Derive high-level roles from generated tasks (if present)
            roles_json = {"roles": []}
            seen_role_names = set()

            def add_role(role_name: str, agent_category: str) -> None:
                if not role_name or role_name in seen_role_names:
                    return
                seen_role_names.add(role_name)
                roles_json["roles"].append({
                    "role_name": role_name,
                    "agent_category": agent_category,
                    "responsibilities": [],
                    "constraints": [],
                    "success_criteria": [],
                })

            results_payload = cursor_response.get("results")
            tasks_container = None

            if isinstance(results_payload, dict) and "tasks" in results_payload:
                tasks_container = results_payload
            elif isinstance(results_payload, list) and results_payload:
                first_item = results_payload[0]
                if isinstance(first_item, dict) and "tasks" in first_item:
                    tasks_container = first_item

            if isinstance(tasks_container, dict):
                tasks = tasks_container.get("tasks") or []
                for task in tasks:
                    if not isinstance(task, dict):
                        continue
                    task_data = task.get("task_data") or {}
                    if not isinstance(task_data, dict):
                        continue

                    role_name = task_data.get("role_name") or task_data.get("owner_role")
                    agent_category = task_data.get("agent_category") or "TaskExecutor"
                    if role_name:
                        add_role(str(role_name), str(agent_category))

            # Fallback: ensure at least a generic Task Executor role exists
            if not roles_json["roles"]:
                add_role("Task Executor", "TaskExecutor")

            # Ensure agents exist for these roles and capture mapping
            agent_mapping = await workflow.execute_activity(
                ensure_agents_from_roles_activity,
                args=[input.project_id, roles_json],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=3)
            )
            last_agent_mapping = agent_mapping

            serialization_results.append({
                "agent_provisioning": {
                    "roles": roles_json["roles"],
                    "agent_mapping": agent_mapping,
                }
            })
        
        workflow.logger.info(
            f"Workflow complete: {len(serialization_results)} documents processed, "
            f"{total_chunks} total chunks created"
        )
        
        tasks_executed = 0
        # Extension of main flow: run task executions immediately after serialization, using the
        # same agent that was started for this run. Each task runs as its own activities for
        # granular error detection and logging. Workflow waits until the final task is complete.
        if agent_instance_id is not None:
            workflow.logger.info(
                "Running task execution as child workflow (extension of main flow); "
                "using executor agent from this run; waiting until final task completes"
            )
            try:
                task_execution_result = await workflow.execute_child_workflow(
                    TaskExecutionWorkflow.run,
                    TaskExecutionInput(
                        project_id=input.project_id,
                        agent_id=input.agent_id,
                        agent_instance_id=agent_instance_id,
                        max_tasks=50,
                        workspace_root=getattr(
                            getattr(config, "temporal", None), "workspace_root", ""
                        ) or "",
                        branch_workflow_run_id=workflow_run_id,
                        agent_provider=input.agent_provider,
                        require_human_review=input.require_human_review,
                        concurrent_tasks=input.concurrent_tasks,
                        execute_mode=input.execute_mode,
                        batch_tasks=input.batch_tasks,
                    ),
                    id=f"task-exec-{input.project_id}-{workflow.info().run_id}",
                    task_queue="task-execution-queue",
                    execution_timeout=timedelta(hours=6),  # Cap total task execution phase
                )
                tasks_executed = task_execution_result.tasks_executed
                workflow.logger.info(
                    f"Task execution child workflow completed: {tasks_executed} tasks executed"
                )
            except Exception as task_err:
                workflow.logger.error(
                    f"Task execution child workflow failed: {task_err}"
                )
        
        result = DocumentSerializationResult(
            project_id=input.project_id,
            agent_instance_id=agent_instance_id,
            documents_processed=len(serialization_results),
            chunks_created=total_chunks,
            serialization_results=serialization_results,
            tasks_executed=tasks_executed,
        )
        
        # Persist workflow_run completion and full result payload
        try:
            if workflow_run_id is not None:
                from dataclasses import asdict
                await workflow.execute_activity(
                    finish_workflow_run_activity,
                    args=[
                        workflow_run_id,
                        "COMPLETED",
                        asdict(result),
                    ],
                    start_to_close_timeout=timedelta(seconds=15),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
        except Exception as finish_err:
            workflow.logger.error(
                f"Failed to mark workflow_run_id={workflow_run_id} as COMPLETED: {finish_err}"
            )
        
        return result

