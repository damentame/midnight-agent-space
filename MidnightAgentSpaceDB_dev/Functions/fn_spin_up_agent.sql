-- FUNCTION: main.fn_spin_up_agent(bigint, bigint)

-- DROP FUNCTION IF EXISTS main.fn_spin_up_agent(bigint, bigint);

CREATE OR REPLACE FUNCTION main.fn_spin_up_agent(
    p_agent_id bigint DEFAULT 2,
    p_project_id bigint DEFAULT NULL
)
RETURNS jsonb
LANGUAGE 'plpgsql'
AS $BODY$
DECLARE
    v_result jsonb;
BEGIN
    -- Call the procedure and capture the result
    CALL main.sp_spin_up_agent(v_result, p_agent_id, p_project_id);
    
    -- Return the result
    RETURN v_result;
END;
$BODY$;

ALTER FUNCTION main.fn_spin_up_agent(bigint, bigint)
    OWNER TO postgres;

