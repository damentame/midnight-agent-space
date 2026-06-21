"""Design pack zip import from Figma plugin."""
import io
import json
import zipfile
from unittest.mock import AsyncMock, MagicMock

import pytest

from dashboard.backend.services.design_pack_service import (
    css_to_tokens,
    import_design_pack,
    parse_design_pack,
)


def _build_pack() -> bytes:
    buf = io.BytesIO()
    png = b"\x89PNG\r\n\x1a\n"
    section_json = {
        "slug": "main",
        "name": "Hero",
        "node_id": "879:474",
        "box": {"x": 0, "y": 0, "w": 100, "h": 200},
        "node_count": 12,
        "manifest_text": "FRAME:Hero",
    }
    meta = {
        "file_name": "Morning Glory",
        "root_node_id": "879:474",
        "extraction_version": "plugin-v1",
        "warnings": [],
    }
    manifest = {
        "sections": [{"slug": "main", "png": "sections/main.png", "json": "sections/main.json"}],
        "assets": [
            {
                "filename": "main-icon.svg",
                "path": "assets/main-icon.svg",
                "section_slug": "main",
                "asset_type": "VECTOR",
                "node_id": "1:2",
            }
        ],
    }
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("mas-export.meta.json", json.dumps(meta))
        zf.writestr("sections/main.json", json.dumps(section_json))
        zf.writestr("sections/main.png", png)
        zf.writestr("assets/main-icon.svg", b"<svg></svg>")
        zf.writestr("ASSET_MANIFEST.json", json.dumps(manifest))
        zf.writestr("tokens.css", ":root {\n  --color-1: #112233;\n}")
        zf.writestr("design-spec.md", "# Design spec")
    return buf.getvalue()


def test_css_to_tokens_parses_colors() -> None:
    tokens = css_to_tokens(":root {\n  --color-1: #AABBCC;\n}")
    assert tokens["colors"]["--color-1"] == "#AABBCC"


def test_parse_design_pack_finds_sections() -> None:
    files, meta, warnings = parse_design_pack(_build_pack())
    assert meta["file_name"] == "Morning Glory"
    assert "sections/main.png" in files
    assert not warnings or isinstance(warnings, list)


@pytest.mark.asyncio
async def test_import_design_pack_persists_documents() -> None:
    db = MagicMock()
    db.get_project_by_id = AsyncMock(return_value={"project_id": 5})
    db.deactivate_figma_import_family = AsyncMock(return_value=1)
    db.insert_document_upload = AsyncMock(
        side_effect=[
            {"document_id": 100},
            {"document_id": 101},
            {"document_id": 102},
        ]
    )
    db.execute = AsyncMock()
    db.fetch_one = AsyncMock(return_value={"metadata": {}})
    db.fetch_many = AsyncMock(return_value=[])

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "dashboard.backend.services.design_pack_service.document_version_service.create_version",
            AsyncMock(),
        )
        mp.setattr(
            "dashboard.backend.services.design_pack_service.project_metadata_service.get_project_metadata",
            AsyncMock(return_value={"metadata": {}}),
        )
        mp.setattr(
            "dashboard.backend.services.design_pack_service.project_metadata_service.update_project_metadata",
            AsyncMock(),
        )
        result = await import_design_pack(
            db,
            project_id=5,
            zip_bytes=_build_pack(),
            pack_filename="mas-test.zip",
        )

    assert result["ok"] is True
    assert result["document_id"] == 100
    assert len(result["sections"]) == 1
    assert result["sections"][0]["slug"] == "main"
    assert result["asset_document_ids"] == [102]
    assert db.insert_document_upload.await_count == 3
