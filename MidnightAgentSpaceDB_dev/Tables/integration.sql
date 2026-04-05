-- Table: main.integration

-- DROP TABLE IF EXISTS main.integration;

CREATE TABLE IF NOT EXISTS main.integration
(
    integration_id bigint NOT NULL DEFAULT nextval('main.integration_integration_id_seq'::regclass),
    name character varying(255) COLLATE pg_catalog."default",
    type character varying(100) COLLATE pg_catalog."default",
    description text COLLATE pg_catalog."default",
    base_url character varying(1000) COLLATE pg_catalog."default",
    is_active boolean,
    config jsonb,
    created_by character varying(200) COLLATE pg_catalog."default",
    updated_by character varying(200) COLLATE pg_catalog."default",
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT integration_pkey PRIMARY KEY (integration_id)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS main.integration
    OWNER to postgres;
-- Index: idx_integration_name

-- DROP INDEX IF EXISTS main.idx_integration_name;

CREATE INDEX IF NOT EXISTS idx_integration_name
    ON main.integration USING btree
    (name COLLATE pg_catalog."default" ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;
-- Index: idx_integration_type

-- DROP INDEX IF EXISTS main.idx_integration_type;

CREATE INDEX IF NOT EXISTS idx_integration_type
    ON main.integration USING btree
    (type COLLATE pg_catalog."default" ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;