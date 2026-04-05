-- Table: main.agent_state

-- DROP TABLE IF EXISTS main.agent_state;

CREATE TABLE IF NOT EXISTS main.agent_state
(
    state_id bigint NOT NULL DEFAULT nextval('main.agent_state_state_id_seq'::regclass),
    agent_id bigint,
    state_key character varying(200) COLLATE pg_catalog."default",
    state_value jsonb,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT agent_state_pkey PRIMARY KEY (state_id)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS main.agent_state
    OWNER to postgres;
-- Index: idx_agent_state_agent

-- DROP INDEX IF EXISTS main.idx_agent_state_agent;

CREATE INDEX IF NOT EXISTS idx_agent_state_agent
    ON main.agent_state USING btree
    (agent_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;
-- Index: idx_agent_state_key

-- DROP INDEX IF EXISTS main.idx_agent_state_key;

CREATE INDEX IF NOT EXISTS idx_agent_state_key
    ON main.agent_state USING btree
    (state_key COLLATE pg_catalog."default" ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;