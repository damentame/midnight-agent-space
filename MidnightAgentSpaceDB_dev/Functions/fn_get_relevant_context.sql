-- FUNCTION: main.fn_get_relevant_context(vector, bigint, integer)

-- DROP FUNCTION IF EXISTS main.fn_get_relevant_context(vector, bigint, integer);

CREATE OR REPLACE FUNCTION main.fn_get_relevant_context(
    p_query_embedding vector(1536),
    p_project_id bigint,
    p_limit integer DEFAULT 5
)
RETURNS text
LANGUAGE 'plpgsql'
AS $BODY$
DECLARE
    v_context_text text := '';
    v_chunk RECORD;
BEGIN
    -- Get relevant chunks ordered by similarity
    FOR v_chunk IN
        SELECT 
            dc.chunk_text,
            pd.document_name,
            (1 - (dc.embedding <=> p_query_embedding)) as similarity
        FROM main.document_chunk dc
        INNER JOIN main.project_document pd ON dc.document_id = pd.document_id
        WHERE dc.embedding IS NOT NULL
          AND dc.project_id = p_project_id
        ORDER BY dc.embedding <=> p_query_embedding
        LIMIT p_limit
    LOOP
        v_context_text := v_context_text || 
            format('\n--- Document: %s (Similarity: %.2f) ---\n%s\n', 
                   v_chunk.document_name, 
                   v_chunk.similarity,
                   v_chunk.chunk_text);
    END LOOP;
    
    RETURN v_context_text;
END;
$BODY$;

ALTER FUNCTION main.fn_get_relevant_context(vector, bigint, integer)
    OWNER TO postgres;

