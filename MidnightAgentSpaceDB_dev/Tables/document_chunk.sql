-- Table: main.document_chunk
-- Stores document chunks with vector embeddings for RAG (Retrieval Augmented Generation)

-- DROP TABLE IF EXISTS main.document_chunk;

CREATE TABLE IF NOT EXISTS main.document_chunk
(
    chunk_id bigint NOT NULL DEFAULT nextval('main.document_chunk_chunk_id_seq'::regclass),
    document_id bigint NOT NULL,
    project_id bigint NOT NULL,
    chunk_index integer NOT NULL,
    chunk_text text COLLATE pg_catalog."default" NOT NULL,
    chunk_metadata jsonb,
    embedding vector(1536),
    token_count integer,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT document_chunk_pkey PRIMARY KEY (chunk_id)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS main.document_chunk
    OWNER to postgres;

-- Sequence: main.document_chunk_chunk_id_seq

-- DROP SEQUENCE IF EXISTS main.document_chunk_chunk_id_seq;

CREATE SEQUENCE IF NOT EXISTS main.document_chunk_chunk_id_seq
    INCREMENT 1
    START 1
    MINVALUE 1
    MAXVALUE 9223372036854775807
    CACHE 1;

ALTER SEQUENCE main.document_chunk_chunk_id_seq
    OWNER TO postgres;

-- Index: idx_document_chunk_document

-- DROP INDEX IF EXISTS main.idx_document_chunk_document;

CREATE INDEX IF NOT EXISTS idx_document_chunk_document
    ON main.document_chunk USING btree
    (document_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;

-- Index: idx_document_chunk_project

-- DROP INDEX IF EXISTS main.idx_document_chunk_project;

CREATE INDEX IF NOT EXISTS idx_document_chunk_project
    ON main.document_chunk USING btree
    (project_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;

-- Index: idx_document_chunk_document_index

-- DROP INDEX IF EXISTS main.idx_document_chunk_document_index;

CREATE INDEX IF NOT EXISTS idx_document_chunk_document_index
    ON main.document_chunk USING btree
    (document_id ASC NULLS LAST, chunk_index ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;

-- Index: idx_document_chunk_embedding

-- DROP INDEX IF EXISTS main.idx_document_chunk_embedding;

CREATE INDEX IF NOT EXISTS idx_document_chunk_embedding
    ON main.document_chunk USING ivfflat
    (embedding vector_cosine_ops)
    WITH (lists = 100)
    TABLESPACE pg_default;

