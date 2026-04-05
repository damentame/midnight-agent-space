-- Table: main.integration_credentials

-- DROP TABLE IF EXISTS main.integration_credentials;

CREATE TABLE IF NOT EXISTS main.integration_credentials
(
    credential_id bigint NOT NULL DEFAULT nextval('main.integration_credentials_credential_id_seq'::regclass),
    integration_id bigint,
    name character varying(255) COLLATE pg_catalog."default",
    credential_data jsonb,
    created_by character varying(200) COLLATE pg_catalog."default",
    updated_by character varying(200) COLLATE pg_catalog."default",
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT integration_credentials_pkey PRIMARY KEY (credential_id)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS main.integration_credentials
    OWNER to postgres;
-- Index: idx_integration_credentials_integration

-- DROP INDEX IF EXISTS main.idx_integration_credentials_integration;

CREATE INDEX IF NOT EXISTS idx_integration_credentials_integration
    ON main.integration_credentials USING btree
    (integration_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;
-- Index: idx_integration_credentials_name

-- DROP INDEX IF EXISTS main.idx_integration_credentials_name;

CREATE INDEX IF NOT EXISTS idx_integration_credentials_name
    ON main.integration_credentials USING btree
    (name COLLATE pg_catalog."default" ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;