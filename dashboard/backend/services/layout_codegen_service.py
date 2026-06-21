"""Generate skeleton CSS from Figma section boxes and semantic elements."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


def _safe_class_part(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "-", str(value or "el"))
    return cleaned.strip("-") or "el"


def _css_px(value: float) -> str:
    rounded = round(value, 1)
    if rounded == int(rounded):
        return f"{int(rounded)}px"
    return f"{rounded}px"


def _box_css(box: Dict[str, Any]) -> Dict[str, float]:
    return {
        "x": float(box.get("x") or 0),
        "y": float(box.get("y") or 0),
        "w": float(box.get("w") or 0),
        "h": float(box.get("h") or 0),
    }


def element_class_name(slug: str, element: Dict[str, Any]) -> str:
    node_id = _safe_class_part(str(element.get("node_id") or "").replace(":", "-"))
    role = _safe_class_part(str(element.get("role") or "element"))
    return f"{slug}__{role}--{node_id}"


def generate_section_layout_css(
    slug: str,
    *,
    section_box: Optional[Dict[str, Any]] = None,
    semantic_elements: Optional[List[Dict[str, Any]]] = None,
    assets: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Build absolute-position skeleton CSS for a section from Figma boxes."""
    section_box = section_box or {}
    semantic_elements = semantic_elements or []
    assets = assets or []
    sw = float(section_box.get("w") or 1920)
    sh = float(section_box.get("h") or 800)

    lines = [
        f"/* Skeleton layout: {slug} — generated from Figma boxes (section-relative coords) */",
        f'[data-section="{slug}"] {{',
        "  position: relative;",
                f"  width: min({_css_px(sw)}, 100%);",
                f"  min-height: {_css_px(sh)};",
        "  margin-inline: auto;",
        "  overflow: hidden;",
        "}",
        "",
    ]

    asset_by_node: Dict[str, Dict[str, Any]] = {}
    for asset in assets:
        node_id = str(asset.get("node_id") or "")
        if node_id:
            asset_by_node[node_id] = asset

    seen_classes: set[str] = set()
    for element in semantic_elements:
        cls = element_class_name(slug, element)
        if cls in seen_classes:
            continue
        seen_classes.add(cls)
        box = _box_css(element.get("box") or {})
        role = str(element.get("role") or "element")
        lines.extend(
            [
                f".{cls} {{",
                "  position: absolute;",
                f"  left: {_css_px(box['x'])};",
                f"  top: {_css_px(box['y'])};",
                f"  width: {_css_px(box['w'])};",
                f"  height: {_css_px(box['h'])};",
                "  box-sizing: border-box;",
                "}",
                "",
            ]
        )
        node_id = str(element.get("node_id") or "")
        asset = asset_by_node.get(node_id)
        if asset and asset.get("filename"):
            lines.append(
                f".{cls} img, .{cls} svg, .{cls} {{ "
                f"object-fit: contain; /* asset: assets/{asset['filename']} node_id={node_id} */ }}"
            )
            lines.append("")
        elif role in {"image", "icon"}:
            lines.append(f"/* {cls}: map to assets/ via node_id={node_id} */")
            lines.append("")

    for asset in assets:
        if str(asset.get("section_slug") or "") != slug:
            continue
        node_id = str(asset.get("node_id") or "")
        if not node_id or node_id in {str(e.get("node_id") or "") for e in semantic_elements}:
            continue
        box = _box_css(asset.get("box") or {})
        if box["w"] <= 0 and box["h"] <= 0:
            continue
        cls = f"{slug}__asset--{_safe_class_part(node_id.replace(':', '-'))}"
        if cls in seen_classes:
            continue
        seen_classes.add(cls)
        filename = asset.get("filename") or ""
        lines.extend(
            [
                f".{cls} {{",
                "  position: absolute;",
                f"  left: {_css_px(box['x'])};",
                f"  top: {_css_px(box['y'])};",
                f"  width: {_css_px(box['w'])};",
                f"  height: {_css_px(box['h'])};",
                f"  /* asset: assets/{filename} node_id={node_id} */",
                "}",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


layout_codegen_service = type(
    "LayoutCodegenService",
    (),
    {"generate_section_layout_css": staticmethod(generate_section_layout_css)},
)()
