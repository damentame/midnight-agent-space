-- ============================================================
-- MIDNIGHT AGENT SPACE - PHASE 5-10 DEMO DATA SEED
-- Additive inserts only.
-- ============================================================

DO $$
DECLARE
    v_project_id BIGINT;
    v_document_id BIGINT;
    v_run_id BIGINT;
BEGIN
    INSERT INTO main.project (
        project_name,
        project_type,
        description,
        status,
        created_by
    )
    SELECT
        'Phase 5-10 Demo Project',
        'Demo',
        'Seeded data for project-scoped runs, documents, and review UI.',
        'ACTIVE',
        'seed-script'
    WHERE NOT EXISTS (
        SELECT 1
        FROM main.project
        WHERE project_name = 'Phase 5-10 Demo Project'
    );

    SELECT project_id
    INTO v_project_id
    FROM main.project
    WHERE project_name = 'Phase 5-10 Demo Project'
    ORDER BY project_id DESC
    LIMIT 1;

    IF v_project_id IS NULL THEN
        RETURN;
    END IF;

    UPDATE main.project
    SET
        repository_url = COALESCE(repository_url, 'https://example.com/midnight-agent-space.git'),
        default_branch = COALESCE(default_branch, 'main'),
        runtime_preferences = COALESCE(runtime_preferences, '{}'::jsonb) || '{"provider":"codex-cli"}'::jsonb,
        metadata = COALESCE(metadata, '{}'::jsonb) || '{"demo":true,"phase":"5-10"}'::jsonb
    WHERE project_id = v_project_id;

    INSERT INTO main.project_document (
        project_id,
        document_name,
        document_type,
        raw_text_content,
        file_extension,
        file_mime_type,
        file_size_bytes,
        version_number,
        is_active_version,
        serialization_status,
        created_by
    )
    SELECT
        v_project_id,
        'README_demo.md',
        'notes',
        '# Demo document' || E'\n' || 'This document is seeded for versioning demos.',
        '.md',
        'text/markdown',
        72,
        1,
        TRUE,
        'READY',
        'seed-script'
    WHERE NOT EXISTS (
        SELECT 1
        FROM main.project_document
        WHERE project_id = v_project_id
          AND document_name = 'README_demo.md'
    );

    SELECT document_id
    INTO v_document_id
    FROM main.project_document
    WHERE project_id = v_project_id
      AND document_name = 'README_demo.md'
    ORDER BY document_id DESC
    LIMIT 1;

    IF v_document_id IS NOT NULL THEN
        INSERT INTO main.document_version (
            project_id,
            document_id,
            version_number,
            version_label,
            source,
            change_summary,
            raw_text_content,
            created_by
        )
        SELECT
            v_project_id,
            v_document_id,
            1,
            'seed-v1',
            'seed',
            'Initial seeded version',
            '# Demo document' || E'\n' || 'Version 1',
            'seed-script'
        WHERE NOT EXISTS (
            SELECT 1
            FROM main.document_version
            WHERE project_id = v_project_id
              AND document_id = v_document_id
              AND version_number = 1
        );
    END IF;

    INSERT INTO main.agent_run (
        project_id,
        run_kind,
        runtime_provider,
        status,
        request_payload,
        context_pack,
        command_preview,
        result_payload,
        created_by
    )
    SELECT
        v_project_id,
        'quick_run',
        'codex-cli',
        'COMPLETED',
        '{"template_name":"quick_run_system_prompt","user_prompt":"Create a demo patch"}'::jsonb,
        '{"demo":true}'::jsonb,
        'codex exec --json --ask-for-approval on-failure --sandbox workspace-write --cd /tmp/demo',
        '{"execution":{"ok":true,"exit_code":0},"review":{"ok":true}}'::jsonb,
        'seed-script'
    WHERE NOT EXISTS (
        SELECT 1
        FROM main.agent_run
        WHERE project_id = v_project_id
          AND created_by = 'seed-script'
    );

    SELECT agent_run_id
    INTO v_run_id
    FROM main.agent_run
    WHERE project_id = v_project_id
      AND created_by = 'seed-script'
    ORDER BY agent_run_id DESC
    LIMIT 1;

    IF v_run_id IS NOT NULL THEN
        INSERT INTO main.agent_event (
            agent_run_id,
            project_id,
            event_type,
            event_order,
            event_payload
        )
        SELECT
            v_run_id,
            v_project_id,
            'RUN_COMPLETED',
            1,
            '{"message":"Seeded completion event"}'::jsonb
        WHERE NOT EXISTS (
            SELECT 1
            FROM main.agent_event
            WHERE agent_run_id = v_run_id
              AND event_type = 'RUN_COMPLETED'
        );

        INSERT INTO main.agent_artifact (
            agent_run_id,
            project_id,
            artifact_type,
            artifact_name,
            artifact_path,
            content_type,
            metadata
        )
        SELECT
            v_run_id,
            v_project_id,
            'log',
            'stdout.log',
            '/tmp/seed/stdout.log',
            'text/plain',
            '{"seed":true}'::jsonb
        WHERE NOT EXISTS (
            SELECT 1
            FROM main.agent_artifact
            WHERE agent_run_id = v_run_id
              AND artifact_name = 'stdout.log'
        );

        INSERT INTO main.git_change (
            project_id,
            agent_run_id,
            branch_name,
            base_branch,
            file_path,
            change_type,
            diff_excerpt,
            metadata
        )
        SELECT
            v_project_id,
            v_run_id,
            'mas/quick-run/seed',
            'main',
            'README_demo.md',
            'M',
            'Seeded diff excerpt',
            '{"seed":true}'::jsonb
        WHERE NOT EXISTS (
            SELECT 1
            FROM main.git_change
            WHERE agent_run_id = v_run_id
              AND file_path = 'README_demo.md'
        );
    END IF;
END $$;
