-- FUNCTION: main.fn_search_documents_rag(vector, bigint, integer, numeric)

-- DROP FUNCTION IF EXISTS main.fn_search_documents_rag(vector, bigint, integer, numeric);

CREATE OR REPLACE FUNCTION main.fn_search_documents_rag(
    p_query_embedding vector(1536),
    p_project_id bigint DEFAULT NULL,
    p_limit integer DEFAULT 10,
    p_similarity_threshold numeric DEFAULT 0.7
)
RETURNS jsonb
LANGUAGE 'plpgsql'
AS $BODY$
DECLARE
    v_results jsonb;
BEGIN
    -- Search for relevant document chunks using cosine similarity
    SELECT COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'chunk_id', dc.chunk_id,
                'document_id', dc.document_id,
                'project_id', dc.project_id,
                'chunk_index', dc.chunk_index,
                'chunk_text', dc.chunk_text,
                'chunk_metadata', dc.chunk_metadata,
                'similarity_score', 1 - (dc.embedding <=> p_query_embedding),
                'document_name', pd.document_name,
                'document_type', pd.document_type
            )
            ORDER BY dc.embedding <=> p_query_embedding
        ),
        '[]'::jsonb
    )
    INTO v_results
    FROM main.document_chunk dc
    INNER JOIN main.project_document pd ON dc.document_id = pd.document_id
    WHERE dc.embedding IS NOT NULL
      AND (p_project_id IS NULL OR dc.project_id = p_project_id)
      AND (1 - (dc.embedding <=> p_query_embedding)) >= p_similarity_threshold
    ORDER BY dc.embedding <=> p_query_embedding
    LIMIT p_limit;
    
    RETURN jsonb_build_object(
        'results', v_results,
        'count', jsonb_array_length(v_results),
        'similarity_threshold', p_similarity_threshold
    );
END;
$BODY$;

ALTER FUNCTION main.fn_search_documents_rag(vector, bigint, integer, numeric)
    OWNER TO postgres;

