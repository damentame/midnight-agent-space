-- ============================================================
-- FULL AGENTIC DEVELOPMENT PLATFORM SCHEMA (NO FKs / NO CONSTRAINTS)
-- ============================================================

/* ============================================================
   1. PROJECT
   ============================================================ */
CREATE TABLE project (
    project_id        BIGSERIAL,
    project_name      VARCHAR(255),
    project_type      VARCHAR(100),
    description       TEXT,
    status            VARCHAR(50),
    created_by        VARCHAR(200),
    updated_by        VARCHAR(200),
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_project_name ON project(project_name);
CREATE INDEX idx_project_type ON project(project_type);
CREATE INDEX idx_project_status ON project(status);


/* ============================================================
   2. PROJECT DOCUMENT
   ============================================================ */
CREATE TABLE project_document (
    document_id          BIGSERIAL,
    project_id           BIGINT,
    parent_document_id   BIGINT,

    document_name        VARCHAR(255),
    document_type        VARCHAR(100),

    raw_text_content     TEXT,
    structured_json      JSONB,

    file_extension       VARCHAR(20),
    file_mime_type       VARCHAR(150),
    file_size_bytes      BIGINT,
    file_content         BYTEA,

    version_number       INT,
    is_active_version    BOOLEAN,

    created_by           VARCHAR(100),
    updated_by           VARCHAR(100),

    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_project_document_project ON project_document(project_id);
CREATE INDEX idx_project_document_parent ON project_document(parent_document_id);
CREATE INDEX idx_project_document_type ON project_document(document_type);


/* ============================================================
   3. AGENT ROLE
   ============================================================ */
CREATE TABLE agent_role (
    agent_role_id     BIGSERIAL,
    role_name         VARCHAR(100),
    role_description  TEXT,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_agent_role_name ON agent_role(role_name);


/* ============================================================
   4. AGENT
   ============================================================ */
CREATE TABLE agent (
    agent_id        BIGSERIAL,
    agent_name      VARCHAR(255),
    agent_type      VARCHAR(100),
    agent_role_id   BIGINT,
    api_key         VARCHAR(1000),
    endpoint_url    VARCHAR(1000),
    agent_status    VARCHAR(50),
    agent_last_seen TIMESTAMP,
    capabilities    JSONB,
    config          JSONB,
    created_by      VARCHAR(200),
    updated_by      VARCHAR(200),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_agent_name ON agent(agent_name);
CREATE INDEX idx_agent_type ON agent(agent_type);
CREATE INDEX idx_agent_status ON agent(agent_status);


/* ============================================================
   5. AGENT STATE (PERSISTENT MEMORY)
   ============================================================ */
CREATE TABLE agent_state (
    state_id        BIGSERIAL,
    agent_id        BIGINT,
    state_key       VARCHAR(200),
    state_value     JSONB,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_agent_state_agent ON agent_state(agent_id);
CREATE INDEX idx_agent_state_key ON agent_state(state_key);


/* ============================================================
   6. TASK
   ============================================================ */

CREATE TABLE task (
    task_id          BIGSERIAL,
    project_id       BIGINT,
    agent_id         BIGINT,
	document_id      BIGINT,
    task_name        VARCHAR(255),
    task_type        VARCHAR(100),
    description      TEXT,
    parameters       JSONB,
    status           VARCHAR(50),
    priority         INT,
    task_notes       TEXT,
    task_data        JSONB,
    created_by       VARCHAR(200),
    updated_by       VARCHAR(200),
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_task_project ON task(project_id);
CREATE INDEX idx_task_agent ON task(agent_id);
CREATE INDEX idx_task_status ON task(status);
CREATE INDEX idx_task_priority ON task(priority);


/* ============================================================
   7. TASK DEPENDENCY
   ============================================================ */
CREATE TABLE task_dependency (
    task_dependency_id    BIGSERIAL,
    task_id               BIGINT,
    depends_on_task_id    BIGINT,
    created_by            VARCHAR(200),
    created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_task_dependency_task ON task_dependency(task_id);
CREATE INDEX idx_task_dependency_depends ON task_dependency(depends_on_task_id);


/* ============================================================
   8. TASK EXECUTION
   ============================================================ */
CREATE TABLE task_execution (
    task_execution_id     BIGSERIAL,
    task_id               BIGINT,
    agent_id              BIGINT,
    task_execution_status VARCHAR(50),
    task_execution_notes  TEXT,
    task_execution_result JSONB,
    logs                  TEXT,
    started_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at           TIMESTAMP
);
CREATE INDEX idx_task_execution_task ON task_execution(task_id);
CREATE INDEX idx_task_execution_agent ON task_execution(agent_id);
CREATE INDEX idx_task_execution_status ON task_execution(task_execution_status);


/* ============================================================
   9. COMMIT (GIT INTEGRATION)
   ============================================================ */
CREATE TABLE commit (
    commit_id        BIGSERIAL,
    project_id       BIGINT,
    task_id          BIGINT,
    git_repo_url     TEXT,
    branch_name      VARCHAR(255),
    commit_hash      VARCHAR(255),
    author           VARCHAR(255),
    commit_message   TEXT,
    commit_metadata  JSONB,
    commit_status    VARCHAR(50),
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_commit_project ON commit(project_id);
CREATE INDEX idx_commit_task ON commit(task_id);
CREATE INDEX idx_commit_hash ON commit(commit_hash);


/* ============================================================
   10. INTEGRATION
   ============================================================ */
CREATE TABLE integration (
    integration_id   BIGSERIAL,
    name             VARCHAR(255),
    type             VARCHAR(100),
    description      TEXT,
    base_url         VARCHAR(1000),
    is_active        BOOLEAN,
    config           JSONB,
    created_by       VARCHAR(200),
    updated_by       VARCHAR(200),
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_integration_name ON integration(name);
CREATE INDEX idx_integration_type ON integration(type);


/* ============================================================
   11. INTEGRATION CREDENTIALS
   ============================================================ */
CREATE TABLE integration_credentials (
    credential_id     BIGSERIAL,
    integration_id    BIGINT,
    name              VARCHAR(255),
    credential_data   JSONB,
    created_by        VARCHAR(200),
    updated_by        VARCHAR(200),
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_integration_credentials_integration ON integration_credentials(integration_id);
CREATE INDEX idx_integration_credentials_name ON integration_credentials(name);


/* ============================================================
   12. INTEGRATION ENDPOINT
   ============================================================ */
CREATE TABLE integration_endpoint (
    endpoint_id      BIGSERIAL,
    integration_id   BIGINT,
    endpoint_name    VARCHAR(255),
    endpoint_type    VARCHAR(100),
    method           VARCHAR(10),
    path             VARCHAR(1000),
    config_schema    JSONB,
    created_by       VARCHAR(200),
    updated_by       VARCHAR(200),
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_integration_endpoint_integration ON integration_endpoint(integration_id);
CREATE INDEX idx_integration_endpoint_name ON integration_endpoint(endpoint_name);


/* ============================================================
   13. AGENT-INTEGRATION ACCESS (RBAC)
   ============================================================ */
CREATE TABLE agent_integration_access (
    agent_id         BIGINT,
    integration_id   BIGINT,
    access_level     VARCHAR(50),
    granted_by       VARCHAR(200),
    granted_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_agent_integration_access_agent ON agent_integration_access(agent_id);
CREATE INDEX idx_agent_integration_access_integration ON agent_integration_access(integration_id);


/* ============================================================
   14. WORKFLOW RUN
   ============================================================ */
CREATE TABLE workflow_run (
    workflow_run_id  BIGSERIAL,
    workflow_name    VARCHAR(255),
    status           VARCHAR(50),
    input_data       JSONB,
    result_data      JSONB,
    started_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at      TIMESTAMP,
    created_by       VARCHAR(200),
    updated_by       VARCHAR(200),
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_workflow_run_name ON workflow_run(workflow_name);
CREATE INDEX idx_workflow_run_status ON workflow_run(status);


/* ============================================================
   15. EVENT LOG
   ============================================================ */
CREATE TABLE event_log (
    event_log_id     BIGSERIAL,
    entity_type      VARCHAR(100),
    entity_id        BIGINT,
    event_type       VARCHAR(100),
    payload          JSONB,
    created_by       VARCHAR(200),
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_event_log_entity ON event_log(entity_type, entity_id);
CREATE INDEX idx_event_log_event_type ON event_log(event_type);


-- ============================================================
-- OPTIONAL: Basic helper indexes you might later want for
-- quick lookups by created_at (commented out; enable if needed)
-- ============================================================

-- CREATE INDEX idx_project_created_at ON project(created_at);
-- CREATE INDEX idx_task_created_at ON task(created_at);
-- CREATE INDEX idx_commit_created_at ON commit(created_at);
