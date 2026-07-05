"""Tests for token usage tracking and efficiency targets."""
from dashboard.backend.services.token_usage_service import (
    APP_EQUIVALENT_TARGETS,
    compute_cost_usd,
    estimate_tokens,
    extract_usage_from_cli_streams,
    token_usage_service,
)


def test_estimate_tokens_from_text() -> None:
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("a" * 4000) == 1000


def test_extract_usage_from_claude_stream() -> None:
    lines = [
        '{"type":"result","usage":{"input_tokens":1200,"output_tokens":800}}',
    ]
    usage = extract_usage_from_cli_streams(lines)
    assert usage == {"input_tokens": 1200, "output_tokens": 800, "total_tokens": 2000}


def test_aggregate_records_and_efficiency() -> None:
    records = [
        token_usage_service.build_task_usage_record(
            task={"task_type": "implementation", "task_name": "Implement section 1: navbar"},
            model="sonnet",
            runtime_provider="claude-cli",
            prompt="x" * 4000,
            cli_result={"stdout_tail": ['{"type":"result","usage":{"input_tokens":1000,"output_tokens":500}}'], "stderr_tail": []},
            context_chars=2000,
        ),
        token_usage_service.build_task_usage_record(
            task={"task_type": "implementation", "task_name": "Implement section 2: hero"},
            model="haiku",
            runtime_provider="claude-cli",
            prompt="y" * 2000,
            cli_result={"stdout_tail": [], "stderr_tail": []},
            context_chars=1000,
        ),
    ]
    summary = token_usage_service.aggregate_records(records)
    assert summary["totals"]["total_tokens"] > 0
    assert len(summary["by_model"]) >= 1
    assert summary["efficiency"]["commercial_target"] == APP_EQUIVALENT_TARGETS["commercial"]


def test_compute_cost_usd_sonnet() -> None:
    cost = compute_cost_usd(input_tokens=1_000_000, output_tokens=200_000, model="sonnet")
    assert cost > 0
