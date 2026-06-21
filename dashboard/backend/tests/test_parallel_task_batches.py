"""Task batch partitioning for parallel section execution."""
from dashboard.backend.services.run_service import RunService


def test_is_parallel_section_task_by_name() -> None:
    task = {"task_name": "Implement section 3: about", "task_data": {}}
    assert RunService._is_parallel_section_task(task) is True
    assert RunService._is_parallel_section_task({"task_name": "Integrate sections and assets", "task_data": {}}) is False


def test_partition_groups_parallel_section_tasks() -> None:
    tasks = [
        {"task_id": 1, "task_name": "Analyze", "task_data": {}},
        {"task_id": 2, "task_name": "Plan", "task_data": {}},
        {
            "task_id": 3,
            "task_name": "Implement section 1: navbar",
            "task_data": {"parallel_group": "sections", "parallel_safe": True},
        },
        {
            "task_id": 4,
            "task_name": "Implement section 2: hero",
            "task_data": {"parallel_group": "sections", "parallel_safe": True},
        },
        {"task_id": 5, "task_name": "Integrate sections and assets", "task_data": {}},
        {"task_id": 6, "task_name": "Review", "task_data": {}},
    ]
    batches = RunService._partition_task_batches(tasks)
    assert batches[0] == ("sequential", [tasks[0]])
    assert batches[1] == ("sequential", [tasks[1]])
    assert batches[2][0] == "parallel"
    assert len(batches[2][1]) == 2
    assert batches[3] == ("sequential", [tasks[4]])
    assert batches[4] == ("sequential", [tasks[5]])
