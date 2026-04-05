-- Table: main.activity_run

-- DROP TABLE IF EXISTS main.activity_run;

-- Sequence: main.activity_run_activity_run_id_seq

-- DROP SEQUENCE IF EXISTS main.activity_run_activity_run_id_seq;

CREATE SEQUENCE IF NOT EXISTS main.activity_run_activity_run_id_seq
    INCREMENT 1
    START 1
    MINVALUE 1
    MAXVALUE 9223372036854775807
    CACHE 1;

ALTER SEQUENCE main.activity_run_activity_run_id_seq
    OWNER TO postgres;

CREATE TABLE IF NOT EXISTS main.activity_run
(
    activity_run_id bigint NOT NULL DEFAULT nextval('main.activity_run_activity_run_id_seq'::regclass),
    workflow_id character varying(255) COLLATE pg_catalog."default",
    run_id character varying(255) COLLATE pg_catalog."default",
    activity_type character varying(255) COLLATE pg_catalog."default",
    activity_id character varying(255) COLLATE pg_catalog."default",
    status character varying(50) COLLATE pg_catalog."default",
    input_data jsonb,
    result_data jsonb,
    error_message text COLLATE pg_catalog."default",
    started_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    finished_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT activity_run_pkey PRIMARY KEY (activity_run_id)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS main.activity_run
    OWNER to postgres;

-- Index: idx_activity_run_workflow

-- DROP INDEX IF EXISTS main.idx_activity_run_workflow;

CREATE INDEX IF NOT EXISTS idx_activity_run_workflow
    ON main.activity_run USING btree
    (workflow_id COLLATE pg_catalog."default" ASC NULLS LAST, run_id COLLATE pg_catalog."default" ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;

-- Index: idx_activity_run_status

-- DROP INDEX IF EXISTS main.idx_activity_run_status;

CREATE INDEX IF NOT EXISTS idx_activity_run_status
    ON main.activity_run USING btree
    (status COLLATE pg_catalog."default" ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;

