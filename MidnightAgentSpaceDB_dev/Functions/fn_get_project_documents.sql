-- FUNCTION: main.fn_get_project_documents(bigint)

-- DROP FUNCTION IF EXISTS main.fn_get_project_documents(bigint);

CREATE OR REPLACE FUNCTION main.fn_get_project_documents(
    p_project_id bigint
)
RETURNS jsonb
LANGUAGE 'plpgsql'
AS $BODY$
DECLARE
    v_documents jsonb;
BEGIN
    -- Fetch all active project documents for the project
    SELECT COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'document_id', document_id,
                'project_id', project_id,
                'document_name', document_name,
                'document_type', document_type,
                'raw_text_content', raw_text_content,
                'structured_json', structured_json,
                'file_extension', file_extension,
                'file_mime_type', file_mime_type,
                'file_size_bytes', file_size_bytes,
                'version_number', version_number,
                'is_active_version', is_active_version,
                'serialization_status', serialization_status,
                'serialized_payload', serialized_payload
            )
            ORDER BY document_id
        ),
        '[]'::jsonb
    )
    INTO v_documents
    FROM main.project_document
    WHERE project_id = p_project_id
      AND is_active_version = TRUE;
    
    RETURN jsonb_build_object(
        'project_id', p_project_id,
        'documents', v_documents,
        'document_count', jsonb_array_length(v_documents)
    );
END;
$BODY$;

ALTER FUNCTION main.fn_get_project_documents(bigint)
    OWNER TO postgres;

