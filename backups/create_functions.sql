-- ============================================================
-- CREATE REQUIRED DATABASE FUNCTIONS FOR TEMPORAL WORKFLOW
-- ============================================================
-- These functions are required by the Temporal workflow activities
-- ============================================================

-- Ensure main schema exists
CREATE SCHEMA IF NOT EXISTS main;

-- ============================================================
-- 1. PROCEDURE: main.sp_spin_up_agent
-- ============================================================
-- Creates an agent instance and returns agent configuration
-- ============================================================

CREATE OR REPLACE PROCEDURE main.sp_spin_up_agent(
    OUT p_result jsonb,
    IN p_agent_id bigint DEFAULT 2,
    IN p_project_id bigint DEFAULT NULL
)
LANGUAGE 'plpgsql'
AS $BODY$
DECLARE
    v_agent RECORD;
    v_agent_instance_id bigint;
BEGIN
    -- Validate required project context
    IF p_project_id IS NULL THEN
        RAISE EXCEPTION 'p_project_id is required to spin up an agent instance';
    END IF;

    -- Fetch agent definition from database (main schema)
    SELECT *
    INTO v_agent
    FROM main.agent
    WHERE agent_id = p_agent_id
      AND (agent_status = 'ACTIVE' OR agent_status IS NULL)
    LIMIT 1;

    -- Check if agent was found
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Agent (agent_id=%) not found. Please ensure agent exists in main.agent table.', p_agent_id;
    END IF;

    -- Create agent_instance record if table exists
    -- Check if agent_instance table exists
    IF EXISTS (SELECT 1 FROM information_schema.tables 
               WHERE table_schema = 'main' AND table_name = 'agent_instance') THEN
        INSERT INTO main.agent_instance (
            agent_id,
            project_id,
            instance_status,
            spin_up_reason,
            instance_metadata,
            started_at,
            created_by,
            updated_by,
            created_at,
            updated_at
        )
        VALUES (
            p_agent_id,
            p_project_id,
            'ACTIVE',
            'sp_spin_up_agent',
            jsonb_build_object(
                'agent_name', COALESCE(v_agent.agent_name, 'Unknown'),
                'agent_type', COALESCE(v_agent.agent_type, 'Unknown'),
                'source', 'sp_spin_up_agent',
                'timestamp', now()
            ),
            now(),
            'system',
            'system',
            now(),
            now()
        )
        RETURNING agent_instance_id INTO v_agent_instance_id;
    ELSE
        -- If agent_instance table doesn't exist, generate a temporary ID
        v_agent_instance_id := p_agent_id * 1000 + p_project_id;
    END IF;

    -- Log event if event_log table exists
    IF EXISTS (SELECT 1 FROM information_schema.tables 
               WHERE table_schema = 'main' AND table_name = 'event_log') THEN
        INSERT INTO main.event_log (
            entity_type,
            entity_id,
            project_id,
            event_type,
            payload,
            created_by
        )
        VALUES (
            'AGENT_INSTANCE',
            v_agent_instance_id,
            p_project_id,
            'AGENT_INSTANCE_SPIN_UP',
            jsonb_build_object(
                'agent_id', p_agent_id,
                'agent_instance_id', v_agent_instance_id,
                'agent_name', COALESCE(v_agent.agent_name, 'Unknown'),
                'project_id', p_project_id,
                'timestamp', now()
            ),
            'system'
        );
    END IF;

    -- Build result JSONB with all data needed
    SELECT jsonb_build_object(
        'agent_id', v_agent.agent_id,
        'agent_instance_id', v_agent_instance_id,
        'agent_name', COALESCE(v_agent.agent_name, 'Unknown Agent'),
        'agent_type', COALESCE(v_agent.agent_type, 'Unknown'),
        'endpoint_url', v_agent.endpoint_url,
        'api_key', v_agent.api_key,
        'capabilities', COALESCE(v_agent.capabilities, '{}'::jsonb),
        'config', COALESCE(v_agent.config, '{}'::jsonb),
        'project_id', p_project_id,
        'spin_up_timestamp', now()
    )
    INTO p_result;
