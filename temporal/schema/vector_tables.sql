-- ============================================================
-- VECTOR STORAGE TABLES FOR RAG (RETRIEVAL AUGMENTED GENERATION)
-- ============================================================
-- These tables store document chunks and their vector embeddings
-- following the same design principles as other tables:
-- - No foreign keys
-- - Redundant references (document_id, project_id)
-- - BIGSERIAL primary keys
-- ============================================================

-- Create main schema if it doesn't exist
CREATE SCHEMA IF NOT EXISTS main;

-- Enable pgvector extension if not already enabled
CREATE EXTENSION IF NOT EXISTS vector;

/* ============================================================
   1. DOCUMENT CHUNK
   ============================================================ */
CREATE TABLE IF NOT EXISTS main.document_chunk (
    chunk_id          BIGSERIAL,
    document_id       BIGINT NOT NULL,
    project_id        BIGINT NOT NULL,
    chunk_index       INT NOT NULL,
    chunk_text        TEXT NOT NULL,
    chunk_metadata    JSONB,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_document_chunk_document ON main.document_chunk(document_id);
CREATE INDEX idx_document_chunk_project ON main.document_chunk(project_id);
CREATE INDEX idx_document_chunk_index ON main.document_chunk(document_id, chunk_index);

COMMENT ON TABLE main.document_chunk IS 'Stores semantic chunks of documents for RAG';
COMMENT ON COLUMN main.document_chunk.chunk_index IS 'Order of chunk within document (0-based)';
COMMENT ON COLUMN main.document_chunk.chunk_metadata IS 'JSONB with start_pos, end_pos, token_count, etc.';

/* ============================================================
   2. DOCUMENT EMBEDDING
   ============================================================ */
CREATE TABLE IF NOT EXISTS main.document_embedding (
    embedding_id      BIGSERIAL,
    chunk_id          BIGINT NOT NULL,
    document_id       BIGINT NOT NULL,
    project_id        BIGINT NOT NULL,
    embedding         vector(384) NOT NULL,
    embedding_model   VARCHAR(100) NOT NULL DEFAULT 'all-MiniLM-L6-v2',
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_document_embedding_chunk ON main.document_embedding(chunk_id);
CREATE INDEX idx_document_embedding_document ON main.document_embedding(document_id);
CREATE INDEX idx_document_embedding_project ON main.document_embedding(project_id);

-- Vector similarity index using HNSW for efficient search
CREATE INDEX IF NOT EXISTS idx_document_embedding_vector_hnsw 
    ON main.document_embedding 
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

COMMENT ON TABLE main.document_embedding IS 'Stores vector embeddings for document chunks';
COMMENT ON COLUMN main.document_embedding.embedding IS 'Sentence Transformers all-MiniLM-L6-v2 vector (384 dimensions)';
COMMENT ON COLUMN main.document_embedding.embedding_model IS 'Model identifier used to generate embedding';

