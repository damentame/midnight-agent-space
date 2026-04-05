-- PROCEDURE: main.sp_ensure_agents_for_roles
--
-- Ensures concrete main.agent rows exist for each role definition provided
-- in p_roles_json and emits AGENT_CREATED_FROM_TASKS events for any newly
-- created agents.
--
-- Expected p_roles_json shape:
-- {
--   "roles": [
--     {
--       "role_name": "Product Manager",
--       "agent_category": "ProjectManager",            -- or BusinessRequirementsAnalyst, TaskExecutor, etc.
--       "responsibilities": [...],
--       "constraints": [...],
--       "success_criteria": [...],
--       "escalation": [...]                            -- optional
--     }
--   ]
-- }
--
-- DROP PROCEDURE IF EXISTS main.sp_ensure_agents_for_roles(bigint, jsonb, text);

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
    -- Validate roles JSON structure
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

        -- Resolve or create agent_role row
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

        -- Construct desired agent_name for this role
        v_agent_name := v_role_name || ' Agent';

        -- Check for existing agent with same name and role
        SELECT agent_id
        INTO v_existing_agent_id
        FROM main.agent
        WHERE agent_name = v_agent_name
          AND agent_role_id = v_agent_role_id
        ORDER BY agent_id
        LIMIT 1;

        IF v_existing_agent_id IS NOT NULL THEN
            -- Agent already exists; nothing to create for this role
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

        -- Simple capabilities template tagged by category and project
        v_capabilities := jsonb_build_object(
            'agent_category', v_agent_category,
            'project_id',     p_project_id
        );

        -- Create new agent using existing procedure
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

        -- Look up the newly created agent_id
        SELECT agent_id
        INTO v_new_agent_id
        FROM main.agent
        WHERE agent_name = v_agent_name
          AND agent_role_id = v_agent_role_id
        ORDER BY agent_id DESC
        LIMIT 1;

        IF v_new_agent_id IS NULL THEN
            RAISE WARNING 'sp_ensure_agents_for_roles: Agent "%" was not found after creation', v_agent_name;
            CONTINUE;
        END IF;

        -- Emit AGENT_CREATED_FROM_TASKS event for this new agent
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
    END LOOP;
END;
$BODY$;

ALTER PROCEDURE main.sp_ensure_agents_for_roles(
    bigint,
    jsonb,
    text
)
    OWNER TO postgres;

