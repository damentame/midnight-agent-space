-- PROCEDURE: main.sp_finish_task_execution
--
-- Updates an existing main.task_execution row to reflect completion or
-- failure, stores result/logs, and emits TASK_EXECUTION_COMPLETED or
-- TASK_EXECUTION_FAILED events.
--
-- DROP PROCEDURE IF EXISTS main.sp_finish_task_execution(bigint, text, jsonb, text, text);

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
    v_task_id   bigint;
    v_agent_id  bigint;
    v_event_type text;
BEGIN
    -- Update task_execution row
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

    -- Update main.task.status so fn_get_next_ready_task does not continue
    -- returning already executed tasks.
    UPDATE main.task
    SET
        status = CASE
            WHEN upper(coalesce(p_status, '')) IN ('FAILED', 'ERROR') THEN 'FAILED'
            ELSE 'COMPLETED'
        END,
        updated_at = now(),
        updated_by = p_updated_by
    WHERE task_id = v_task_id;

    v_event_type := CASE
        WHEN upper(coalesce(p_status, '')) IN ('FAILED', 'ERROR') THEN 'TASK_EXECUTION_FAILED'
        ELSE 'TASK_EXECUTION_COMPLETED'
    END;

    -- Emit TASK_EXECUTION_* event
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
END;
$BODY$;

ALTER PROCEDURE main.sp_finish_task_execution(
    bigint,
    text,
    jsonb,
    text,
    text
)
    OWNER TO postgres;

