-- Table: main.commit

-- DROP TABLE IF EXISTS main.commit;

CREATE TABLE IF NOT EXISTS main.commit
(
    commit_id bigint NOT NULL DEFAULT nextval('main.commit_commit_id_seq'::regclass),
    project_id bigint,
    task_id bigint,
    git_repo_url text COLLATE pg_catalog."default",
    branch_name character varying(255) COLLATE pg_catalog."default",
    commit_hash character varying(255) COLLATE pg_catalog."default",
    author character varying(255) COLLATE pg_catalog."default",
    commit_message text COLLATE pg_catalog."default",
    commit_metadata jsonb,
    commit_status character varying(50) COLLATE pg_catalog."default",
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT commit_pkey PRIMARY KEY (commit_id)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS main.commit
    OWNER to postgres;
-- Index: idx_commit_hash

-- DROP INDEX IF EXISTS main.idx_commit_hash;

CREATE INDEX IF NOT EXISTS idx_commit_hash
    ON main.commit USING btree
    (commit_hash COLLATE pg_catalog."default" ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;
-- Index: idx_commit_project

-- DROP INDEX IF EXISTS main.idx_commit_project;

CREATE INDEX IF NOT EXISTS idx_commit_project
    ON main.commit USING btree
    (project_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;
-- Index: idx_commit_task

-- DROP INDEX IF EXISTS main.idx_commit_task;

CREATE INDEX IF NOT EXISTS idx_commit_task
    ON main.commit USING btree
    (task_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;