-- Table: main.event_log

-- DROP TABLE IF EXISTS main.event_log;

-- Sequence: main.event_log_event_log_id_seq

-- DROP SEQUENCE IF EXISTS main.event_log_event_log_id_seq;

CREATE SEQUENCE IF NOT EXISTS main.event_log_event_log_id_seq
    INCREMENT 1
    START 1
    MINVALUE 1
    MAXVALUE 9223372036854775807
    CACHE 1;

ALTER SEQUENCE main.event_log_event_log_id_seq
    OWNER TO postgres;

CREATE TABLE IF NOT EXISTS main.event_log
(
    event_log_id bigint NOT NULL DEFAULT nextval('main.event_log_event_log_id_seq'::regclass),
    entity_type character varying(100) COLLATE pg_catalog."default",
    entity_id bigint,
    project_id bigint,
    event_type character varying(100) COLLATE pg_catalog."default",
    payload jsonb,
    created_by character varying(200) COLLATE pg_catalog."default",
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT event_log_pkey PRIMARY KEY (event_log_id)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS main.event_log
    OWNER to postgres;
-- Index: idx_event_log_entity

-- DROP INDEX IF EXISTS main.idx_event_log_entity;

CREATE INDEX IF NOT EXISTS idx_event_log_entity
    ON main.event_log USING btree
    (entity_type COLLATE pg_catalog."default" ASC NULLS LAST, entity_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;
-- Index: idx_event_log_event_type

-- DROP INDEX IF EXISTS main.idx_event_log_event_type;

CREATE INDEX IF NOT EXISTS idx_event_log_event_type
    ON main.event_log USING btree
    (event_type COLLATE pg_catalog."default" ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;

-- Index: idx_event_log_project

-- DROP INDEX IF EXISTS main.idx_event_log_project;

CREATE INDEX IF NOT EXISTS idx_event_log_project
    ON main.event_log USING btree
    (project_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;