/* Additive document processing status fields used by the RAG-ready document flow. */

ALTER TABLE IF EXISTS main.project_document
    ADD COLUMN IF NOT EXISTS embedding_status TEXT DEFAULT 'PENDING',
    ADD COLUMN IF NOT EXISTS embedding_model VARCHAR(100),
    ADD COLUMN IF NOT EXISTS embedded_at TIMESTAMP WITHOUT TIME ZONE,
    ADD COLUMN IF NOT EXISTS chunk_count INTEGER DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_project_document_embedding_status
    ON main.project_document (embedding_status);
