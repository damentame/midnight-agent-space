-- FUNCTION: main.fn_get_or_create_code_document(bigint)
-- Returns a stable document_id for "code context" RAG per project.
-- Uses main.project_document with document_name='__codebase__', document_type='code'.
-- DROP FUNCTION IF EXISTS main.fn_get_or_create_code_document(bigint);

CREATE OR REPLACE FUNCTION main.fn_get_or_create_code_document(
    p_project_id bigint
)
RETURNS bigint
LANGUAGE 'plpgsql'
AS $BODY$
DECLARE
    v_document_id bigint;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'main' AND table_name = 'project_document'
    ) THEN
        RAISE EXCEPTION 'main.project_document table not found';
    END IF;

    SELECT document_id INTO v_document_id
    FROM main.project_document
    WHERE project_id = p_project_id
      AND document_name = '__codebase__'
      AND document_type = 'code'
    LIMIT 1;

    IF FOUND THEN
        RETURN v_document_id;
    END IF;

    INSERT INTO main.project_document (
        project_id,
        document_name,
        document_type,
        created_by
    )
    VALUES (
        p_project_id,
        '__codebase__',
        'code',
        'system'
    )
    RETURNING document_id INTO v_document_id;

    RETURN v_document_id;
END;
$BODY$;

ALTER FUNCTION main.fn_get_or_create_code_document(bigint) OWNER TO postgres;
