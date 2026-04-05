-- Table: main.agent_role

-- DROP TABLE IF EXISTS main.agent_role;

CREATE TABLE IF NOT EXISTS main.agent_role
(
    agent_role_id bigint NOT NULL DEFAULT nextval('main.agent_role_agent_role_id_seq'::regclass),
    role_name character varying(100) COLLATE pg_catalog."default",
    role_description text COLLATE pg_catalog."default",
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT agent_role_pkey PRIMARY KEY (agent_role_id)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS main.agent_role
    OWNER to postgres;
-- Index: idx_agent_role_name

-- DROP INDEX IF EXISTS main.idx_agent_role_name;

CREATE INDEX IF NOT EXISTS idx_agent_role_name
    ON main.agent_role USING btree
    (role_name COLLATE pg_catalog."default" ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;