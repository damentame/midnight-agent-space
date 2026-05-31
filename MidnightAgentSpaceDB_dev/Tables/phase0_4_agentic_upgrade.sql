-- ============================================================
-- MIDNIGHT AGENT SPACE - MAJOR UPGRADE (PHASE 0-4)
-- Additive migration only (no drops, no destructive changes).
-- ============================================================

CREATE SCHEMA IF NOT EXISTS main;

/* ============================================================
   1) PROJECT METADATA (ADDITIVE COLUMNS)
   ============================================================ */
ALTER TABLE IF EXISTS main.project
    ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS repository_url TEXT,
    ADD COLUMN IF NOT EXISTS default_branch VARCHAR(255),
    ADD COLUMN IF NOT EXISTS runtime_preferences JSONB DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_project_repository_url
    ON main.project (repository_url);

/* ============================================================
   2) DOCUMENT VERSIONING
   ============================================================ */
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
CREATE INDEX IF NOT EXISTS idx_document_version_project
    ON main.document_version (project_id);
CREATE INDEX IF NOT EXISTS idx_document_version_document
    ON main.document_version (document_id);

/* ============================================================
   3) AGENT RUNS / TASKS / EVENTS / ARTIFACTS
   ============================================================ */
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

CREATE INDEX IF NOT EXISTS idx_agent_run_project
    ON main.agent_run (project_id);
CREATE INDEX IF NOT EXISTS idx_agent_run_status
    ON main.agent_run (status);
CREATE INDEX IF NOT EXISTS idx_agent_run_runtime_provider
    ON main.agent_run (runtime_provider);
CREATE INDEX IF NOT EXISTS idx_agent_run_workflow_run
    ON main.agent_run (workflow_run_id);

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

CREATE INDEX IF NOT EXISTS idx_agent_task_run
    ON main.agent_task (agent_run_id);
CREATE INDEX IF NOT EXISTS idx_agent_task_project
    ON main.agent_task (project_id);
CREATE INDEX IF NOT EXISTS idx_agent_task_status
    ON main.agent_task (status);

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

CREATE INDEX IF NOT EXISTS idx_agent_event_run
    ON main.agent_event (agent_run_id);
CREATE INDEX IF NOT EXISTS idx_agent_event_task
    ON main.agent_event (agent_task_id);
CREATE INDEX IF NOT EXISTS idx_agent_event_project
    ON main.agent_event (project_id);
CREATE INDEX IF NOT EXISTS idx_agent_event_type
    ON main.agent_event (event_type);
CREATE INDEX IF NOT EXISTS idx_agent_event_order
    ON main.agent_event (agent_run_id, event_order);

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

CREATE INDEX IF NOT EXISTS idx_agent_artifact_run
    ON main.agent_artifact (agent_run_id);
CREATE INDEX IF NOT EXISTS idx_agent_artifact_task
    ON main.agent_artifact (agent_task_id);
CREATE INDEX IF NOT EXISTS idx_agent_artifact_project
    ON main.agent_artifact (project_id);
CREATE INDEX IF NOT EXISTS idx_agent_artifact_type
    ON main.agent_artifact (artifact_type);

/* ============================================================
   4) GIT CHANGE TRACKING + HUMAN-READABLE CHANGE HISTORY
   ============================================================ */
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

CREATE INDEX IF NOT EXISTS idx_git_change_project
    ON main.git_change (project_id);
CREATE INDEX IF NOT EXISTS idx_git_change_run
    ON main.git_change (agent_run_id);
CREATE INDEX IF NOT EXISTS idx_git_change_task
    ON main.git_change (agent_task_id);
CREATE INDEX IF NOT EXISTS idx_git_change_branch
    ON main.git_change (branch_name);
CREATE INDEX IF NOT EXISTS idx_git_change_file
    ON main.git_change (file_path);

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

CREATE INDEX IF NOT EXISTS idx_change_history_project
    ON main.change_history (project_id);
CREATE INDEX IF NOT EXISTS idx_change_history_entity
    ON main.change_history (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_change_history_type
    ON main.change_history (change_type);
CREATE INDEX IF NOT EXISTS idx_change_history_created_at
    ON main.change_history (created_at);
