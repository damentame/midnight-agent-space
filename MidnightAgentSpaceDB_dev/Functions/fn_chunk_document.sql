-- FUNCTION: main.fn_chunk_document(bigint, integer, integer)

-- DROP FUNCTION IF EXISTS main.fn_chunk_document(bigint, integer, integer);

CREATE OR REPLACE FUNCTION main.fn_chunk_document(
    p_document_id bigint,
    p_chunk_size integer DEFAULT 1000,
    p_chunk_overlap integer DEFAULT 200
)
RETURNS jsonb
LANGUAGE 'plpgsql'
AS $BODY$
DECLARE
    v_document RECORD;
    v_content text;
    v_chunks jsonb := '[]'::jsonb;
    v_chunk_text text;
    v_start_pos integer := 1;
    v_end_pos integer;
    v_content_length integer;
    v_chunk_index integer := 0;
BEGIN
    -- Get document content
    SELECT 
        pd.project_id,
        pd.document_name,
        pd.document_type,
        COALESCE(pd.raw_text_content, convert_from(pd.file_content, 'UTF8'), '') as content
    INTO v_document
    FROM main.project_document pd
    WHERE pd.document_id = p_document_id;
    
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Document (document_id=%) not found', p_document_id;
    END IF;
    
    v_content := v_document.content;
    v_content_length := length(v_content);
    
    -- If content is empty, return empty array
    IF v_content IS NULL OR v_content = '' THEN
        RETURN jsonb_build_object(
            'document_id', p_document_id,
            'chunks', '[]'::jsonb,
            'chunk_count', 0,
            'error', 'Document has no content'
        );
    END IF;
    
    -- Simple chunking logic (splits by character count)
    -- Note: In production, you might want more sophisticated chunking (by sentences, paragraphs, etc.)
    WHILE v_start_pos <= v_content_length
    LOOP
        v_end_pos := LEAST(v_start_pos + p_chunk_size - 1, v_content_length);
        v_chunk_text := substring(v_content from v_start_pos for (v_end_pos - v_start_pos + 1));
        
        -- Add chunk to array
        v_chunks := v_chunks || jsonb_build_object(
            'chunk_index', v_chunk_index,
            'chunk_text', v_chunk_text,
            'chunk_metadata', jsonb_build_object(
                'start_pos', v_start_pos,
                'end_pos', v_end_pos,
                'chunk_size', length(v_chunk_text),
                'document_name', v_document.document_name,
                'document_type', v_document.document_type
            )
        );
        
        v_chunk_index := v_chunk_index + 1;
        v_start_pos := v_end_pos - p_chunk_overlap + 1;
        
        -- Safety check to avoid infinite loop
        IF v_start_pos > v_end_pos - p_chunk_overlap + 1 OR v_end_pos >= v_content_length THEN
            IF v_start_pos >= v_content_length THEN
                EXIT;
            END IF;
        END IF;
        
        -- Prevent infinite loops
        IF v_chunk_index > 10000 THEN
            RAISE EXCEPTION 'Too many chunks generated (limit: 10000)';
        END IF;
    END LOOP;
    
    RETURN jsonb_build_object(
        'document_id', p_document_id,
        'project_id', v_document.project_id,
        'document_name', v_document.document_name,
        'chunks', v_chunks,
        'chunk_count', v_chunk_index
    );
END;
$BODY$;

ALTER FUNCTION main.fn_chunk_document(bigint, integer, integer)
    OWNER TO postgres;

