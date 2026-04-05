"""Agent-related Temporal activities."""
import logging
from typing import Dict, Any

from temporalio import activity
from temporal.utils.db import execute_function, execute_query, get_connection
from temporal.utils.activity_run import track_activity

logger = logging.getLogger(__name__)


@activity.defn
@track_activity
async def spin_up_agent_activity(agent_id: int, project_id: int) -> Dict[str, Any]:
    """
    Spin up an agent instance for a project.
    
    Calls main.fn_spin_up_agent() to get agent configuration and create instance.
    """
    # #region agent log
    try:
        with open(r'c:\Users\tipod\Documents\Midnight\MidnightAgentSpace\.cursor\debug.log', 'a') as f:
            import json
            f.write(json.dumps({"runId":"activity","hypothesisId":"I","location":"agent_activities.py:12","message":"Activity called","data":{"agent_id":agent_id,"project_id":project_id},"timestamp":__import__('time').time()*1000})+'\n')
    except: pass
    # #endregion
    try:
        logger.info(f"Spinning up agent {agent_id} for project {project_id}")
        
        # #region agent log
        try:
            with open(r'c:\Users\tipod\Documents\Midnight\MidnightAgentSpace\.cursor\debug.log', 'a') as f:
                import json
                f.write(json.dumps({"runId":"activity","hypothesisId":"I","location":"agent_activities.py:25","message":"Before execute_function","data":{},"timestamp":__import__('time').time()*1000})+'\n')
        except: pass
        # #endregion
        
        # Call database function
        result = execute_function("main.fn_spin_up_agent", (agent_id, project_id))
        
        # #region agent log
        try:
            with open(r'c:\Users\tipod\Documents\Midnight\MidnightAgentSpace\.cursor\debug.log', 'a') as f:
                import json
                f.write(json.dumps({"runId":"activity","hypothesisId":"I","location":"agent_activities.py:30","message":"After execute_function","data":{"result":bool(result)},"timestamp":__import__('time').time()*1000})+'\n')
        except: pass
        # #endregion
        
        if not result:
            raise ValueError(f"Failed to spin up agent {agent_id}")
        
        logger.info(f"Agent {agent_id} spun up successfully, instance_id: {result.get('agent_instance_id')}")
        return result
        
    except Exception as e:
        import traceback
        # #region agent log
        try:
            with open(r'c:\Users\tipod\Documents\Midnight\MidnightAgentSpace\.cursor\debug.log', 'a') as f:
                import json
                f.write(json.dumps({"runId":"activity","hypothesisId":"I","location":"agent_activities.py:40","message":"Activity exception","data":{"error_type":type(e).__name__,"error_msg":str(e)[:500]},"timestamp":__import__('time').time()*1000})+'\n')
        except: pass
        # #endregion
        logger.error(f"Error spinning up agent: {e}")
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
        raise


@activity.defn
@track_activity
async def prepare_agent_prompt_activity(agent_data: Dict[str, Any]) -> str:
    """
    Build agent prompt from agent configuration.
    
    Extracts responsibilities, constraints, and success criteria from agent config
    and formats them into a prompt string.
    """
    try:
        config = agent_data.get("config", {})
        agent_name = agent_data.get("agent_name", "Agent")
        
        def get_text(field):
            """Extract text from config field, handling objects."""
            if not field:
                return "Not specified"
            if isinstance(field, str):
                return field
            if isinstance(field, dict):
                if "text" in field:
                    return field["text"]
                # Format object nicely
                import json
                return json.dumps(field, indent=2)
            return str(field)
        
        prompt_text = f"""You are an AI software agent named {agent_name}.

Your responsibilities include:
{get_text(config.get('responsibilities'))}

Constraints:
{get_text(config.get('constraints'))}

Success Criteria:
{get_text(config.get('success_criteria'))}

Please respond briefly and clearly."""
        
        logger.info(f"Prepared prompt for agent {agent_name}")
        return prompt_text
        
    except Exception as e:
        logger.error(f"Error preparing agent prompt: {e}")
        raise


