-- PROCEDURE: main.sp_serialize_project(bigint)

-- DROP PROCEDURE IF EXISTS main.sp_serialize_project(bigint);

CREATE OR REPLACE PROCEDURE main.sp_serialize_project(
	IN p_project_id bigint,
	OUT p_result jsonb)
LANGUAGE 'plpgsql'
AS $BODY$
DECLARE
    v_agent_count INTEGER;
    v_documents JSONB;
BEGIN
    -- Fetch BRA agent (agent_id = 2 enforced for now) into temp table
    DROP TABLE IF EXISTS v_agent;
    CREATE TEMP TABLE v_agent AS
    SELECT *
    FROM main.agent
    WHERE agent_id = 2
      AND agent_type = '1'
      AND agent_status = 'ACTIVE';

    -- Check if agent was found
    SELECT COUNT(*) INTO v_agent_count FROM v_agent;
    
    IF v_agent_count = 0 THEN
        DROP TABLE IF EXISTS v_agent;
        RAISE EXCEPTION 'BRA agent (agent_id=2) not available. Check: agent_id=2, agent_type=1, agent_status=ACTIVE';
    END IF;

    -- Fetch all project documents into temp table
    DROP TABLE IF EXISTS v_documents;
    CREATE TEMP TABLE v_documents AS
    SELECT COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'document_id', d.document_id,
                'document_name', d.document_name,
                'document_type', d.document_type,
                'content', COALESCE(
                    convert_from(d.file_content, 'UTF8'),
                    d.raw_text_content
                )
            )
        ),
        '[]'::jsonb
    ) AS documents_json
    FROM main.project_document d
    WHERE d.project_id = p_project_id;

    -- Build and assign result to OUT parameter
    SELECT jsonb_build_object(
        'project_id', p_project_id,
        'agent', jsonb_build_object(
            'agent_id', a.agent_id,
            'agent_name', a.agent_name,
            'capabilities', a.capabilities,
            'config', a.config
        ),
        'documents', d.documents_json
    )
    INTO p_result
    FROM v_agent a
    CROSS JOIN v_documents d;

    -- Clean up temp tables
    DROP TABLE IF EXISTS v_agent;
    DROP TABLE IF EXISTS v_documents;
END;
$BODY$;
ALTER PROCEDURE main.sp_serialize_project(bigint)
    OWNER TO postgres;
