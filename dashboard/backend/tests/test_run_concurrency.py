"""Concurrency gate and stale run release."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from dashboard.backend.services.run_service import RunService


@pytest.mark.asyncio
async def test_release_stale_running_runs_clears_orphan_db_rows() -> None:
    service = RunService()
    db = MagicMock()
    db.fetch_many = AsyncMock(
        return_value=[{"agent_run_id": 99, "project_id": 7}]
    )
    service._update_run = AsyncMock()
    service.create_event = AsyncMock()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "dashboard.backend.services.run_service.schema_support.table_exists",
            AsyncMock(return_value=True),
        )
        released = await service._release_stale_running_runs(db)

    assert released == [99]
    service._update_run.assert_awaited_once()
    assert service._update_run.await_args.kwargs["status"] == "FAILED"


@pytest.mark.asyncio
async def test_live_executor_count_prunes_done_tasks() -> None:
    service = RunService()
    done_task = MagicMock()
    done_task.done.return_value = True
    active_task = MagicMock()
    active_task.done.return_value = False
    service._active_tasks = {1: done_task, 2: active_task}
    db = MagicMock()
    db.fetch_many = AsyncMock(return_value=[])

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "dashboard.backend.services.run_service.schema_support.table_exists",
            AsyncMock(return_value=True),
        )
        count = await service._live_executor_count(db)

    assert count == 1
    assert 1 not in service._active_tasks
    assert 2 in service._active_tasks
