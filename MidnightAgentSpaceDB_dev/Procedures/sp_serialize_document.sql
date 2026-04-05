-- PROCEDURE: main.sp_serialize_document(bigint)

-- DROP PROCEDURE IF EXISTS main.sp_serialize_document(bigint);

CREATE OR REPLACE PROCEDURE main.sp_serialize_document(
	IN p_document_id bigint,
	IN p_serialized_payload jsonb,
	IN p_updated_by character varying DEFAULT 'system')
LANGUAGE 'plpgsql'
AS $BODY$
BEGIN
    -- Update the document with serialized payload
    UPDATE main.project_document
    SET 
        serialized_payload = p_serialized_payload,
        serialization_status = 'COMPLETED',
        serialized_at = CURRENT_TIMESTAMP,
        updated_by = p_updated_by,
        updated_at = CURRENT_TIMESTAMP
    WHERE document_id = p_document_id;
    
    -- Check if document was found and updated
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Document (document_id=%) not found', p_document_id;
    END IF;
    
    -- Log the serialization event
    INSERT INTO main.event_log (
        entity_type,
        entity_id,
        project_id,
        event_type,
        payload,
        created_by
    )
    SELECT 
        'project_document',
        p_document_id,
        project_id,
        'document_serialized',
        jsonb_build_object(
            'document_id', p_document_id,
            'document_name', document_name,
            'serialization_status', 'COMPLETED',
            'timestamp', CURRENT_TIMESTAMP
        ),
        p_updated_by
    FROM main.project_document
    WHERE document_id = p_document_id;
END;
$BODY$;

ALTER PROCEDURE main.sp_serialize_document(bigint, jsonb, character varying)
    OWNER TO postgres;

