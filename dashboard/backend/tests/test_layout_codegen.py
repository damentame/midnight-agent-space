"""Tests for layout skeleton CSS generation."""
from dashboard.backend.services.layout_codegen_service import (
    element_class_name,
    generate_section_layout_css,
)


def test_generate_section_layout_css_positions_elements() -> None:
    css = generate_section_layout_css(
        "hero",
        section_box={"w": 1920, "h": 800},
        semantic_elements=[
            {
                "node_id": "1864:18569",
                "role": "heading",
                "box": {"x": 100, "y": 50, "w": 400, "h": 120},
            }
        ],
        assets=[],
    )
    assert '[data-section="hero"]' in css
    assert "position: absolute" in css
    assert "left: 100px" in css
    assert "top: 50px" in css
    assert element_class_name("hero", {"node_id": "1864:18569", "role": "heading"}) in css


def test_generate_section_layout_css_includes_asset_box() -> None:
    css = generate_section_layout_css(
        "navbar",
        section_box={"w": 1920, "h": 104},
        semantic_elements=[],
        assets=[
            {
                "node_id": "1:2",
                "filename": "navbar-icon.svg",
                "section_slug": "navbar",
                "box": {"x": 10, "y": 20, "w": 34, "h": 34},
            }
        ],
    )
    assert "navbar__asset--1-2" in css
    assert "assets/navbar-icon.svg" in css