END;
$BODY$;

-- ============================================================
-- 2. FUNCTION: main.fn_spin_up_agent
-- ============================================================
-- Wrapper function that calls the procedure
-- ============================================================

CREATE OR REPLACE FUNCTION main.fn_spin_up_agent(
    p_agent_id bigint DEFAULT 2,
    p_project_id bigint DEFAULT NULL
)
RETURNS jsonb
LANGUAGE 'plpgsql'
AS $BODY$
DECLARE
    v_result jsonb;
BEGIN
    -- Call the procedure and capture the result
    CALL main.sp_spin_up_agent(v_result, p_agent_id, p_project_id);
    
    -- Return the result
    RETURN v_result;
END;
$BODY$;

-- ============================================================
-- 3. FUNCTION: main.fn_get_project_documents
-- ============================================================
-- Returns all active documents for a project
-- ============================================================

CREATE OR REPLACE FUNCTION main.fn_get_project_documents(
    p_project_id bigint
)
RETURNS jsonb
LANGUAGE 'plpgsql'
AS $BODY$
DECLARE
    v_documents jsonb;
BEGIN
    -- Fetch all active project documents for the project (main schema)
    SELECT COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'document_id', document_id,
                'project_id', project_id,
                'document_name', document_name,
                'document_type', document_type,
                'raw_text_content', raw_text_content,
                'structured_json', structured_json,
                'file_extension', file_extension,
                'file_mime_type', file_mime_type,
                'file_size_bytes', file_size_bytes,
                'file_content', file_content,
                'version_number', version_number,
                'is_active_version', is_active_version,
                'serialization_status', serialization_status,
                'serialized_payload', serialized_payload
            )
            ORDER BY document_id
        ),
        '[]'::jsonb
    )
    INTO v_documents
    FROM main.project_document
    WHERE project_id = p_project_id
      AND (is_active_version = TRUE OR is_active_version IS NULL);
    
    RETURN jsonb_build_object(
        'project_id', p_project_id,
        'documents', v_documents,
        'document_count', jsonb_array_length(v_documents)
    );
END;
$BODY$;

-- ============================================================
-- 4. PROCEDURE: main.sp_serialize_document
-- ============================================================
-- Updates document with serialized payload
-- ============================================================

CREATE OR REPLACE PROCEDURE main.sp_serialize_document(
    IN p_document_id bigint,
    IN p_serialized_payload jsonb,
    IN p_updated_by character varying DEFAULT 'system'
)
LANGUAGE 'plpgsql'
AS $BODY$
BEGIN
    -- Update the document with serialized payload (main schema)
    UPDATE main.project_document
    SET 
        serialized_payload = p_serialized_payload,
        serialization_status = 'COMPLETED',
        serialized_at = CURRENT_TIMESTAMP,
        updated_by = p_updated_by,
        updated_at = CURRENT_TIMESTAMP
    WHERE document_id = p_document_id;
    
    -- Check if document was found and updated
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Document (document_id=%) not found', p_document_id;
    END IF;
    
    -- Log the serialization event if event_log table exists
    IF EXISTS (SELECT 1 FROM information_schema.tables 
               WHERE table_schema = 'main' AND table_name = 'event_log') THEN
        INSERT INTO main.event_log (
            entity_type,
            entity_id,
            project_id,
            event_type,
            payload,
            created_by
        )
        SELECT 
            'project_document',
            p_document_id,
            project_id,
            'document_serialized',
            jsonb_build_object(
                'document_id', p_document_id,
                'document_name', document_name,
                'serialization_status', 'COMPLETED',
                'timestamp', CURRENT_TIMESTAMP
            ),
            p_updated_by
        FROM main.project_document
        WHERE document_id = p_document_id;
    END IF;
END;
$BODY$;

-- ============================================================
-- 5. FUNCTION: main.fn_get_enhanced_rag_context
-- ============================================================
-- Enhanced RAG retrieval with document/project context
-- Optimized single query with all joins
-- ============================================================

