-- Table: main.task_dependency

-- DROP TABLE IF EXISTS main.task_dependency;

CREATE TABLE IF NOT EXISTS main.task_dependency
(
    task_dependency_id bigint NOT NULL DEFAULT nextval('main.task_dependency_task_dependency_id_seq'::regclass),
    task_id bigint,
    depends_on_task_id bigint,
    created_by character varying(200) COLLATE pg_catalog."default",
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT task_dependency_pkey PRIMARY KEY (task_dependency_id)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS main.task_dependency
    OWNER to postgres;
-- Index: idx_task_dependency_depends

-- DROP INDEX IF EXISTS main.idx_task_dependency_depends;

CREATE INDEX IF NOT EXISTS idx_task_dependency_depends
    ON main.task_dependency USING btree
    (depends_on_task_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;
-- Index: idx_task_dependency_task

-- DROP INDEX IF EXISTS main.idx_task_dependency_task;

CREATE INDEX IF NOT EXISTS idx_task_dependency_task
    ON main.task_dependency USING btree
    (task_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;