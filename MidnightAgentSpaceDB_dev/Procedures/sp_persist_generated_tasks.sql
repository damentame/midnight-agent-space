-- PROCEDURE: main.sp_persist_generated_tasks
--
-- Normalizes task-generation JSON from Cursor into main.task and main.task_dependency
-- and emits a TASKS_GENERATED_FROM_CURSOR event for traceability.
--
-- The expected JSON shape for p_tasks_json is:
-- {
--   "tasks": [
--     {
--       "task_name": "Implement authentication middleware",
--       "task_type": "implementation",
--       "description": "...",
--       "parameters": { ... },
--       "status": "PENDING",
--       "priority": 1,
--       "task_notes": "...",
--       "task_data": {
--         "requirement_snippets": [...],
--         "requirement_type": "...",
--         "constraints": [...],
--         "success_criteria": [...],
--         "project_id": 123,
--         "document_ids": [...],
--         "chunk_ids": [...],
--         "dependencies": ["Other task name", ...]
--       }
--     }
--   ]
-- }
--
-- Dependencies can be provided either as a top-level "dependencies" array
-- or as task_data.dependencies.
--
-- Idempotency / replay safety:
-- - Optional p_batch_id can be supplied by callers. If provided, the procedure
--   checks main.event_log for an existing TASKS_GENERATED_FROM_CURSOR event
--   with the same project_id and batch_id and becomes a no-op if found.
-- - If p_batch_id is NULL, a unique batch_id is generated and recorded in
--   both task.task_data and the event_log payload, so repeated calls are
--   safely distinguishable.
--
-- DROP PROCEDURE IF EXISTS main.sp_persist_generated_tasks(bigint, bigint, bigint, bigint, jsonb, text, text);

CREATE OR REPLACE PROCEDURE main.sp_persist_generated_tasks(
    IN p_project_id          bigint,
    IN p_document_id         bigint,
    IN p_agent_id            bigint,
    IN p_agent_instance_id   bigint,
    IN p_tasks_json          jsonb,
    IN p_batch_id            text DEFAULT NULL,
    IN p_created_by          text DEFAULT 'system',
    IN p_workflow_run_id     bigint DEFAULT NULL
)
LANGUAGE 'plpgsql'
AS $BODY$
DECLARE
    v_tasks           jsonb;
    v_task            jsonb;
    v_idx             integer;
    v_task_id         bigint;
    v_task_name       text;
    v_task_type       text;
    v_description     text;
    v_parameters      jsonb;
    v_status          text;
    v_priority        integer;
    v_task_notes      text;
    v_task_data       jsonb;
    v_dependencies    jsonb;
    v_dep_name        text;
    v_dep_task_id     bigint;
    v_name_to_id      jsonb := '{}'::jsonb;
    v_existing_count  integer := 0;
    v_batch_id        text;