CREATE OR REPLACE FUNCTION main.fn_get_enhanced_rag_context(
    p_query_embedding vector(384),
    p_project_id bigint,
    p_limit integer DEFAULT 10,
    p_similarity_threshold numeric DEFAULT 0.7,
    p_document_types text[] DEFAULT NULL
)
RETURNS jsonb
LANGUAGE 'plpgsql'
AS $BODY$
DECLARE
    v_results jsonb;
BEGIN
    -- Optimized single query with all joins
    -- Uses HNSW index for fast similarity search
    -- Returns enriched chunks with document/project context from metadata
    -- First order and limit in subquery, then aggregate to avoid GROUP BY issues
    SELECT COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'chunk_id', subq.chunk_id,
                'chunk_text', subq.chunk_text,
                'chunk_metadata', subq.chunk_metadata,
                'similarity_score', subq.similarity_score,
                
                -- Document context from metadata
                'document_name', subq.chunk_metadata->>'document_name',
                'document_type', subq.chunk_metadata->>'document_type',
                'document_version', (subq.chunk_metadata->>'document_version')::int,
                
                -- Project context from metadata
                'project_name', subq.chunk_metadata->>'project_name',
                'project_type', subq.chunk_metadata->>'project_type',
                
                -- Semantic metadata
                'requirement_type', subq.chunk_metadata->>'requirement_type',
                'has_constraints', (subq.chunk_metadata->>'has_constraints')::boolean,
                'has_success_criteria', (subq.chunk_metadata->>'has_success_criteria')::boolean,
                'priority_indicators', subq.chunk_metadata->>'priority_indicators',
                
                -- Additional metadata
                'chunk_index', subq.chunk_index,
                'document_id', subq.document_id,
                'project_id', subq.project_id
            )
            ORDER BY subq.similarity_score DESC
        ),
        '[]'::jsonb
    )
    INTO v_results
    FROM (
        SELECT 
            dc.chunk_id,
            dc.chunk_text,
            dc.chunk_metadata,
            1 - (de.embedding <=> p_query_embedding) AS similarity_score,
            dc.chunk_index,
            dc.document_id,
            dc.project_id
        FROM main.document_chunk dc
        INNER JOIN main.document_embedding de ON dc.chunk_id = de.chunk_id
        WHERE dc.project_id = p_project_id
          AND (1 - (de.embedding <=> p_query_embedding)) >= p_similarity_threshold
          AND (p_document_types IS NULL OR dc.chunk_metadata->>'document_type' = ANY(p_document_types))
        ORDER BY de.embedding <=> p_query_embedding
        LIMIT p_limit
    ) subq;
    
    RETURN jsonb_build_object(
        'results', v_results,
        'count', jsonb_array_length(v_results),
        'similarity_threshold', p_similarity_threshold,
        'project_id', p_project_id
    );
END;
$BODY$;

-- ============================================================
-- 6. PROCEDURE: main.sp_persist_generated_tasks
-- ============================================================
-- Normalizes generated tasks JSON into main.task and main.task_dependency
-- and emits TASKS_GENERATED_FROM_CURSOR events. Includes basic idempotency
-- via optional batch_id.
-- ============================================================

