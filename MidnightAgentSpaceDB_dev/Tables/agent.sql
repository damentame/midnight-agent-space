-- Table: main.agent

-- DROP TABLE IF EXISTS main.agent;

CREATE TABLE IF NOT EXISTS main.agent
(
    agent_id bigint NOT NULL DEFAULT nextval('main.agent_agent_id_seq'::regclass),
    agent_name character varying(255) COLLATE pg_catalog."default",
    agent_type character varying(100) COLLATE pg_catalog."default",
    agent_role_id bigint,
    api_key character varying(1000) COLLATE pg_catalog."default",
    endpoint_url character varying(1000) COLLATE pg_catalog."default",
    agent_status character varying(50) COLLATE pg_catalog."default" DEFAULT 'ACTIVE'::character varying,
    agent_last_seen timestamp without time zone,
    capabilities jsonb,
    config jsonb,
    created_by character varying(200) COLLATE pg_catalog."default",
    updated_by character varying(200) COLLATE pg_catalog."default",
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now(),
    CONSTRAINT agent_pkey PRIMARY KEY (agent_id)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS main.agent
    OWNER to postgres;
-- Index: idx_agent_name

-- DROP INDEX IF EXISTS main.idx_agent_name;

CREATE INDEX IF NOT EXISTS idx_agent_name
    ON main.agent USING btree
    (agent_name COLLATE pg_catalog."default" ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;
-- Index: idx_agent_status

-- DROP INDEX IF EXISTS main.idx_agent_status;

CREATE INDEX IF NOT EXISTS idx_agent_status
    ON main.agent USING btree
    (agent_status COLLATE pg_catalog."default" ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;
-- Index: idx_agent_type

-- DROP INDEX IF EXISTS main.idx_agent_type;

CREATE INDEX IF NOT EXISTS idx_agent_type
    ON main.agent USING btree
    (agent_type COLLATE pg_catalog."default" ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;