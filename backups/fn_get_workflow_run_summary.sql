-- FUNCTION: main.fn_get_workflow_run_summary(bigint)
--
-- Returns a human-readable JSON summary of a workflow_run and
-- the associated event_log entries within its time window.
--
-- DROP FUNCTION IF EXISTS main.fn_get_workflow_run_summary(bigint);

CREATE OR REPLACE FUNCTION main.fn_get_workflow_run_summary(
    p_workflow_run_id bigint
)
RETURNS jsonb
LANGUAGE 'plpgsql'
AS $BODY$
DECLARE
    v_run        main.workflow_run%ROWTYPE;
    v_events     jsonb;
    v_activities jsonb;
BEGIN
    SELECT *
    INTO v_run
    FROM main.workflow_run
    WHERE workflow_run_id = p_workflow_run_id;

    IF NOT FOUND THEN
        RETURN NULL;
    END IF;

    SELECT COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'event_log_id', e.event_log_id,
                'entity_type',  e.entity_type,
                'entity_id',    e.entity_id,
                'event_type',   e.event_type,
                'created_at',   e.created_at,
                'payload',      e.payload
            )
            ORDER BY e.created_at
        ),
        '[]'::jsonb
    )
    INTO v_events
    FROM main.event_log e
    WHERE e.project_id = v_run.project_id
      AND e.created_at >= COALESCE(v_run.started_at, v_run.created_at)
      AND (v_run.finished_at IS NULL OR e.created_at <= v_run.finished_at);

    SELECT COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'activity_run_id', ar.activity_run_id,
                'workflow_id',     ar.workflow_id,
                'run_id',          ar.run_id,
                'activity_type',   ar.activity_type,
                'activity_id',     ar.activity_id,
                'status',          ar.status,
                'started_at',      ar.started_at,
                'finished_at',     ar.finished_at,
                'input_data',      ar.input_data,
                'result_data',     ar.result_data,
                'error_message',   ar.error_message
            )
            ORDER BY ar.started_at
        ),
        '[]'::jsonb
    )
    INTO v_activities
    FROM main.activity_run ar
    WHERE ar.workflow_id = v_run.workflow_name
      AND ar.run_id IS NOT NULL;

    RETURN jsonb_build_object(
        'workflow_run', jsonb_build_object(
            'workflow_run_id',   v_run.workflow_run_id,
            'workflow_name',     v_run.workflow_name,
            'project_id',        v_run.project_id,
            'agent_instance_id', v_run.agent_instance_id,
            'status',            v_run.status,
            'input_data',        v_run.input_data,
            'result_data',       v_run.result_data,
            'started_at',        v_run.started_at,
            'finished_at',       v_run.finished_at
        ),
        'events',        v_events,
        'activity_runs', v_activities
    );
END;
$BODY$;

ALTER FUNCTION main.fn_get_workflow_run_summary(bigint)
    OWNER TO postgres;