BEGIN
    -- Validate input JSON structure
    IF p_tasks_json IS NULL OR NOT (p_tasks_json ? 'tasks') THEN
        RAISE EXCEPTION 'p_tasks_json must contain a "tasks" array';
    END IF;

    v_tasks := p_tasks_json->'tasks';

    IF jsonb_typeof(v_tasks) <> 'array' THEN
        RAISE EXCEPTION '"tasks" must be a JSON array';
    END IF;

    -- Resolve / generate batch id
    IF p_batch_id IS NOT NULL THEN
        v_batch_id := p_batch_id;

        -- Check for existing batch to ensure idempotency
        SELECT COUNT(1)
        INTO v_existing_count
        FROM main.event_log
        WHERE entity_type = 'PROJECT'
          AND entity_id = p_project_id
          AND project_id = p_project_id
          AND event_type = 'TASKS_GENERATED_FROM_CURSOR'
          AND payload ->> 'batch_id' = v_batch_id;

        IF v_existing_count > 0 THEN
            RAISE NOTICE 'Tasks for project_id=% with batch_id=% already persisted, skipping', p_project_id, v_batch_id;
            RETURN;
        END IF;
    ELSE
        -- Generate a reasonably unique batch identifier
        v_batch_id := concat(
            'batch_',
            coalesce(p_project_id::text, 'no_project'), '_',
            coalesce(p_document_id::text, 'no_doc'), '_',
            floor(extract(epoch FROM clock_timestamp()))::bigint
        );
    END IF;

    -- First pass: insert tasks and build name -> id mapping
    FOR v_idx IN 0 .. COALESCE(jsonb_array_length(v_tasks), 0) - 1 LOOP
        v_task := v_tasks -> v_idx;

        v_task_name   := NULLIF(trim(v_task->>'task_name'), '');
        IF v_task_name IS NULL THEN
            v_task_name := format('Task %s', v_idx + 1);
        END IF;

        -- Skip duplicate names beyond the first occurrence to avoid ambiguous dependencies
        IF v_name_to_id ? v_task_name THEN
            RAISE NOTICE 'Duplicate task_name "%", skipping additional occurrence (index=%)', v_task_name, v_idx;
            CONTINUE;
        END IF;

        v_task_type   := NULLIF(trim(v_task->>'task_type'), '');
        v_description := v_task->>'description';
        v_parameters  := COALESCE(v_task->'parameters', '{}'::jsonb);
        v_status      := COALESCE(NULLIF(trim(v_task->>'status'), ''), 'PENDING');

        BEGIN
            v_priority := (v_task->>'priority')::integer;
        EXCEPTION WHEN others THEN
            v_priority := 3;
        END;

        v_task_notes  := v_task->>'task_notes';
        v_task_data   := COALESCE(v_task->'task_data', '{}'::jsonb);

        -- Insert task row
        INSERT INTO main.task (
            project_id,
            agent_id,
            document_id,
            task_name,
            task_type,
            description,
            parameters,
            status,
            priority,
            task_notes,
            task_data,
            created_by,
            updated_by,
            created_at,
            updated_at
        )
        VALUES (
            p_project_id,
            p_agent_id,
            p_document_id,
            v_task_name,
            v_task_type,
            v_description,
            v_parameters,
            v_status,
            v_priority,
            v_task_notes,
            -- Enrich task_data with batch + provenance metadata and workflow_run_id
            COALESCE(v_task_data, '{}'::jsonb)
            || jsonb_build_object(
                'batch_id', v_batch_id,
                'source', 'sp_persist_generated_tasks',
                'agent_instance_id', p_agent_instance_id,
                'original_task_index', v_idx
            )
            || CASE
                WHEN p_workflow_run_id IS NOT NULL
                  THEN jsonb_build_object('workflow_run_id', p_workflow_run_id)
                ELSE '{}'::jsonb
               END,
            p_created_by,
            p_created_by,
            now(),
            now()
        )
        RETURNING task_id INTO v_task_id;

        -- Record mapping of task_name -> task_id
        v_name_to_id := v_name_to_id || jsonb_build_object(v_task_name, v_task_id);
    END LOOP;

    -- Second pass: insert dependencies using the name -> id mapping
    FOR v_idx IN 0 .. COALESCE(jsonb_array_length(v_tasks), 0) - 1 LOOP
        v_task := v_tasks -> v_idx;

        v_task_name := NULLIF(trim(v_task->>'task_name'), '');
        IF v_task_name IS NULL THEN
            v_task_name := format('Task %s', v_idx + 1);
        END IF;

        -- Only proceed if this task was actually inserted
        IF NOT (v_name_to_id ? v_task_name) THEN
            CONTINUE;
        END IF;

        v_task_id := (v_name_to_id->>v_task_name)::bigint;

        -- Prefer top-level "dependencies"; fall back to task_data.dependencies
        v_dependencies := COALESCE(
            v_task->'dependencies',
            (v_task->'task_data')->'dependencies'
        );

        IF v_dependencies IS NULL OR jsonb_typeof(v_dependencies) <> 'array' THEN
            CONTINUE;
        END IF;

        FOR v_dep_name IN
            SELECT jsonb_array_elements_text(v_dependencies)
        LOOP
            v_dep_name := NULLIF(trim(v_dep_name), '');
            IF v_dep_name IS NULL THEN
                CONTINUE;
            END IF;

            IF NOT (v_name_to_id ? v_dep_name) THEN
                RAISE NOTICE 'Dependency "%" for task "%" not found in batch, skipping', v_dep_name, v_task_name;
                CONTINUE;
            END IF;

            v_dep_task_id := (v_name_to_id->>v_dep_name)::bigint;

            INSERT INTO main.task_dependency (
                task_id,
                depends_on_task_id,
                created_by
            )
            VALUES (
                v_task_id,
                v_dep_task_id,
                p_created_by
            );
        END LOOP;
    END LOOP;

    -- Emit event_log entry with full payload + mapping
    INSERT INTO main.event_log (
        entity_type,
        entity_id,
        project_id,
        event_type,
        payload,
        created_by
    )
    VALUES (
        'PROJECT',
        p_project_id,
        p_project_id,
        'TASKS_GENERATED_FROM_CURSOR',
        jsonb_build_object(
            'project_id', p_project_id,
            'document_id', p_document_id,
            'agent_id', p_agent_id,
            'agent_instance_id', p_agent_instance_id,
            'batch_id', v_batch_id,
            'tasks_json', p_tasks_json,
            'task_name_to_id', v_name_to_id
        ),
        p_created_by
    );
END;
$BODY$;

ALTER PROCEDURE main.sp_persist_generated_tasks(
    bigint,
    bigint,
    bigint,
    bigint,
    jsonb,
    text,
    text
)
    OWNER TO postgres;

