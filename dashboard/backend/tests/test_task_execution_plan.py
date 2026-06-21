"""Execution batch planning at serialize time."""
from dashboard.backend.services.task_execution_plan_service import (
    annotate_task_execution_fields,
    build_execution_batches,
)


def test_build_execution_batches_groups_sections() -> None:
    tasks = [
        {"task_name": "Analyze", "task_type": "analysis", "task_data": {}},
        {
            "task_name": "Implement section 1: navbar",
            "task_type": "implementation",
            "task_data": {"parallel_group": "sections", "parallel_safe": True, "design_section_slug": "navbar"},
        },
        {
            "task_name": "Implement section 2: hero",
            "task_type": "implementation",
            "task_data": {"parallel_group": "sections", "parallel_safe": True, "design_section_slug": "hero"},
        },
        {"task_name": "Integrate sections and assets", "task_type": "implementation", "task_data": {}},
    ]
    batches = build_execution_batches(tasks, section_max_concurrency=4)
    assert len(batches) == 3
    assert batches[0]["mode"] == "sequential"
    assert batches[1]["mode"] == "parallel"
    assert batches[1]["max_concurrency"] == 4
    assert len(batches[1]["tasks"]) == 2
    annotated = annotate_task_execution_fields(tasks[1], sequence_index=1, execution_batches=batches)
    assert annotated["execution_mode"] == "parallel"
    assert annotated["execution_max_concurrency"] == 4