@activity.defn
@track_activity
async def prepare_agent_prompt_with_rag_activity(
    agent_data: Dict[str, Any],
    rag_context: Dict[str, Any]
) -> str:
    """
    Build enhanced agent prompt with RAG context.
    
    Combines agent configuration with relevant chunks from RAG retrieval
    to create a comprehensive prompt with project context, requirements,
    constraints, and success criteria.
    
    Args:
        agent_data: Agent configuration dictionary
        rag_context: RAG retrieval results with enriched chunks
        
    Returns:
        Enhanced prompt string with RAG context
    """
    try:
        config = agent_data.get("config", {})
        agent_name = agent_data.get("agent_name", "Agent")
        
        def get_text(field):
            """Extract text from config field, handling objects."""
            if not field:
                return "Not specified"
            if isinstance(field, str):
                return field
            if isinstance(field, dict):
                if "text" in field:
                    return field["text"]
                # Format object nicely
                import json
                return json.dumps(field, indent=2)
            return str(field)
        
        # Extract RAG results
        rag_results = rag_context.get("results", [])
        
        # Format RAG chunks
        rag_sections = []
        for chunk in rag_results[:10]:  # Top 10 most relevant
            chunk_text = chunk.get("chunk_text", "")
            document_name = chunk.get("document_name", "Unknown")
            document_type = chunk.get("document_type", "N/A")
            requirement_type = chunk.get("requirement_type", "general")
            similarity_score = chunk.get("similarity_score", 0)
            has_constraints = chunk.get("has_constraints", False)
            has_success_criteria = chunk.get("has_success_criteria", False)
            
            rag_sections.append(f"""
--- {document_name} ({document_type}) ---
Requirement Type: {requirement_type}
Similarity: {similarity_score:.2f}
{chunk_text}
""")
        
        # Extract project context from first chunk (if available)
        project_name = "Unknown"
        project_type = "N/A"
        if rag_results and len(rag_results) > 0:
            project_name = rag_results[0].get("project_name", "Unknown")
            project_type = rag_results[0].get("project_type", "N/A")
        
        # Extract constraints from RAG chunks
        constraints_from_rag = []
        for chunk in rag_results:
            if chunk.get("has_constraints", False):
                chunk_text = chunk.get("chunk_text", "")
                # Extract constraint-related sentences
                import re
                constraint_sentences = re.findall(r'[^.!?]*(?:constraint|limit|restriction|must not|cannot)[^.!?]*[.!?]', chunk_text, re.IGNORECASE)
                constraints_from_rag.extend(constraint_sentences[:2])  # Limit to 2 per chunk
        
        # Extract success criteria from RAG chunks
        criteria_from_rag = []
        for chunk in rag_results:
            if chunk.get("has_success_criteria", False):
                chunk_text = chunk.get("chunk_text", "")
                # Extract criteria-related sentences
                import re
                criteria_sentences = re.findall(r'[^.!?]*(?:acceptance|criteria|success|pass|verify|validate)[^.!?]*[.!?]', chunk_text, re.IGNORECASE)
                criteria_from_rag.extend(criteria_sentences[:2])  # Limit to 2 per chunk
        
        # Build enhanced prompt
        prompt_parts = [
            f"You are {agent_name}, an AI software agent.",
            "",
            "PROJECT CONTEXT:",
            f"- Project: {project_name}",
            f"- Type: {project_type}",
            "",
            f"RELEVANT REQUIREMENTS (Retrieved via RAG - {len(rag_results)} chunks):",
        ]
        
        if rag_sections:
            prompt_parts.extend(rag_sections)
        else:
            prompt_parts.append("No relevant requirements found.")
        
        prompt_parts.extend([
            "",
            "YOUR RESPONSIBILITIES:",
            get_text(config.get('responsibilities')),
            "",
            "CONSTRAINTS:",
            get_text(config.get('constraints')),
        ])
        
        if constraints_from_rag:
            prompt_parts.extend([
                "",
                "Additional constraints from requirements:",
                "\n".join(f"- {c}" for c in constraints_from_rag[:5])  # Limit to 5
            ])
        
        prompt_parts.extend([
            "",
            "SUCCESS CRITERIA:",
            get_text(config.get('success_criteria')),
        ])
        
        if criteria_from_rag:
            prompt_parts.extend([
                "",
                "Additional success criteria from requirements:",
                "\n".join(f"- {c}" for c in criteria_from_rag[:5])  # Limit to 5
            ])
        
        prompt_parts.extend([
            "",
            "TASK GENERATION INSTRUCTIONS:",
            "Generate tasks with:",
            "- Strict constraints and parameters",
            "- Detailed success criteria",
            "- Clear acceptance criteria",
            "- Explicit dependencies",
            "- Technical specifications",
        ])
        
        prompt_text = "\n".join(prompt_parts)
        
        logger.info(f"Prepared enhanced prompt for agent {agent_name} with {len(rag_results)} RAG chunks")
        return prompt_text
        
    except Exception as e:
        import traceback
        logger.error(f"Error preparing enhanced agent prompt: {e}")
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
        raise


