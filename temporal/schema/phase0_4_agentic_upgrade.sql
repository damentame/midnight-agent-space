-- ============================================================
-- TEMPORAL COMPANION SCHEMA - MAJOR UPGRADE (PHASE 0-4)
-- Mirrors dashboard additive entities for agentic runs.
-- ============================================================

CREATE SCHEMA IF NOT EXISTS main;

ALTER TABLE IF EXISTS main.project
    ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS repository_url TEXT,
    ADD COLUMN IF NOT EXISTS default_branch VARCHAR(255),
    ADD COLUMN IF NOT EXISTS runtime_preferences JSONB DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS main.document_version (
    document_version_id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL,
    document_id BIGINT NOT NULL,
    version_number INTEGER NOT NULL,
    version_label VARCHAR(255),
    source VARCHAR(100),
    content_hash VARCHAR(128),
    change_summary TEXT,
    raw_text_content TEXT,
    structured_json JSONB,
    created_by VARCHAR(200),
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_document_version_unique
    ON main.document_version (project_id, document_id, version_number);

CREATE TABLE IF NOT EXISTS main.agent_run (
    agent_run_id BIGSERIAL PRIMARY KEY,
    project_id BIGINT,
    workflow_run_id BIGINT,
    run_kind VARCHAR(100) DEFAULT 'quick_run',
    runtime_provider VARCHAR(100) DEFAULT 'codex-cli',
    status VARCHAR(50) DEFAULT 'PENDING',
    request_payload JSONB,
    context_pack JSONB,
    command_preview TEXT,
    result_payload JSONB,
    started_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP WITHOUT TIME ZONE,
    created_by VARCHAR(200),
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS main.agent_task (
    agent_task_id BIGSERIAL PRIMARY KEY,
    agent_run_id BIGINT NOT NULL,
    project_id BIGINT,
    task_name VARCHAR(255),
    task_kind VARCHAR(100),
    status VARCHAR(50) DEFAULT 'PENDING',
    input_payload JSONB,
    output_payload JSONB,
    started_at TIMESTAMP WITHOUT TIME ZONE,
    finished_at TIMESTAMP WITHOUT TIME ZONE,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS main.agent_event (
    agent_event_id BIGSERIAL PRIMARY KEY,
    agent_run_id BIGINT,
    agent_task_id BIGINT,
    project_id BIGINT,
    event_type VARCHAR(150),
    event_order BIGINT,
    event_payload JSONB,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS main.agent_artifact (
    agent_artifact_id BIGSERIAL PRIMARY KEY,
    agent_run_id BIGINT,
    agent_task_id BIGINT,
    project_id BIGINT,
    artifact_type VARCHAR(100),
    artifact_name VARCHAR(255),
    artifact_path TEXT,
    content_type VARCHAR(150),
    size_bytes BIGINT,
    metadata JSONB,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS main.git_change (
    git_change_id BIGSERIAL PRIMARY KEY,
    project_id BIGINT,
    agent_run_id BIGINT,
    agent_task_id BIGINT,
    repository_url TEXT,
    worktree_path TEXT,
    branch_name VARCHAR(255),
    base_branch VARCHAR(255),
    file_path TEXT,
    change_type VARCHAR(50),
    diff_excerpt TEXT,
    commit_hash VARCHAR(255),
    metadata JSONB,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS main.change_history (
    change_history_id BIGSERIAL PRIMARY KEY,
    project_id BIGINT,
    entity_type VARCHAR(100),
    entity_id BIGINT,
    source VARCHAR(100),
    change_type VARCHAR(100),
    title VARCHAR(255),
    summary TEXT,
    payload JSONB,
    created_by VARCHAR(200),
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
