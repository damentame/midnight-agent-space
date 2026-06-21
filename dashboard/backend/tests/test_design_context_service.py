"""Design context staging into worktrees."""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from dashboard.backend.services.design_context_service import DesignContextService


@pytest.mark.asyncio
async def test_stage_design_context_writes_manifest_and_exports(tmp_path) -> None:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    png_bytes = b"\x89PNG\r\n\x1a\n"

    db = MagicMock()
    db.fetch_many = AsyncMock(
        return_value=[
            {
                "document_id": 10,
                "parent_document_id": None,
                "document_name": "Figma: Home",
                "document_type": "figma_import",
                "raw_text_content": "# Design spec",
                "structured_json": {
                    "agent_context": {
                        "compact_spec": {"root_name": "Home", "node_count": 2},
                        "image_document_ids": [11],
                    }
                },
                "has_binary": False,
                "is_active_version": True,
            },
            {
                "document_id": 11,
                "parent_document_id": 10,
                "document_name": "export 1",
                "document_type": "figma_export_image",
                "raw_text_content": None,
                "structured_json": None,
                "has_binary": True,
                "is_active_version": True,
            },
        ]
    )
    db.get_document_file = AsyncMock(
        return_value={
            "file_content": png_bytes,
            "file_mime_type": "image/png",
        }
    )

    service = DesignContextService()
    result = await service.stage_design_context(
        db,
        project_id=5,
        worktree_path=str(worktree),
    )

    assert result["ok"] is True
    design_dir = worktree / ".midnight" / "design"
    assert (design_dir / "DESIGN_MANIFEST.md").exists()
    assert (design_dir / "figma-spec.json").exists()
    assert (design_dir / "figma-spec.md").exists()
    assert (design_dir / "exports" / "frame-1.png").exists()
    spec = json.loads((design_dir / "figma-spec.json").read_text(encoding="utf-8"))
    assert spec["root_name"] == "Home"


@pytest.mark.asyncio
async def test_validate_design_context_flags_missing_spec() -> None:
    db = MagicMock()
    db.fetch_many = AsyncMock(
        return_value=[
            {
                "document_id": 10,
                "parent_document_id": None,
                "document_name": "Figma: Home",
                "document_type": "figma_import",
                "raw_text_content": None,
                "structured_json": {"agent_context": {"sections": []}},
                "has_binary": False,
                "is_active_version": True,
            },
        ]
    )
    service = DesignContextService()
    result = await service.validate_design_context(db, project_id=5)
    assert result["required"] is True
    assert result["ok"] is False
    assert result["gaps"]
