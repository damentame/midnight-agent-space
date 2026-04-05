-- Table: main.workflow_run

-- DROP TABLE IF EXISTS main.workflow_run;

-- Sequence: main.workflow_run_workflow_run_id_seq

-- DROP SEQUENCE IF EXISTS main.workflow_run_workflow_run_id_seq;

CREATE SEQUENCE IF NOT EXISTS main.workflow_run_workflow_run_id_seq
    INCREMENT 1
    START 1
    MINVALUE 1
    MAXVALUE 9223372036854775807
    CACHE 1;

ALTER SEQUENCE main.workflow_run_workflow_run_id_seq
    OWNER TO postgres;

CREATE TABLE IF NOT EXISTS main.workflow_run
(
    workflow_run_id bigint NOT NULL DEFAULT nextval('main.workflow_run_workflow_run_id_seq'::regclass),
    workflow_name character varying(255) COLLATE pg_catalog."default",
    project_id bigint,
    agent_instance_id bigint,
    status character varying(50) COLLATE pg_catalog."default",
    input_data jsonb,
    result_data jsonb,
    started_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    finished_at timestamp without time zone,
    created_by character varying(200) COLLATE pg_catalog."default",
    updated_by character varying(200) COLLATE pg_catalog."default",
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT workflow_run_pkey PRIMARY KEY (workflow_run_id)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS main.workflow_run
    OWNER to postgres;
-- Index: idx_workflow_run_name

-- DROP INDEX IF EXISTS main.idx_workflow_run_name;

CREATE INDEX IF NOT EXISTS idx_workflow_run_name
    ON main.workflow_run USING btree
    (workflow_name COLLATE pg_catalog."default" ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;
-- Index: idx_workflow_run_status

-- DROP INDEX IF EXISTS main.idx_workflow_run_status;

CREATE INDEX IF NOT EXISTS idx_workflow_run_status
    ON main.workflow_run USING btree
    (status COLLATE pg_catalog."default" ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;

-- Index: idx_workflow_run_agent_instance

-- DROP INDEX IF EXISTS main.idx_workflow_run_agent_instance;

CREATE INDEX IF NOT EXISTS idx_workflow_run_agent_instance
    ON main.workflow_run USING btree
    (agent_instance_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;

-- Index: idx_workflow_run_project

-- DROP INDEX IF EXISTS main.idx_workflow_run_project;

CREATE INDEX IF NOT EXISTS idx_workflow_run_project
    ON main.workflow_run USING btree
    (project_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;