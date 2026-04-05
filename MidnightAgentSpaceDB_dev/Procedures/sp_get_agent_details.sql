-- PROCEDURE: main.sp_get_agent_details(bigint)

-- DROP PROCEDURE IF EXISTS main.sp_get_agent_details(bigint);

CREATE OR REPLACE PROCEDURE main.sp_get_agent_details(
	OUT p_result jsonb,
	IN p_agent_id bigint DEFAULT 2)
LANGUAGE 'plpgsql'
AS $BODY$
DECLARE
    v_agent RECORD;
BEGIN
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

    -- Build result JSONB with agent details needed for Cursor API call
    SELECT jsonb_build_object(
        'agent_id', v_agent.agent_id,
        'agent_name', v_agent.agent_name,
        'agent_type', v_agent.agent_type,
        'endpoint_url', v_agent.endpoint_url,
        'api_key', v_agent.api_key,
        'capabilities', v_agent.capabilities,
        'config', v_agent.config
    )
    INTO p_result;
END;
$BODY$;

ALTER PROCEDURE main.sp_get_agent_details(bigint)
    OWNER TO postgres;

