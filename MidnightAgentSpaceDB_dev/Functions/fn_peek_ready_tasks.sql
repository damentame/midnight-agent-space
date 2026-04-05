-- FUNCTION: main.fn_peek_ready_tasks
-- Returns up to p_limit next ready tasks (same selection as fn_get_next_ready_task) as a JSON array.
-- Does not mutate task state; used to plan batched execution / model tier for follow-up chains.
--
-- DROP FUNCTION IF EXISTS main.fn_peek_ready_tasks(bigint, bigint, integer);

CREATE OR REPLACE FUNCTION main.fn_peek_ready_tasks(
    p_project_id bigint,
    p_workflow_run_id bigint DEFAULT NULL,
    p_limit integer DEFAULT 50
)
RETURNS jsonb
LANGUAGE 'plpgsql'
AS $BODY$
DECLARE
    v_tasks jsonb;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'main' AND table_name = 'task'
    ) THEN
        RETURN '[]'::jsonb;
    END IF;

    SELECT COALESCE(
        jsonb_agg(
            jsonb_build_object(
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
            ) ORDER BY COALESCE(t.priority, 3) ASC, t.created_at ASC
        ),
        '[]'::jsonb
    )
    INTO v_tasks
    FROM (
        SELECT *
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
        LIMIT p_limit
    ) t;

    RETURN v_tasks;
END;
$BODY$;

ALTER FUNCTION main.fn_peek_ready_tasks(bigint, bigint, integer) OWNER TO postgres;
