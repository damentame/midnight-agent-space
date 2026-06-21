"""Table-driven tests for balanced agent routing."""
from dashboard.backend.services.agent_routing_service import build_task_agent_plan, task_role


def _task(task_id: int, task_type: str, task_name: str = "") -> dict:
    return {
        "task_id": task_id,
        "task_type": task_type,
        "task_name": task_name,
        "description": "",
    }


def test_analysis_routes_to_cursor_agent_when_balanced() -> None:
    plan = build_task_agent_plan(
        primary_provider="codex-cli",
        reviewer_provider="claude-cli",
        model_selection_mode="optimized",
        fixed_model=None,
        tasks=[_task(1, "analysis", "Analyze requirements")],
        cursor_available=True,
    )
    assert plan[0]["runtime_provider"] == "cursor-agent"
    assert plan[0]["task_role"] == "code"


def test_review_routes_to_reviewer_cli() -> None:
    plan = build_task_agent_plan(
        primary_provider="cursor-agent",
        reviewer_provider="claude-cli",
        model_selection_mode="optimized",
        fixed_model=None,
        tasks=[_task(2, "review", "Design review")],
        cursor_available=True,
    )
    assert plan[0]["runtime_provider"] == "claude-cli"
    assert plan[0]["task_role"] == "review"


def test_implementation_and_planning_use_cursor_in_balanced_mode() -> None:
    tasks = [
        _task(3, "planning", "Plan build"),
        _task(4, "implementation", "Build UI"),
    ]
    plan = build_task_agent_plan(
        primary_provider="codex-cli",
        reviewer_provider="claude-cli",
        model_selection_mode="optimized",
        fixed_model=None,
        tasks=tasks,
        cursor_available=True,
    )
    assert [row["runtime_provider"] for row in plan] == ["cursor-agent", "cursor-agent"]


def test_fixed_mode_keeps_primary_for_code_tasks() -> None:
    plan = build_task_agent_plan(
        primary_provider="codex-cli",
        reviewer_provider="claude-cli",
        model_selection_mode="fixed",
        fixed_model="gpt-4",
        tasks=[_task(5, "implementation", "Implement feature")],
        cursor_available=True,
    )
    assert plan[0]["runtime_provider"] == "codex-cli"


def test_task_role_hints_from_name() -> None:
    assert task_role(_task(6, "general", "Verify design adherence")) == "review"
    assert task_role(_task(7, "general", "Build frontend component")) == "code"
