"""Serialize must not overwrite Figma import structured_json."""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from dashboard.backend.routes.projects import _serialize_project_documents


@pytest.mark.asyncio
async def test_serialize_skips_figma_import_documents() -> None:
    figma_structured = {
        "content_kind": "figma_import",
        "agent_context": {
            "compact_spec": {"root_name": "Home", "node_count": 5},
            "text_preview": "Figma design tree",
            "image_document_ids": [99],
        },
    }
    db = MagicMock()
    db.fetch_many = AsyncMock(
        return_value=[
            {
                "document_id": 1,
                "document_name": "Figma: Home",
                "document_type": "figma_import",
                "raw_text_content": "# Figma spec",
                "file_extension": ".md",
                "file_mime_type": "text/markdown",
                "file_size_bytes": 100,
                "serialization_status": "RAG_READY",
            },
            {
                "document_id": 2,
                "document_name": "export.png",
                "document_type": "figma_export_image",
                "raw_text_content": None,
                "file_extension": ".png",
                "file_mime_type": "image/png",
                "file_size_bytes": 500,
                "serialization_status": "RAG_READY",
            },
            {
                "document_id": 3,
                "document_name": "requirements.txt",
                "document_type": "text",
                "raw_text_content": "Build the app",
                "file_extension": ".txt",
                "file_mime_type": "text/plain",
                "file_size_bytes": 12,
                "serialization_status": "PENDING",
            },
        ]
    )
    db.execute = AsyncMock()

    result = await _serialize_project_documents(db, project_id=5)

    assert result["count"] == 3
    skipped = [row for row in result["documents"] if row.get("skipped")]
    assert len(skipped) == 2
    assert db.execute.await_count == 1
    call_args = db.execute.await_args_list[0][0]
    descriptor = json.loads(call_args[1])
    assert descriptor["content_kind"] == "text"
    assert call_args[4] == 3
    assert call_args[3] == 5
