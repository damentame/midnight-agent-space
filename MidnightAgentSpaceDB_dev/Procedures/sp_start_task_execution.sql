-- PROCEDURE: main.sp_start_task_execution
--
-- Inserts a new row into main.task_execution to represent the start of a
-- task execution and emits a TASK_EXECUTION_STARTED event.
--
-- DROP PROCEDURE IF EXISTS main.sp_start_task_execution(bigint, bigint, bigint, text);

CREATE OR REPLACE PROCEDURE main.sp_start_task_execution(
    IN p_task_id          bigint,
    IN p_agent_id         bigint,
    IN p_agent_instance_id bigint,
    IN p_created_by       text DEFAULT 'system'
)
LANGUAGE 'plpgsql'
AS $BODY$
DECLARE
    v_task_execution_id bigint;
BEGIN
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

    -- Mark task as IN_PROGRESS so it is not repeatedly selected as PENDING
    UPDATE main.task
    SET
        status = 'IN_PROGRESS',
        updated_at = now(),
        updated_by = p_created_by
    WHERE task_id = p_task_id;

    -- Emit TASK_EXECUTION_STARTED event
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
END;
$BODY$;

ALTER PROCEDURE main.sp_start_task_execution(
    bigint,
    bigint,
    bigint,
    text
)
    OWNER TO postgres;