CREATE OR REPLACE PROCEDURE main.sp_persist_generated_tasks(
    IN p_project_id          bigint,
    IN p_document_id         bigint,
    IN p_agent_id            bigint,
    IN p_agent_instance_id   bigint,
    IN p_tasks_json          jsonb,
    IN p_batch_id            text DEFAULT NULL,
    IN p_created_by          text DEFAULT 'system'
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
    -- If task table does not exist (e.g., in minimal schemas), do nothing
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'main' AND table_name = 'task'
    ) THEN
        RAISE NOTICE 'main.task table not found; sp_persist_generated_tasks is a no-op in this schema';
        RETURN;
    END IF;

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

        -- Check for existing batch to ensure idempotency (if event_log exists)
        IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'main' AND table_name = 'event_log'
        ) THEN
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
            COALESCE(v_task_data, '{}'::jsonb) || jsonb_build_object(
                'batch_id', v_batch_id,
                'source', 'sp_persist_generated_tasks',
                'agent_instance_id', p_agent_instance_id,
                'original_task_index', v_idx
            ),
            p_created_by,
            p_created_by,
            now(),
            now()
        )
        RETURNING task_id INTO v_task_id;

        v_name_to_id := v_name_to_id || jsonb_build_object(v_task_name, v_task_id);
    END LOOP;

    -- Second pass: insert dependencies using the name -> id mapping (if table exists)
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'main' AND table_name = 'task_dependency'
    ) THEN
        FOR v_idx IN 0 .. COALESCE(jsonb_array_length(v_tasks), 0) - 1 LOOP
            v_task := v_tasks -> v_idx;

            v_task_name := NULLIF(trim(v_task->>'task_name'), '');
            IF v_task_name IS NULL THEN
                v_task_name := format('Task %s', v_idx + 1);
            END IF;

            IF NOT (v_name_to_id ? v_task_name) THEN
                CONTINUE;
            END IF;

            v_task_id := (v_name_to_id->>v_task_name)::bigint;

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
    END IF;

    -- Emit event_log entry if event_log table exists
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'main' AND table_name = 'event_log'
    ) THEN
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
    END IF;
END;
$BODY$;

-- ============================================================
-- 7. PROCEDURE: main.sp_ensure_agents_for_roles
-- ============================================================
-- Ensures main.agent rows exist for each role in p_roles_json and
-- emits AGENT_CREATED_FROM_TASKS events for any newly created agents.
-- ============================================================

CREATE OR REPLACE PROCEDURE main.sp_ensure_agents_for_roles(
    IN p_project_id bigint,
    IN p_roles_json jsonb,
    IN p_created_by text DEFAULT 'system'
)
LANGUAGE 'plpgsql'
AS $BODY$
DECLARE
    v_roles              jsonb;
    v_role               jsonb;
    v_idx                integer;
    v_role_name          text;
    v_agent_category     text;
    v_agent_role_name    text;
    v_agent_role_id      bigint;
    v_agent_name         text;
    v_existing_agent_id  bigint;
    v_new_agent_id       bigint;
    v_agent_type         bigint := 1; -- Use type "1" consistently with existing agents
    v_constraints        jsonb;
    v_responsibilities   jsonb;
    v_success_criteria   jsonb;
    v_escalation         jsonb;
    v_config             jsonb;
    v_capabilities       jsonb;
