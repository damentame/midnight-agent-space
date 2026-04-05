-- FUNCTION: main.fn_get_next_ready_task
--
-- Returns the next PENDING task for a project whose dependencies (if any)
-- have completed successfully. Selection is ordered by priority and
-- created_at.
--
-- DROP FUNCTION IF EXISTS main.fn_get_next_ready_task(bigint);

CREATE OR REPLACE FUNCTION main.fn_get_next_ready_task(
    p_project_id bigint,
    p_workflow_run_id bigint
)
RETURNS jsonb
LANGUAGE 'plpgsql'
AS $BODY$
DECLARE
    v_task jsonb;
BEGIN
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
      AND (
          p_workflow_run_id IS NULL
          OR ((t.task_data->>'workflow_run_id')::bigint = p_workflow_run_id)
      )
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

    IF v_task IS NULL THEN
        RETURN NULL;
    END IF;

    RETURN v_task;
END;
$BODY$;

ALTER FUNCTION main.fn_get_next_ready_task(bigint)
    OWNER TO postgres;

