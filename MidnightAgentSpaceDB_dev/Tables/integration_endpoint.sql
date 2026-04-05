-- Table: main.integration_endpoint

-- DROP TABLE IF EXISTS main.integration_endpoint;

CREATE TABLE IF NOT EXISTS main.integration_endpoint
(
    endpoint_id bigint NOT NULL DEFAULT nextval('main.integration_endpoint_endpoint_id_seq'::regclass),
    integration_id bigint,
    endpoint_name character varying(255) COLLATE pg_catalog."default",
    endpoint_type character varying(100) COLLATE pg_catalog."default",
    method character varying(10) COLLATE pg_catalog."default",
    path character varying(1000) COLLATE pg_catalog."default",
    config_schema jsonb,
    created_by character varying(200) COLLATE pg_catalog."default",
    updated_by character varying(200) COLLATE pg_catalog."default",
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT integration_endpoint_pkey PRIMARY KEY (endpoint_id)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS main.integration_endpoint
    OWNER to postgres;
-- Index: idx_integration_endpoint_integration

-- DROP INDEX IF EXISTS main.idx_integration_endpoint_integration;

CREATE INDEX IF NOT EXISTS idx_integration_endpoint_integration
    ON main.integration_endpoint USING btree
    (integration_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;
-- Index: idx_integration_endpoint_name

-- DROP INDEX IF EXISTS main.idx_integration_endpoint_name;

CREATE INDEX IF NOT EXISTS idx_integration_endpoint_name
    ON main.integration_endpoint USING btree
    (endpoint_name COLLATE pg_catalog."default" ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;