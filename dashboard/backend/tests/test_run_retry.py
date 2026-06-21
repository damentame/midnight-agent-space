"""Retry deduplication and task continuation."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from dashboard.backend.services.run_service import RunService, _COMPLETED_TASK_STATUSES


@pytest.mark.asyncio
async def test_live_project_run_returns_only_executor_backed_rows() -> None:
    service = RunService()
    db = MagicMock()
    db.fetch_one = AsyncMock(return_value={"agent_run_id": 53, "project_id": 8, "status": "RUNNING"})
    live_task = MagicMock()
    live_task.done.return_value = False
    service._active_tasks = {53: live_task}

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "dashboard.backend.services.run_service.schema_support.table_exists",
            AsyncMock(return_value=True),
        )
        row = await service._live_project_run(db, project_id=8)

    assert row is not None
    assert row["agent_run_id"] == 53


@pytest.mark.asyncio
async def test_live_project_run_ignores_stale_db_row_without_executor() -> None:
    service = RunService()
    db = MagicMock()
    db.fetch_one = AsyncMock(return_value={"agent_run_id": 53, "project_id": 8, "status": "RUNNING"})
    service._active_tasks = {}

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "dashboard.backend.services.run_service.schema_support.table_exists",
            AsyncMock(return_value=True),
        )
        row = await service._live_project_run(db, project_id=8)

    assert row is None


def test_completed_task_statuses_include_done_and_passed() -> None:
    assert "COMPLETED" in _COMPLETED_TASK_STATUSES
    assert "DONE" in _COMPLETED_TASK_STATUSES
    assert "PASSED" in _COMPLETED_TASK_STATUSES


def test_first_incomplete_task_skips_completed_prefix() -> None:
    tasks = [
        {"task_id": 125, "task_name": "Analyze", "status": "COMPLETED"},
        {"task_id": 135, "task_name": "Integrate sections and assets", "status": "FAILED"},
        {"task_id": 136, "task_name": "Review", "status": "FAILED"},
    ]
    first = RunService._first_incomplete_task(tasks)
    assert first is not None
    assert first["task_id"] == 135


def test_task_is_completed() -> None:
    assert RunService._task_is_completed({"status": "COMPLETED"}) is True
    assert RunService._task_is_completed({"status": "FAILED"}) is False