BEGIN
    -- If core tables do not exist, become a no-op
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'main' AND table_name = 'agent'
    ) THEN
        RAISE NOTICE 'main.agent table not found; sp_ensure_agents_for_roles is a no-op in this schema';
        RETURN;
    END IF;

    IF p_roles_json IS NULL OR NOT (p_roles_json ? 'roles') THEN
        RAISE EXCEPTION 'p_roles_json must contain a "roles" array';
    END IF;

    v_roles := p_roles_json->'roles';

    IF jsonb_typeof(v_roles) <> 'array' THEN
        RAISE EXCEPTION '"roles" must be a JSON array';
    END IF;

    FOR v_idx IN 0 .. COALESCE(jsonb_array_length(v_roles), 0) - 1 LOOP
        v_role := v_roles -> v_idx;

        v_role_name := NULLIF(trim(v_role->>'role_name'), '');
        IF v_role_name IS NULL THEN
            v_role_name := format('Role %s', v_idx + 1);
        END IF;

        v_agent_category := NULLIF(trim(v_role->>'agent_category'), '');

        -- Map agent_category to a base agent_role.role_name
        v_agent_role_name := CASE v_agent_category
            WHEN 'BusinessRequirementsAnalyst' THEN 'Business Requirements Analyst'
            WHEN 'ProjectManager'              THEN 'Project Manager'
            WHEN 'TaskExecutor'                THEN 'Task Executor'
            ELSE v_role_name
        END;

        -- Resolve or create agent_role row (if agent_role table exists)
        IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'main' AND table_name = 'agent_role'
        ) THEN
            SELECT agent_role_id
            INTO v_agent_role_id
            FROM main.agent_role
            WHERE role_name = v_agent_role_name
            ORDER BY agent_role_id
            LIMIT 1;

            IF v_agent_role_id IS NULL THEN
                INSERT INTO main.agent_role (
                    role_name,
                    role_description,
                    created_at,
                    updated_at
                )
                VALUES (
                    v_agent_role_name,
                    format(
                        'Auto-created from sp_ensure_agents_for_roles for category %s',
                        coalesce(v_agent_category, 'unknown')
                    ),
                    now(),
                    now()
                )
                RETURNING agent_role_id INTO v_agent_role_id;
            END IF;
        ELSE
            -- If agent_role table is missing, fall back to NULL role_id
            v_agent_role_id := NULL;
        END IF;

        -- Construct desired agent_name for this role
        v_agent_name := v_role_name || ' Agent';

        -- Check for existing agent with same name and role (or any role if NULL)
        IF v_agent_role_id IS NOT NULL THEN
            SELECT agent_id
            INTO v_existing_agent_id
            FROM main.agent
            WHERE agent_name = v_agent_name
              AND agent_role_id = v_agent_role_id
            ORDER BY agent_id
            LIMIT 1;
        ELSE
            SELECT agent_id
            INTO v_existing_agent_id
            FROM main.agent
            WHERE agent_name = v_agent_name
            ORDER BY agent_id
            LIMIT 1;
        END IF;

        IF v_existing_agent_id IS NOT NULL THEN
            CONTINUE;
        END IF;

        -- Build config JSON expected by sp_create_agent
        v_constraints      := COALESCE(v_role->'constraints', '[]'::jsonb);
        v_responsibilities := COALESCE(v_role->'responsibilities', '[]'::jsonb);
        v_success_criteria := COALESCE(v_role->'success_criteria', '[]'::jsonb);
        v_escalation       := COALESCE(v_role->'escalation', '[]'::jsonb);

        v_config := jsonb_build_object(
            'constraints',       v_constraints,
            'responsibilities',  v_responsibilities,
            'success_criteria',  v_success_criteria,
            'escalation',        v_escalation
        );

        v_capabilities := jsonb_build_object(
            'agent_category', v_agent_category,
            'project_id',     p_project_id
        );

        -- Only call sp_create_agent if it exists in this schema
        IF EXISTS (
            SELECT 1 FROM information_schema.routines
            WHERE routine_schema = 'main'
              AND routine_name = 'sp_create_agent'
        ) THEN
            CALL main.sp_create_agent(
                p_agent_name        => v_agent_name,
                p_agent_type        => v_agent_type,
                p_agent_role_id     => v_agent_role_id,
                p_api_key           => NULL,
                p_endpoint_url      => NULL,
                p_capabilities      => v_capabilities,
                p_config            => v_config,
                p_created_by        => p_created_by
            );
        ELSE
            -- Fallback: insert directly into agent table
            INSERT INTO main.agent (
                agent_name,
                agent_type,
                agent_role_id,
                api_key,
                endpoint_url,
                agent_status,
                capabilities,
                config,
                created_by,
                updated_by,
                created_at,
                updated_at
            )
            VALUES (
                v_agent_name,
                v_agent_type::text,
                v_agent_role_id,
                NULL,
                NULL,
                'ACTIVE',
                v_capabilities,
                v_config,
                p_created_by,
                p_created_by,
                now(),
                now()
            );
        END IF;

        -- Look up the newly created agent_id
        SELECT agent_id
        INTO v_new_agent_id
        FROM main.agent
        WHERE agent_name = v_agent_name
        ORDER BY agent_id DESC
        LIMIT 1;

        IF v_new_agent_id IS NULL THEN
            RAISE WARNING 'sp_ensure_agents_for_roles: Agent "%" was not found after creation', v_agent_name;
            CONTINUE;
        END IF;

        -- Emit AGENT_CREATED_FROM_TASKS event if event_log table exists
        IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'main' AND table_name = 'event_log'
        ) THEN
            INSERT INTO main.event_log (
                entity_type,
                entity_id,
                project_id,
                event_type,
                payload,
                created_by
            )
            VALUES (
                'AGENT',
                v_new_agent_id,
                p_project_id,
                'AGENT_CREATED_FROM_TASKS',
                jsonb_build_object(
                    'project_id',        p_project_id,
                    'agent_id',          v_new_agent_id,
                    'role_name',         v_role_name,
                    'agent_category',    v_agent_category,
                    'agent_role_name',   v_agent_role_name,
                    'agent_role_id',     v_agent_role_id,
                    'source',            'sp_ensure_agents_for_roles',
                    'role_payload',      v_role
                ),
                p_created_by
            );
        END IF;
    END LOOP;
