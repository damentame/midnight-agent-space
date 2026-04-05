-- PROCEDURE: main.sp_spin_up_agent(bigint, bigint)

-- DROP PROCEDURE IF EXISTS main.sp_spin_up_agent(bigint, bigint);

CREATE OR REPLACE PROCEDURE main.sp_spin_up_agent(
	OUT p_result jsonb,
	IN p_agent_id bigint DEFAULT 2,
	IN p_project_id bigint DEFAULT NULL)
LANGUAGE 'plpgsql'
AS $BODY$
DECLARE
    v_agent RECORD;
    v_agent_instance_id bigint;
BEGIN
    -- Validate required project context (agent_instance requires a project_id)
    IF p_project_id IS NULL THEN
        RAISE EXCEPTION 'p_project_id is required to spin up an agent instance';
    END IF;

    -- Fetch agent definition from database
    SELECT *
    INTO v_agent
    FROM main.agent
    WHERE agent_id = p_agent_id
      AND agent_status = 'ACTIVE';

    -- Check if agent was found
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Agent (agent_id=%) not available or not ACTIVE. Check: agent_id=%, agent_status=ACTIVE', p_agent_id, p_agent_id;
    END IF;

    -- Validate that agent has required configuration
    IF v_agent.config IS NULL OR v_agent.capabilities IS NULL THEN
        RAISE EXCEPTION 'Agent (agent_id=%) missing required config or capabilities', p_agent_id;
    END IF;

    -- Create agent instance record for this spin-up
    INSERT INTO main.agent_instance (
        agent_id,
        project_id,
        instance_status,
        spin_up_reason,
        instance_metadata,
        started_at,
        created_by,
        updated_by,
        created_at,
        updated_at
    )
    VALUES (
        p_agent_id,
        p_project_id,
        'ACTIVE',
        'sp_spin_up_agent',
        jsonb_build_object(
            'agent_name', v_agent.agent_name,
            'agent_type', v_agent.agent_type,
            'source', 'sp_spin_up_agent',
            'timestamp', now()
        ),
        now(),
        'system',
        'system',
        now(),
        now()
    )
    RETURNING agent_instance_id INTO v_agent_instance_id;

    -- Log agent-instance spin-up event
    INSERT INTO main.event_log (
        entity_type,
        entity_id,
        project_id,
        event_type,
        payload,
        created_by
    )
    VALUES (
        'AGENT_INSTANCE',
        v_agent_instance_id,
        p_project_id,
        'AGENT_INSTANCE_SPIN_UP',
        jsonb_build_object(
            'agent_id', p_agent_id,
            'agent_instance_id', v_agent_instance_id,
            'agent_name', v_agent.agent_name,
            'project_id', p_project_id,
            'timestamp', now()
        ),
        'system'
    );

    -- Build result JSONB with all data needed for n8n to make Cursor API call
    SELECT jsonb_build_object(
        'agent_id', v_agent.agent_id,
        'agent_instance_id', v_agent_instance_id,
        'agent_name', v_agent.agent_name,
        'agent_type', v_agent.agent_type,
        'endpoint_url', v_agent.endpoint_url,
        'api_key', v_agent.api_key,
        'capabilities', v_agent.capabilities,
        'config', v_agent.config,
        'project_id', p_project_id,
        'spin_up_timestamp', now()
    )
    INTO p_result;
END;
$BODY$;

ALTER PROCEDURE main.sp_spin_up_agent(bigint, bigint)
    OWNER TO postgres;

