-- Table: main.task_execution

-- DROP TABLE IF EXISTS main.task_execution;

-- Sequence: main.task_execution_task_execution_id_seq

-- DROP SEQUENCE IF EXISTS main.task_execution_task_execution_id_seq;

CREATE SEQUENCE IF NOT EXISTS main.task_execution_task_execution_id_seq
    INCREMENT 1
    START 1
    MINVALUE 1
    MAXVALUE 9223372036854775807
    CACHE 1;

ALTER SEQUENCE main.task_execution_task_execution_id_seq
    OWNER TO postgres;

CREATE TABLE IF NOT EXISTS main.task_execution
(
    task_execution_id bigint NOT NULL DEFAULT nextval('main.task_execution_task_execution_id_seq'::regclass),
    task_id bigint,
    agent_id bigint,
    agent_instance_id bigint,
    task_execution_status character varying(50) COLLATE pg_catalog."default",
    task_execution_notes text COLLATE pg_catalog."default",
    task_execution_result jsonb,
    logs text COLLATE pg_catalog."default",
    started_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    finished_at timestamp without time zone,
    CONSTRAINT task_execution_pkey PRIMARY KEY (task_execution_id)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS main.task_execution
    OWNER to postgres;
-- Index: idx_task_execution_agent

-- DROP INDEX IF EXISTS main.idx_task_execution_agent;

CREATE INDEX IF NOT EXISTS idx_task_execution_agent
    ON main.task_execution USING btree
    (agent_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;
-- Index: idx_task_execution_status

-- DROP INDEX IF EXISTS main.idx_task_execution_status;

CREATE INDEX IF NOT EXISTS idx_task_execution_status
    ON main.task_execution USING btree
    (task_execution_status COLLATE pg_catalog."default" ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;
-- Index: idx_task_execution_task

-- DROP INDEX IF EXISTS main.idx_task_execution_task;

CREATE INDEX IF NOT EXISTS idx_task_execution_task
    ON main.task_execution USING btree
    (task_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;

-- Index: idx_task_execution_agent_instance

-- DROP INDEX IF EXISTS main.idx_task_execution_agent_instance;

CREATE INDEX IF NOT EXISTS idx_task_execution_agent_instance
    ON main.task_execution USING btree
    (agent_instance_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;