-- PROCEDURE: main.sp_chunk_and_embed_document(bigint, integer, integer, character varying)

-- DROP PROCEDURE IF EXISTS main.sp_chunk_and_embed_document(bigint, integer, integer, character varying);

CREATE OR REPLACE PROCEDURE main.sp_chunk_and_embed_document(
    IN p_document_id bigint,
    IN p_chunk_size integer DEFAULT 1000,
    IN p_chunk_overlap integer DEFAULT 200,
    IN p_embedding_model character varying DEFAULT 'text-embedding-3-small',
    IN p_updated_by character varying DEFAULT 'system'
)
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
    
    -- If content is empty, raise error
    IF v_content IS NULL OR v_content = '' THEN
        RAISE EXCEPTION 'Document (document_id=%) has no content to chunk', p_document_id;
    END IF;
    
    -- Update status to processing
    UPDATE main.project_document
    SET 
        embedding_status = 'PROCESSING',
        updated_by = p_updated_by,
        updated_at = CURRENT_TIMESTAMP
    WHERE document_id = p_document_id;
    
    -- Simple chunking logic (splits by character count)
    -- Note: In production, you might want more sophisticated chunking (by sentences, paragraphs, etc.)
    WHILE v_start_pos <= v_content_length
    LOOP
        v_end_pos := LEAST(v_start_pos + p_chunk_size - 1, v_content_length);
        v_chunk_text := substring(v_content from v_start_pos for (v_end_pos - v_start_pos + 1));
        
        -- Add chunk to array (embedding will be added by external API call)
        v_chunks := v_chunks || jsonb_build_object(
            'chunk_index', v_chunk_index,
            'chunk_text', v_chunk_text,
            'chunk_metadata', jsonb_build_object(
                'start_pos', v_start_pos,
                'end_pos', v_end_pos,
                'chunk_size', length(v_chunk_text),
                'document_name', v_document.document_name,
                'document_type', v_document.document_type
            ),
            'token_count', NULL, -- Will be calculated by embedding API
            'embedding', NULL -- Will be populated by embedding API
        );
        
        v_chunk_index := v_chunk_index + 1;
        v_start_pos := v_end_pos - p_chunk_overlap + 1;
        
        -- Safety check to avoid infinite loop
        IF v_start_pos <= (v_end_pos - p_chunk_overlap + 1) AND v_end_pos >= v_content_length THEN
            EXIT;
        END IF;
    END LOOP;
    
    -- Return chunks as result (these will need to be sent to embedding API)
    -- The chunks JSON will be used by n8n to call embedding API, then stored via sp_store_document_chunks
    RAISE NOTICE 'Document chunked into % chunks', v_chunk_index;
    
    -- Note: This procedure prepares chunks for embedding
    -- Actual embedding should be done via external API (OpenAI, Cohere, etc.) in n8n
    -- Then use sp_store_document_chunks to store the chunks with embeddings
END;
$BODY$;

ALTER PROCEDURE main.sp_chunk_and_embed_document(bigint, integer, integer, character varying, character varying)
    OWNER TO postgres;