END;
$BODY$;

-- ============================================================
-- 8. PROCEDURE: main.sp_start_task_execution
-- ============================================================

CREATE OR REPLACE PROCEDURE main.sp_start_task_execution(
    IN p_task_id           bigint,
    IN p_agent_id          bigint,
    IN p_agent_instance_id bigint,
    IN p_created_by        text DEFAULT 'system'
)
LANGUAGE 'plpgsql'
AS $BODY$
DECLARE
    v_task_execution_id bigint;
BEGIN
    -- If task_execution table is not present, do nothing
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'main' AND table_name = 'task_execution'
    ) THEN
        RAISE NOTICE 'main.task_execution table not found; sp_start_task_execution is a no-op in this schema';
        RETURN;
    END IF;

    INSERT INTO main.task_execution (
        task_id,
        agent_id,
        agent_instance_id,
        task_execution_status,
        started_at
    )
    VALUES (
        p_task_id,
        p_agent_id,
        p_agent_instance_id,
        'STARTED',
        now()
    )
    RETURNING task_execution_id INTO v_task_execution_id;

    -- Emit TASK_EXECUTION_STARTED event if event_log and task tables exist
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'main' AND table_name = 'event_log'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'main' AND table_name = 'task'
    ) THEN
        INSERT INTO main.event_log (
            entity_type,
            entity_id,
            project_id,
            event_type,
            payload,
            created_by
        )
        SELECT
            'TASK_EXECUTION',
            v_task_execution_id,
            t.project_id,
            'TASK_EXECUTION_STARTED',
            jsonb_build_object(
                'task_execution_id', v_task_execution_id,
                'task_id',           p_task_id,
                'agent_id',          p_agent_id,
                'agent_instance_id', p_agent_instance_id,
                'status',            'STARTED',
                'timestamp',         now()
            ),
            p_created_by
        FROM main.task t
        WHERE t.task_id = p_task_id;
    END IF;
END;
$BODY$;

-- ============================================================
-- 9. PROCEDURE: main.sp_finish_task_execution
-- ============================================================

CREATE OR REPLACE PROCEDURE main.sp_finish_task_execution(
    IN p_task_execution_id bigint,
    IN p_status            text,
    IN p_result_json       jsonb,
    IN p_logs_text         text,
    IN p_updated_by        text DEFAULT 'system'
)
LANGUAGE 'plpgsql'
AS $BODY$
DECLARE
    v_task_id    bigint;
    v_agent_id   bigint;
    v_event_type text;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'main' AND table_name = 'task_execution'
    ) THEN
        RAISE NOTICE 'main.task_execution table not found; sp_finish_task_execution is a no-op in this schema';
        RETURN;
    END IF;

    UPDATE main.task_execution
    SET
        task_execution_status = p_status,
        task_execution_result = p_result_json,
        logs                  = p_logs_text,
        finished_at           = now()
    WHERE task_execution_id = p_task_execution_id
    RETURNING task_id, agent_id INTO v_task_id, v_agent_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Task execution (id=%) not found', p_task_execution_id;
    END IF;

    v_event_type := CASE
        WHEN upper(coalesce(p_status, '')) IN ('FAILED', 'ERROR') THEN 'TASK_EXECUTION_FAILED'
        ELSE 'TASK_EXECUTION_COMPLETED'
    END;

    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'main' AND table_name = 'event_log'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'main' AND table_name = 'task'
    ) THEN
        INSERT INTO main.event_log (
            entity_type,
            entity_id,
            project_id,
            event_type,
            payload,
            created_by
        )
        SELECT
            'TASK_EXECUTION',
            p_task_execution_id,
            t.project_id,
            v_event_type,
            jsonb_build_object(
                'task_execution_id', p_task_execution_id,
                'task_id',           v_task_id,
                'agent_id',          v_agent_id,
                'status',            p_status,
                'finished_at',       now()
            ),
            p_updated_by
        FROM main.task t
        WHERE t.task_id = v_task_id;
    END IF;
