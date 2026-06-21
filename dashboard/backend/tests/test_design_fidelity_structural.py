"""Structural design fidelity checks."""
from pathlib import Path

from dashboard.backend.services.design_fidelity_service import DesignFidelityService


def test_stock_photo_detection(tmp_path: Path) -> None:
    html = tmp_path / "index.html"
    html.write_text('<img src="https://images.unsplash.com/photo-123" />', encoding="utf-8")
    service = DesignFidelityService()
    result = service.check_stock_photos([html])
    assert result["ok"] is False
    assert result["hits"]


def test_asset_manifest_usage(tmp_path: Path) -> None:
    design = tmp_path / ".midnight" / "design"
    design.mkdir(parents=True)
    (design / "ASSET_MANIFEST.json").write_text(
        '{"assets":[{"node_id":"1:4","filename":"1-4.png"}]}',
        encoding="utf-8",
    )
    css = tmp_path / "style.css"
    css.write_text('background: url("assets/1-4.png")', encoding="utf-8")
    service = DesignFidelityService()
    result = service.check_asset_manifest_usage(str(tmp_path), [css])
    assert result["ok"] is True


def test_section_landmarks(tmp_path: Path) -> None:
    html = tmp_path / "index.html"
    html.write_text('<section data-section="hero"></section>', encoding="utf-8")
    service = DesignFidelityService()
    result = service.check_section_landmarks(
        str(tmp_path),
        [{"slug": "hero"}],
        [html],
    )
    assert result["ok"] is True
