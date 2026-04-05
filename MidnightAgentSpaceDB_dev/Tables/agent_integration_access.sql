-- Table: main.agent_integration_access

-- DROP TABLE IF EXISTS main.agent_integration_access;

CREATE TABLE IF NOT EXISTS main.agent_integration_access
(
    access_id bigint NOT NULL DEFAULT nextval('main.agent_integration_access_access_id_seq'::regclass),
    agent_id bigint,
    integration_id bigint,
    access_level character varying(50) COLLATE pg_catalog."default",
    granted_by character varying(200) COLLATE pg_catalog."default",
    granted_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT agent_integration_access_pkey PRIMARY KEY (access_id)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS main.agent_integration_access
    OWNER to postgres;
-- Index: idx_agent_integration_access_agent

-- DROP INDEX IF EXISTS main.idx_agent_integration_access_agent;

CREATE INDEX IF NOT EXISTS idx_agent_integration_access_agent
    ON main.agent_integration_access USING btree
    (agent_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;
-- Index: idx_agent_integration_access_integration

-- DROP INDEX IF EXISTS main.idx_agent_integration_access_integration;

CREATE INDEX IF NOT EXISTS idx_agent_integration_access_integration
    ON main.agent_integration_access USING btree
    (integration_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;