END;
$BODY$;

-- ============================================================
-- 10. FUNCTION: main.fn_get_next_ready_task
-- ============================================================

CREATE OR REPLACE FUNCTION main.fn_get_next_ready_task(
    p_project_id bigint
)
RETURNS jsonb
LANGUAGE 'plpgsql'
AS $BODY$
DECLARE
    v_task jsonb;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'main' AND table_name = 'task'
    ) THEN
        RETURN NULL;
    END IF;

    SELECT jsonb_build_object(
        'task_id',        t.task_id,
        'project_id',     t.project_id,
        'agent_id',       t.agent_id,
        'document_id',    t.document_id,
        'task_name',      t.task_name,
        'task_type',      t.task_type,
        'description',    t.description,
        'parameters',     t.parameters,
        'priority',       t.priority,
        'task_notes',     t.task_notes,
        'task_data',      t.task_data
    )
    INTO v_task
    FROM main.task t
    WHERE t.project_id = p_project_id
      AND coalesce(t.status, 'PENDING') = 'PENDING'
      AND NOT EXISTS (
          SELECT 1
          FROM main.task_dependency d
          LEFT JOIN main.task_execution te
            ON te.task_id = d.depends_on_task_id
          WHERE d.task_id = t.task_id
            AND (
                te.task_execution_id IS NULL
                OR te.task_execution_status NOT IN ('COMPLETED', 'SUCCESS')
            )
      )
    ORDER BY
        COALESCE(t.priority, 3) ASC,
        t.created_at ASC
    LIMIT 1;

    RETURN v_task;
END;
$BODY$;

-- Set ownership
ALTER FUNCTION main.fn_spin_up_agent(bigint, bigint) OWNER TO postgres;
ALTER FUNCTION main.fn_get_project_documents(bigint) OWNER TO postgres;
ALTER FUNCTION main.fn_get_enhanced_rag_context(vector, bigint, integer, numeric, text[]) OWNER TO postgres;
ALTER FUNCTION main.fn_get_next_ready_task(bigint) OWNER TO postgres;
ALTER FUNCTION main.fn_get_workflow_run_summary(bigint) OWNER TO postgres;
ALTER PROCEDURE main.sp_spin_up_agent(OUT jsonb, IN bigint, IN bigint) OWNER TO postgres;
ALTER PROCEDURE main.sp_serialize_document(bigint, jsonb, character varying) OWNER TO postgres;
ALTER PROCEDURE main.sp_persist_generated_tasks(
    bigint,
    bigint,
    bigint,
    bigint,
    jsonb,
    text,
    text
) OWNER TO postgres;
ALTER PROCEDURE main.sp_ensure_agents_for_roles(
    bigint,
    jsonb,
    text
) OWNER TO postgres;
ALTER PROCEDURE main.sp_start_task_execution(
    bigint,
    bigint,
    bigint,
    text
) OWNER TO postgres;
ALTER PROCEDURE main.sp_finish_task_execution(
    bigint,
    text,
    jsonb,
    text,
    text
) OWNER TO postgres;

