"""Figma v2 extraction: sections, layout, assets, tokens."""
from dashboard.backend.services.figma_service import (
    build_design_tokens,
    build_full_spec_tree,
    collect_asset_node_ids,
    extract_sections,
    slugify_name,
    tokens_to_css,
)
from dashboard.backend.services.figma_font_service import resolve_font_families


def _sample_root() -> dict:
    return {
        "id": "1:1",
        "name": "Page",
        "type": "FRAME",
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 2000},
        "children": [
            {
                "id": "1:2",
                "name": "Hero",
                "type": "FRAME",
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 400},
                "fills": [{"type": "SOLID", "color": {"r": 0.85, "g": 0.8, "b": 0.7}}],
                "children": [
                    {
                        "id": "1:3",
                        "name": "Headline",
                        "type": "TEXT",
                        "characters": "Hello",
                        "absoluteBoundingBox": {"x": 100, "y": 50, "width": 200, "height": 40},
                        "style": {"fontFamily": "Poppins", "fontSize": 32},
                    },
                    {
                        "id": "1:4",
                        "name": "Photo",
                        "type": "RECTANGLE",
                        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 400, "height": 300},
                        "fills": [{"type": "IMAGE", "visible": True}],
                    },
                ],
            },
            {
                "id": "1:5",
                "name": "Footer",
                "type": "FRAME",
                "absoluteBoundingBox": {"x": 0, "y": 1600, "width": 1920, "height": 200},
            },
        ],
    }


def test_full_node_includes_xy() -> None:
    tree, count = build_full_spec_tree(_sample_root(), max_nodes=50, max_depth=10)
    assert count >= 3
    hero = next(c for c in tree.get("children", []) if c.get("name") == "Hero")
    assert "x" in hero["box"]
    assert "y" in hero["box"]


def test_extract_sections_explicit_children() -> None:
    sections = extract_sections(_sample_root(), max_sections=10)
    assert len(sections) >= 2
    slugs = {s["slug"] for s in sections}
    assert "hero" in slugs or any("hero" in s for s in slugs)


def test_collect_asset_node_ids() -> None:
    assets = collect_asset_node_ids(_sample_root(), limit=10)
    assert any(a["asset_type"] == "IMAGE" for a in assets)


def test_build_design_tokens_and_css() -> None:
    sections = extract_sections(_sample_root())
    tokens = build_design_tokens(_sample_root(), sections)
    assert tokens["colors"]
    css = tokens_to_css(tokens)
    assert ":root" in css
    assert "--color-" in css


def test_slugify_name() -> None:
    assert slugify_name("Hero Section!") == "hero-section"


def test_resolve_font_families() -> None:
    result = resolve_font_families({"Poppins", "UnknownFont XYZ"})
    assert "Poppins" in result["resolved"]
    assert "UnknownFont XYZ" in result["unresolved"]
