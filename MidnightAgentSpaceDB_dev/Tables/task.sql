-- Table: main.task

-- DROP TABLE IF EXISTS main.task;

CREATE TABLE IF NOT EXISTS main.task
(
    task_id bigint NOT NULL DEFAULT nextval('main.task_task_id_seq'::regclass),
    project_id bigint,
    agent_id bigint,
    document_id bigint,
    task_name character varying(255) COLLATE pg_catalog."default",
    task_type character varying(100) COLLATE pg_catalog."default",
    description text COLLATE pg_catalog."default",
    parameters jsonb,
    status character varying(50) COLLATE pg_catalog."default",
    priority integer,
    task_notes text COLLATE pg_catalog."default",
    task_data jsonb,
    created_by character varying(200) COLLATE pg_catalog."default",
    updated_by character varying(200) COLLATE pg_catalog."default",
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT task_pkey PRIMARY KEY (task_id)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS main.task
    OWNER to postgres;
-- Index: idx_task_agent

-- DROP INDEX IF EXISTS main.idx_task_agent;

CREATE INDEX IF NOT EXISTS idx_task_agent
    ON main.task USING btree
    (agent_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;
-- Index: idx_task_priority

-- DROP INDEX IF EXISTS main.idx_task_priority;

CREATE INDEX IF NOT EXISTS idx_task_priority
    ON main.task USING btree
    (priority ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;
-- Index: idx_task_project

-- DROP INDEX IF EXISTS main.idx_task_project;

CREATE INDEX IF NOT EXISTS idx_task_project
    ON main.task USING btree
    (project_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;
-- Index: idx_task_status

-- DROP INDEX IF EXISTS main.idx_task_status;

CREATE INDEX IF NOT EXISTS idx_task_status
    ON main.task USING btree
    (status COLLATE pg_catalog."default" ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;