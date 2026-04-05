-- Table: main.project_document

-- DROP TABLE IF EXISTS main.project_document;

CREATE TABLE IF NOT EXISTS main.project_document
(
    document_id bigint NOT NULL DEFAULT nextval('main.project_document_document_id_seq'::regclass),
    project_id bigint,
    parent_document_id bigint,
    document_name character varying(255) COLLATE pg_catalog."default",
    document_type character varying(100) COLLATE pg_catalog."default",
    raw_text_content text COLLATE pg_catalog."default",
    structured_json jsonb,
    file_extension character varying(20) COLLATE pg_catalog."default",
    file_mime_type character varying(150) COLLATE pg_catalog."default",
    file_size_bytes bigint,
    file_content bytea,
    version_number integer,
    is_active_version boolean,
    created_by character varying(100) COLLATE pg_catalog."default",
    updated_by character varying(100) COLLATE pg_catalog."default",
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    serialization_status text COLLATE pg_catalog."default" DEFAULT 'PENDING'::text,
    serialized_payload jsonb,
    serialized_at timestamp without time zone,
    embedding_status text COLLATE pg_catalog."default" DEFAULT 'PENDING'::text,
    embedding_model character varying(100) COLLATE pg_catalog."default",
    embedded_at timestamp without time zone,
    chunk_count integer DEFAULT 0,
    CONSTRAINT project_document_pkey PRIMARY KEY (document_id)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS main.project_document
    OWNER to postgres;
-- Index: idx_project_document_parent

-- DROP INDEX IF EXISTS main.idx_project_document_parent;

CREATE INDEX IF NOT EXISTS idx_project_document_parent
    ON main.project_document USING btree
    (parent_document_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;
-- Index: idx_project_document_project

-- DROP INDEX IF EXISTS main.idx_project_document_project;

CREATE INDEX IF NOT EXISTS idx_project_document_project
    ON main.project_document USING btree
    (project_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;
-- Index: idx_project_document_type

-- DROP INDEX IF EXISTS main.idx_project_document_type;

CREATE INDEX IF NOT EXISTS idx_project_document_type
    ON main.project_document USING btree
    (document_type COLLATE pg_catalog."default" ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;

-- Index: idx_project_document_embedding_status

-- DROP INDEX IF EXISTS main.idx_project_document_embedding_status;

CREATE INDEX IF NOT EXISTS idx_project_document_embedding_status
    ON main.project_document USING btree
    (embedding_status COLLATE pg_catalog."default" ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;