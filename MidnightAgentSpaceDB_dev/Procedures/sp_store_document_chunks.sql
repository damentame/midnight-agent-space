-- PROCEDURE: main.sp_store_document_chunks(bigint, jsonb, character varying)

-- DROP PROCEDURE IF EXISTS main.sp_store_document_chunks(bigint, jsonb, character varying);

CREATE OR REPLACE PROCEDURE main.sp_store_document_chunks(
    IN p_document_id bigint,
    IN p_chunks jsonb,
    IN p_embedding_model character varying DEFAULT 'text-embedding-3-small',
    IN p_updated_by character varying DEFAULT 'system'
)
LANGUAGE 'plpgsql'
AS $BODY$
DECLARE
    v_chunk jsonb;
    v_document_rec RECORD;
    v_chunk_count integer := 0;
    v_embedding_vector vector(1536);
    v_embedding_json jsonb;
    v_embedding_str text;
BEGIN
    -- Get document info
    SELECT project_id, document_name
    INTO v_document_rec
    FROM main.project_document
    WHERE document_id = p_document_id;
    
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Document (document_id=%) not found', p_document_id;
    END IF;
    
    -- Delete existing chunks for this document
    DELETE FROM main.document_chunk
    WHERE document_id = p_document_id;
    
    -- Insert new chunks
    FOR v_chunk IN SELECT * FROM jsonb_array_elements(p_chunks)
    LOOP
        BEGIN
            -- Handle embedding conversion (can be array or string)
            v_embedding_vector := NULL;
            
            IF v_chunk->'embedding' IS NOT NULL AND v_chunk->'embedding' != 'null'::jsonb THEN
                v_embedding_json := v_chunk->'embedding';
                IF jsonb_typeof(v_embedding_json) = 'array' THEN
                    -- Convert JSON array to PostgreSQL array format: [1,2,3] -> '{1,2,3}'::vector
                    -- pgvector accepts PostgreSQL array format
                    v_embedding_vector := (
                        SELECT ('{' || string_agg(value::text, ',') || '}')::vector
                        FROM jsonb_array_elements(v_embedding_json) AS elem(value)
                    );
                ELSIF jsonb_typeof(v_embedding_json) = 'string' THEN
                    -- If it's already a string, try to parse it
                    -- Could be comma-separated or array format
                    BEGIN
                        v_embedding_str := v_chunk->>'embedding';
                        -- Remove brackets if present and convert to array format
                        v_embedding_str := replace(replace(v_embedding_str, '[', ''), ']', '');
                        v_embedding_vector := ('{' || v_embedding_str || '}')::vector;
                    EXCEPTION
                        WHEN OTHERS THEN
                            v_embedding_vector := NULL;
                    END;
                END IF;
            END IF;
            
            INSERT INTO main.document_chunk (
                document_id,
                project_id,
                chunk_index,
                chunk_text,
                chunk_metadata,
                embedding,
                token_count
            )
            VALUES (
                p_document_id,
                v_document_rec.project_id,
                (v_chunk->>'chunk_index')::integer,
                v_chunk->>'chunk_text',
                COALESCE(v_chunk->'chunk_metadata', '{}'::jsonb),
                v_embedding_vector,
                CASE 
                    WHEN v_chunk->>'token_count' IS NOT NULL AND v_chunk->>'token_count' != 'null'
                    THEN (v_chunk->>'token_count')::integer 
                    ELSE NULL 
                END
            );
            
            v_chunk_count := v_chunk_count + 1;
        EXCEPTION
            WHEN OTHERS THEN
                -- Log error but continue with other chunks
                RAISE WARNING 'Error inserting chunk %: %', (v_chunk->>'chunk_index'), SQLERRM;
        END;
    END LOOP;
    
    -- Update document with embedding status
    UPDATE main.project_document
    SET 
        embedding_status = 'COMPLETED',
        embedding_model = p_embedding_model,
        embedded_at = CURRENT_TIMESTAMP,
        chunk_count = v_chunk_count,
        updated_by = p_updated_by,
        updated_at = CURRENT_TIMESTAMP
    WHERE document_id = p_document_id;
    
    -- Log the embedding event
    INSERT INTO main.event_log (
        entity_type,
        entity_id,
        project_id,
        event_type,
        payload,
        created_by
    )
    VALUES (
        'project_document',
        p_document_id,
        v_document_rec.project_id,
        'document_embedded',
        jsonb_build_object(
            'document_id', p_document_id,
            'document_name', v_document_rec.document_name,
            'chunk_count', v_chunk_count,
            'embedding_model', p_embedding_model,
            'timestamp', CURRENT_TIMESTAMP
        ),
        p_updated_by
    );
END;
$BODY$;

ALTER PROCEDURE main.sp_store_document_chunks(bigint, jsonb, character varying, character varying)
    OWNER TO postgres;

