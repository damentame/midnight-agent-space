-- PROCEDURE: main.sp_add_project_document(bigint, character varying, character varying, text, jsonb, character varying, character varying, bigint, bytea, character varying)

-- DROP PROCEDURE IF EXISTS main.sp_add_project_document(bigint, character varying, character varying, text, jsonb, character varying, character varying, bigint, bytea, character varying);

CREATE OR REPLACE PROCEDURE main.sp_add_project_document(
	IN p_project_id bigint,
	IN p_document_name character varying,
	IN p_document_type character varying,
	IN p_raw_text_content text,
	IN p_structured_json jsonb,
	IN p_file_extension character varying,
	IN p_file_mime_type character varying,
	IN p_file_size_bytes bigint,
	IN p_file_content bytea,
	IN p_created_by character varying)
LANGUAGE 'plpgsql'
AS $BODY$
DECLARE
    v_next_version INT;
    v_document_id  BIGINT;
BEGIN
    /*
     * Determine next version number for this project + document name
     */
    SELECT COALESCE(MAX(version_number), 0) + 1
    INTO v_next_version
    FROM project_document
    WHERE project_id = p_project_id
      AND document_name = p_document_name;

    /*
     * Deactivate previous active versions (logical versioning)
     */
    UPDATE project_document
    SET is_active_version = FALSE,
        updated_at = CURRENT_TIMESTAMP
    WHERE project_id = p_project_id
      AND document_name = p_document_name
      AND is_active_version = TRUE;

    /*
     * Insert new document record
     */
    INSERT INTO project_document (
        project_id,
        document_name,
        document_type,
        raw_text_content,
        structured_json,
        file_extension,
        file_mime_type,
        file_size_bytes,
        file_content,
        version_number,
        is_active_version,
        created_by,
        updated_by
    )
    VALUES (
        p_project_id,
        p_document_name,
        p_document_type,
        p_raw_text_content,
        p_structured_json,
        p_file_extension,
        p_file_mime_type,
        p_file_size_bytes,
        p_file_content,
        v_next_version,
        TRUE,
        p_created_by,
        p_created_by
    )
    RETURNING document_id INTO v_document_id;

    /*
     * Log document creation event
     */
    INSERT INTO event_log (
        entity_type,
        entity_id,
        event_type,
        payload,
        created_by
    )
    VALUES (
        'project_document',
        v_document_id,
        'project_document_created',
        jsonb_build_object(
            'project_id', p_project_id,
            'document_name', p_document_name,
            'version', v_next_version,
            'document_type', p_document_type
        ),
        p_created_by
    );
END;
$BODY$;
ALTER PROCEDURE main.sp_add_project_document(bigint, character varying, character varying, text, jsonb, character varying, character varying, bigint, bytea, character varying)
    OWNER TO postgres;
