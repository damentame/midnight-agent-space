"""Timeline event queries must preserve lifecycle events."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from dashboard.backend.services import run_service as run_service_module
from dashboard.backend.services.run_service import RunService


@pytest.mark.asyncio
async def test_list_run_events_timeline_includes_lifecycle_when_verbose_floods(monkeypatch) -> None:
    service = RunService()

    lifecycle = [
        {"agent_event_id": 1, "event_type": "RUN_STARTED", "event_payload": {}},
        {"agent_event_id": 2, "event_type": "TASK_STARTED", "event_payload": {"task_id": 76}},
    ]
    verbose = [
        {"agent_event_id": 1000 + index, "event_type": "THINKING", "event_payload": {}}
        for index in range(5)
    ]

    db = MagicMock()

    async def fetch_many(query, *args):
        if "NOT (" in query:
            return lifecycle
        return list(reversed(verbose))

    db.fetch_many = AsyncMock(side_effect=fetch_many)
    monkeypatch.setattr(run_service_module.schema_support, "table_exists", AsyncMock(return_value=True))
    monkeypatch.setattr(run_service_module, "decode_jsonb_fields", lambda row, _fields: row)

    events = await service.list_run_events(db, run_id=41, limit=100, mode="timeline")

    types = [event["event_type"] for event in events]
    assert "RUN_STARTED" in types
    assert "TASK_STARTED" in types
    assert events[0]["agent_event_id"] == 1