@activity.defn
@track_activity
async def start_workflow_run_activity(
    workflow_name: str,
    project_id: int,
    agent_instance_id: int,
    input_data: Dict[str, Any],
) -> int:
    """
    Create a workflow_run row to track a workflow execution.
    """
    import json

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO main.workflow_run (
                        workflow_name,
                        project_id,
                        agent_instance_id,
                        status,
                        input_data,
                        started_at,
                        created_by,
                        updated_by
                    )
                    VALUES (
                        %s, %s, %s,
                        %s,
                        %s::jsonb,
                        now(),
                        %s,
                        %s
                    )
                    RETURNING workflow_run_id
                    """,
                    (
                        workflow_name,
                        project_id,
                        agent_instance_id,
                        "RUNNING",
                        json.dumps(input_data),
                        "system",
                        "system",
                    ),
                )
                row = cur.fetchone()
                if not row:
                    raise RuntimeError(
                        "Failed to create workflow_run row (no id returned)"
                    )
                workflow_run_id = int(row[0])

        logger.info(
            "Started workflow_run_id=%s for workflow_name=%s project_id=%s "
            "agent_instance_id=%s",
            workflow_run_id,
            workflow_name,
            project_id,
            agent_instance_id,
        )
        return workflow_run_id

    except Exception as e:
        import traceback
        logger.error("Error starting workflow_run: %s", e)
        logger.error("Full traceback:\n%s", traceback.format_exc())
        raise


@activity.defn
@track_activity
async def finish_workflow_run_activity(
    workflow_run_id: int,
    status: str,
    result_data: Dict[str, Any],
) -> None:
    """
    Mark a workflow_run as completed/failed and store result_data.
    """
    import json

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE main.workflow_run
                    SET
                        status      = %s,
                        result_data = %s::jsonb,
                        finished_at = now(),
                        updated_at  = now(),
                        updated_by  = %s
                    WHERE workflow_run_id = %s
                    """,
                    (
                        status,
                        json.dumps(result_data),
                        "system",
                        workflow_run_id,
                    ),
                )

        logger.info(
            "Finished workflow_run_id=%s with status=%s",
            workflow_run_id,
            status,
        )
    except Exception as e:
        import traceback
        logger.error("Error finishing workflow_run: %s", e)
        logger.error("Full traceback:\n%s", traceback.format_exc())
        raise


@activity.defn
@track_activity
async def ensure_agents_from_roles_activity(
    project_id: int,
    roles_json: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Ensure DB agents exist for each role definition and return a mapping
    from role_name -> agent_id.
    """
    import json

    try:
        logger.info(
            "Ensuring agents exist for roles for project_id=%s", project_id
        )

        # Call stored procedure to create any missing agents
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CALL main.sp_ensure_agents_for_roles(
                        %s,
                        %s::jsonb,
                        %s
                    )
                    """,
                    (
                        project_id,
                        json.dumps(roles_json),
                        "system",
                    ),
                )

        roles = roles_json.get("roles") or []
        mapping: Dict[str, Any] = {}

        # Re-query agent table to build role_name -> agent_id mapping
        for role in roles:
            role_name = role.get("role_name")
            if not role_name:
                continue

            agent_name = f"{role_name} Agent"
            rows = execute_query(
                """
                SELECT agent_id
                FROM main.agent
                WHERE agent_name = %s
                ORDER BY agent_id DESC
                LIMIT 1
                """,
                (agent_name,),
            )
            if rows:
                mapping[role_name] = rows[0]["agent_id"]

        logger.info(
            "ensure_agents_from_roles_activity created/resolved %s agents",
            len(mapping),
        )
        return mapping

    except Exception as e:
        import traceback
        logger.error(
            "Error in ensure_agents_from_roles_activity: %s", e
        )
        logger.error("Full traceback:\n%s", traceback.format_exc())
        raise

