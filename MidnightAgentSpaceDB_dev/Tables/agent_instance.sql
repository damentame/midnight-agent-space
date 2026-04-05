-- Table: main.agent_instance

-- DROP TABLE IF EXISTS main.agent_instance;

-- Sequence: main.agent_instance_agent_instance_id_seq

-- DROP SEQUENCE IF EXISTS main.agent_instance_agent_instance_id_seq;

CREATE SEQUENCE IF NOT EXISTS main.agent_instance_agent_instance_id_seq
    INCREMENT 1
    START 1
    MINVALUE 1
    MAXVALUE 9223372036854775807
    CACHE 1;

ALTER SEQUENCE main.agent_instance_agent_instance_id_seq
    OWNER TO postgres;

CREATE TABLE IF NOT EXISTS main.agent_instance
(
    agent_instance_id bigint NOT NULL DEFAULT nextval('main.agent_instance_agent_instance_id_seq'::regclass),
    agent_id bigint NOT NULL,
    project_id bigint NOT NULL,
    instance_status character varying(50) COLLATE pg_catalog."default" DEFAULT 'ACTIVE'::character varying,
    spin_up_reason text COLLATE pg_catalog."default",
    instance_metadata jsonb,
    started_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    ended_at timestamp without time zone,
    created_by character varying(200) COLLATE pg_catalog."default",
    updated_by character varying(200) COLLATE pg_catalog."default",
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now(),
    CONSTRAINT agent_instance_pkey PRIMARY KEY (agent_instance_id)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS main.agent_instance
    OWNER to postgres;

-- Index: idx_agent_instance_agent

-- DROP INDEX IF EXISTS main.idx_agent_instance_agent;

CREATE INDEX IF NOT EXISTS idx_agent_instance_agent
    ON main.agent_instance USING btree
    (agent_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;

-- Index: idx_agent_instance_project

-- DROP INDEX IF EXISTS main.idx_agent_instance_project;

CREATE INDEX IF NOT EXISTS idx_agent_instance_project
    ON main.agent_instance USING btree
    (project_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;

-- Index: idx_agent_instance_status

-- DROP INDEX IF EXISTS main.idx_agent_instance_status;

CREATE INDEX IF NOT EXISTS idx_agent_instance_status
    ON main.agent_instance USING btree
    (instance_status COLLATE pg_catalog."default" ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;

-- Index: idx_agent_instance_agent_project

-- DROP INDEX IF EXISTS main.idx_agent_instance_agent_project;

CREATE INDEX IF NOT EXISTS idx_agent_instance_agent_project
    ON main.agent_instance USING btree
    (agent_id ASC NULLS LAST, project_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;

