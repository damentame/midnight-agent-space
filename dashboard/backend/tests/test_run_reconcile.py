"""Orphan run recovery on API restart."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dashboard.backend.services.run_service import RunService


@pytest.mark.asyncio
async def test_recover_orphan_marks_failed_when_no_active_task() -> None:
    service = RunService()
    db = AsyncMock()
    db.fetch_many = AsyncMock(
        return_value=[{"agent_run_id": 36, "project_id": 5, "started_at": None}],
    )

    with patch("dashboard.backend.services.run_service.schema_support.table_exists", new=AsyncMock(return_value=True)):
        with patch.object(service, "reconcile_run", new=AsyncMock(return_value={"ok": True, "status": "RUNNING"})):
            with patch.object(service, "_update_run", new=AsyncMock()) as update_run:
                with patch.object(service, "create_event", new=AsyncMock()):
                    result = await service.recover_orphan_runs(db)

    assert result["ok"] is True
    assert len(result["recovered"]) == 1
    assert result["recovered"][0]["status"] == "FAILED"
    update_run.assert_awaited_once()
    kwargs = update_run.await_args.kwargs
    assert kwargs["status"] == "FAILED"
    assert kwargs["result_payload"]["orphaned_on_restart"] is True


@pytest.mark.asyncio
async def test_recover_skips_runs_with_active_asyncio_task() -> None:
    service = RunService()
    active_task = MagicMock()
    active_task.done.return_value = False
    service._active_tasks[99] = active_task

    db = AsyncMock()
    db.fetch_many = AsyncMock(
        return_value=[{"agent_run_id": 99, "project_id": 5, "started_at": None}],
    )

    with patch("dashboard.backend.services.run_service.schema_support.table_exists", new=AsyncMock(return_value=True)):
        with patch.object(service, "reconcile_run", new=AsyncMock()) as reconcile:
            result = await service.recover_orphan_runs(db)

    reconcile.assert_not_awaited()
    assert result["recovered"] == []
