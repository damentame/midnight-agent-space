-- ============================================================
-- MIGRATION: Update database schema for Sentence Transformers
-- ============================================================
-- This migration updates the embedding dimension from 1536 (OpenAI)
-- to 384 (Sentence Transformers all-MiniLM-L6-v2)
-- 
-- IMPORTANT: This will require regenerating all embeddings!
-- ============================================================

-- Step 1: Drop existing vector index (required before altering column)
DROP INDEX IF EXISTS main.idx_document_embedding_vector_hnsw;

-- Step 2: Delete all existing embeddings (they need to be regenerated with new dimensions)
-- Uncomment the line below if you want to clear existing embeddings
-- DELETE FROM main.document_embedding;

-- Step 3: Alter the embedding column to use 384 dimensions
-- Note: This will fail if there are existing embeddings with 1536 dimensions
-- You must delete existing embeddings first (see Step 2)
ALTER TABLE main.document_embedding 
    ALTER COLUMN embedding TYPE vector(384);

-- Step 4: Recreate the vector similarity index with new dimensions
CREATE INDEX idx_document_embedding_vector_hnsw 
    ON main.document_embedding 
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Step 5: Update default embedding model name
ALTER TABLE main.document_embedding 
    ALTER COLUMN embedding_model SET DEFAULT 'all-MiniLM-L6-v2';

-- Step 6: Update comments
COMMENT ON COLUMN main.document_embedding.embedding IS 'Sentence Transformers all-MiniLM-L6-v2 vector (384 dimensions)';

-- ============================================================
-- VERIFICATION
-- ============================================================
-- Run these queries to verify the migration:
-- 
-- SELECT 
--     column_name, 
--     data_type, 
--     udt_name 
-- FROM information_schema.columns 
-- WHERE table_schema = 'main' 
--   AND table_name = 'document_embedding' 
--   AND column_name = 'embedding';
--
-- Should show: vector(384)
-- ============================================================

