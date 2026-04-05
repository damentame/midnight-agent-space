-- Table: main.project

-- DROP TABLE IF EXISTS main.project;

CREATE TABLE IF NOT EXISTS main.project
(
    project_id bigint NOT NULL DEFAULT nextval('main.project_project_id_seq'::regclass),
    project_name character varying(255) COLLATE pg_catalog."default",
    project_type character varying(100) COLLATE pg_catalog."default",
    description text COLLATE pg_catalog."default",
    status character varying(50) COLLATE pg_catalog."default",
    created_by character varying(200) COLLATE pg_catalog."default",
    updated_by character varying(200) COLLATE pg_catalog."default",
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT project_pkey PRIMARY KEY (project_id)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS main.project
    OWNER to postgres;
-- Index: idx_project_name

-- DROP INDEX IF EXISTS main.idx_project_name;

CREATE INDEX IF NOT EXISTS idx_project_name
    ON main.project USING btree
    (project_name COLLATE pg_catalog."default" ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;
-- Index: idx_project_status

-- DROP INDEX IF EXISTS main.idx_project_status;

CREATE INDEX IF NOT EXISTS idx_project_status
    ON main.project USING btree
    (status COLLATE pg_catalog."default" ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;
-- Index: idx_project_type

-- DROP INDEX IF EXISTS main.idx_project_type;

CREATE INDEX IF NOT EXISTS idx_project_type
    ON main.project USING btree
    (project_type COLLATE pg_catalog."default" ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;