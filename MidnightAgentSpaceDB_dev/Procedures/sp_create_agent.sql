-- PROCEDURE: main.sp_create_agent(text, bigint, bigint, text, text, jsonb, jsonb, text)

-- DROP PROCEDURE IF EXISTS main.sp_create_agent(text, bigint, bigint, text, text, jsonb, jsonb, text);

CREATE OR REPLACE PROCEDURE main.sp_create_agent(
	IN p_agent_name text,
	IN p_agent_type bigint,
	IN p_agent_role_id bigint,
	IN p_api_key text,
	IN p_endpoint_url text,
	IN p_capabilities jsonb,
	IN p_config jsonb,
	IN p_created_by text)
LANGUAGE 'plpgsql'
AS $BODY$
DECLARE
BEGIN
    -- Validate agent type (should be BIGINT, so pass TRUE)
    PERFORM fn_validate_type(p_agent_type, 'BIGINT'::regtype, TRUE);
    
    -- Validate config structure
    IF NOT (
        p_config ? 'constraints' AND
        p_config ? 'responsibilities' AND
        p_config ? 'success_criteria' AND
        p_config ? 'escalation'
    ) THEN
        RAISE EXCEPTION 'Invalid config JSON: missing required sections';
    END IF;

    INSERT INTO agent (
        agent_name,
        agent_type,
        agent_role_id,
        api_key,
        endpoint_url,
        agent_status,
        capabilities,
        config,
        created_by,
        updated_by,
        created_at,
        updated_at
    )
    VALUES (
        p_agent_name,
        p_agent_type,
        p_agent_role_id,
        p_api_key,
        p_endpoint_url,
        'ACTIVE',
        p_capabilities,
        p_config,
        p_created_by,
        p_created_by,
        now(),
        now()
    );
END;
$BODY$;
ALTER PROCEDURE main.sp_create_agent(text, bigint, bigint, text, text, jsonb, jsonb, text)
    OWNER TO postgres;
