"""Design context v2 staging and validation."""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from dashboard.backend.services.design_context_service import DesignContextService


@pytest.mark.asyncio
async def test_stage_v2_writes_sections_assets_tokens(tmp_path) -> None:
    worktree = tmp_path / "wt"
    worktree.mkdir()
    png = b"\x89PNG\r\n\x1a\n"

    db = MagicMock()
    db.fetch_many = AsyncMock(
        return_value=[
            {
                "document_id": 10,
                "parent_document_id": None,
                "document_name": "Figma: Site",
                "document_type": "figma_import",
                "raw_text_content": "# spec",
                "structured_json": {
                    "agent_context": {
                        "extraction_version": "v2",
                        "compact_spec": {"root_name": "Site"},
                        "sections": [
                            {
                                "slug": "hero",
                                "name": "Hero",
                                "section_export_document_id": 11,
                                "manifest_text": "Hero section",
                            }
                        ],
                        "tokens": {"colors": {"--color-1": "#fff"}},
                        "assets": [{"node_id": "1:4", "filename": "1-4.png"}],
                    }
                },
                "has_binary": False,
                "is_active_version": True,
            },
            {
                "document_id": 11,
                "parent_document_id": 10,
                "document_name": "hero png",
                "document_type": "figma_section_export",
                "structured_json": {"section_slug": "hero"},
                "has_binary": True,
                "is_active_version": True,
            },
            {
                "document_id": 12,
                "parent_document_id": 10,
                "document_name": "asset",
                "document_type": "figma_asset",
                "structured_json": {"filename": "1-4.png", "node_id": "1:4"},
                "has_binary": True,
                "is_active_version": True,
            },
        ]
    )
    db.get_document_file = AsyncMock(return_value={"file_content": png})

    result = await DesignContextService().stage_design_context(db, project_id=5, worktree_path=str(worktree))
    design = worktree / ".midnight" / "design"
    assert result["ok"]
    assert (design / "sections" / "hero.json").exists()
    assert (design / "sections" / "hero.png").exists()
    assert (design / "assets" / "1-4.png").exists()
    assert (design / "tokens.css").exists()
    assert (design / "ASSET_MANIFEST.json").exists()


@pytest.mark.asyncio
async def test_validate_v2_structural_ready_with_sections() -> None:
    db = MagicMock()
    db.fetch_many = AsyncMock(
        return_value=[
            {
                "document_id": 10,
                "document_type": "figma_import",
                "document_name": "Figma",
                "raw_text_content": "x",
                "structured_json": {
                    "agent_context": {
                        "compact_spec": {"tree": {}},
                        "sections": [{"slug": "hero", "section_export_document_id": 11}],
                        "assets": [{"node_id": "1:4"}],
                    }
                },
                "has_binary": False,
                "is_active_version": True,
            },
            {
                "document_id": 11,
                "document_type": "figma_section_export",
                "has_binary": True,
                "is_active_version": True,
            },
            {
                "document_id": 12,
                "document_type": "figma_asset",
                "has_binary": True,
                "is_active_version": True,
            },
        ]
    )
    result = await DesignContextService().validate_design_context(db, project_id=5)
    assert result["required"] is True
    assert result["ok"] is True
    assert result["structural_ready"] is True
