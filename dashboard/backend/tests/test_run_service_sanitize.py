"""Ensure execution payloads stay JSON-safe."""
from dashboard.backend.services.run_service import RunService


def test_sanitize_strips_large_streams() -> None:
    raw = {
        "ok": True,
        "stdout_tail": [f"line-{index}" for index in range(20)],
        "stderr_tail": [f"err-{index}" for index in range(20)],
        "exit_code": 0,
    }
    sanitized = RunService._sanitize_cli_task_result(raw)
    assert len(sanitized["stdout_tail"]) == 4
    assert len(sanitized["stderr_tail"]) == 4


def test_build_execution_result_has_no_nested_self_reference() -> None:
    per_task = [
        {"ok": True, "exit_code": 0, "stdout_tail": ["done"], "stderr_tail": []},
        {"ok": False, "exit_code": 1, "error": "failed", "stdout_tail": [], "stderr_tail": ["boom"]},
    ]
    payload = RunService._build_execution_result(
        per_task_results=per_task,
        all_ok=False,
        selection_mode="optimized",
    )
    assert payload["ok"] is False
    assert len(payload["per_task_results"]) == 2
    assert "per_task_results" not in payload["per_task_results"][0]
