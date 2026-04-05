-- FUNCTION: main.fn_validate_type(anyelement, regtype, boolean, text, boolean)

-- DROP FUNCTION IF EXISTS main.fn_validate_type(anyelement, regtype, boolean, text, boolean);

CREATE OR REPLACE FUNCTION main.fn_validate_type(
	p_value anyelement,
	p_expected_type regtype,
	p_should_be_type boolean DEFAULT true,
	p_custom_error_message text DEFAULT NULL::text,
	p_include_full_stack boolean DEFAULT true)
    RETURNS boolean
    LANGUAGE 'plpgsql'
    COST 100
    VOLATILE PARALLEL UNSAFE
AS $BODY$
DECLARE
    v_is_correct_type BOOLEAN;
    v_actual_type REGTYPE;
    v_error_stack TEXT;
    v_call_stack TEXT[];
    v_formatted_stack TEXT;
    v_error_detail TEXT;
    v_error_context TEXT;
    v_error_line TEXT;
    v_error_msg TEXT;
BEGIN
    -- Get the call stack BEFORE validation for trace using PG_CONTEXT
    GET DIAGNOSTICS v_error_context = PG_CONTEXT;
    v_error_stack := v_error_context;
    
    -- Determine actual type of the value
    v_actual_type := pg_typeof(p_value);
    
    -- Check if value is of expected type
    v_is_correct_type := (v_actual_type = p_expected_type);
    
    -- Validate based on p_should_be_type
    IF p_should_be_type THEN
        -- Should BE the expected type
        IF NOT v_is_correct_type THEN
            -- Format call stack - split by lines and format
            IF v_error_stack IS NOT NULL AND v_error_stack != '' THEN
                v_call_stack := string_to_array(v_error_stack, E'\n');
                v_formatted_stack := array_to_string(
                    array( 
                        SELECT format('  [%s] %s', 
                            row_number() OVER (), 
                            stack_line
                        ) 
                        FROM unnest(v_call_stack) AS stack_line
                    ),
                    E'\n'
                );
            ELSE
                v_formatted_stack := '  [1] (No stack trace available)';
            END IF;
            
            -- Get current error context for line number
            GET DIAGNOSTICS v_error_context = PG_CONTEXT;
            v_error_line := substring(v_error_context from 'line (\d+)');
            
            -- Build error message using FORMAT to avoid E'' syntax issues
            v_error_msg := FORMAT(
                '%sTYPE VALIDATION FAILED!' || E'\n' ||
                '  Expected Type: %s' || E'\n' ||
                '  Actual Type:   %s' || E'\n' ||
                '  Value:         "%s"' || E'\n' ||
                '  Error Line:    %s' || E'\n' ||
                '  Call Stack:' || E'\n' ||
                '%s' || E'\n',
                CASE WHEN p_custom_error_message IS NOT NULL 
                     THEN p_custom_error_message || E'\n' 
                     ELSE '' END,
                p_expected_type,
                v_actual_type,
                p_value,
                COALESCE(v_error_line, 'unknown'),
                CASE WHEN p_include_full_stack 
                     THEN v_formatted_stack 
                     ELSE 'Stack trace disabled' END
            );
            
            RAISE EXCEPTION '%', v_error_msg
            USING 
                ERRCODE = '2200G',  -- invalid_parameter_value
                DETAIL = format('Type mismatch: expected %s but got %s', 
                    p_expected_type, v_actual_type),
                HINT = format('Try casting: %s::%s', p_value, p_expected_type);
        END IF;
    ELSE
        -- Should NOT BE the expected type
        IF v_is_correct_type THEN
            GET DIAGNOSTICS v_error_context = PG_CONTEXT;
            v_error_line := substring(v_error_context from 'line (\d+)');
            
            v_error_msg := FORMAT(
                '%sTYPE VALIDATION FAILED: Value should NOT be of type!' || E'\n' ||
                '  Forbidden Type: %s' || E'\n' ||
                '  Actual Type:    %s' || E'\n' ||
                '  Value:          "%s"' || E'\n' ||
                '  Error Line:     %s',
                CASE WHEN p_custom_error_message IS NOT NULL 
                     THEN p_custom_error_message || E'\n' 
                     ELSE '' END,
                p_expected_type,
                v_actual_type,
                p_value,
                COALESCE(v_error_line, 'unknown')
            );
            
            RAISE EXCEPTION '%', v_error_msg
            USING 
                ERRCODE = '2200G';
        END IF;
    END IF;
    
    RETURN TRUE;  -- Validation passed
END;
$BODY$;

ALTER FUNCTION main.fn_validate_type(anyelement, regtype, boolean, text, boolean)
    OWNER TO postgres;
