"""Figma REST API: parse links, fetch nodes, build design specs (v1 compact + v2 fidelity)."""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import parse_qs, urlparse

import httpx

from ..config import app_config
from .figma_font_service import collect_font_families_from_tree, resolve_font_families

logger = logging.getLogger(__name__)

FIGMA_API = "https://api.figma.com/v1"
MAX_SPEC_CHARS = 12000
MAX_NODES = 96
MAX_TEXT_LEN = 200
MAX_EXPORT_FRAMES = 6
MAX_PREVIEW_CHARS = 1800

_FILE_KEY_RE = re.compile(
    r"(?:figma\.com/(?:design|file|proto)/|figma\.com/board/)([A-Za-z0-9]{10,128})",
    re.I,
)
_NODE_ID_PARAM_RE = re.compile(r"node-id=([\d]+-[\d]+)", re.I)
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def parse_figma_reference(value: str) -> Tuple[str, Optional[str]]:
    """Accept a Figma URL or raw file key. Returns (file_key, node_id with colon separator)."""
    raw = (value or "").strip()
    if not raw:
        raise ValueError("Figma URL or file key is required")

    node_id: Optional[str] = None
    file_key: Optional[str] = None

    if "figma.com" in raw.lower() or raw.startswith("http"):
        parsed = urlparse(raw if "://" in raw else f"https://{raw}")
        path_match = _FILE_KEY_RE.search(parsed.path) or _FILE_KEY_RE.search(raw)
        if not path_match:
            raise ValueError("Could not parse Figma file key from URL")
        file_key = path_match.group(1)
        qs = parse_qs(parsed.query)
        for key in ("node-id", "node_id"):
            if key in qs and qs[key]:
                node_id = qs[key][0].replace("-", ":")
                break
        if not node_id:
            param_match = _NODE_ID_PARAM_RE.search(raw)
            if param_match:
                node_id = param_match.group(1).replace("-", ":")
    else:
        if "/" in raw:
            parts = raw.split("/", 1)
            file_key = parts[0].strip()
            if parts[1].strip():
                node_id = parts[1].strip().replace("-", ":")
        else:
            file_key = raw

    if not file_key or len(file_key) < 10:
        raise ValueError("Invalid Figma file key")
    return file_key, node_id


def slugify_name(name: str, fallback: str = "section") -> str:
    slug = _SLUG_RE.sub("-", (name or "").lower()).strip("-")
    return slug[:64] or fallback


def _solid_fill_hex(fills: Any) -> Optional[str]:
    if not isinstance(fills, list):
        return None
    for fill in fills:
        if not isinstance(fill, dict) or fill.get("visible") is False:
            continue
        if fill.get("type") != "SOLID":
            continue
        color = fill.get("color") or {}
        r = int(round((color.get("r") or 0) * 255))
        g = int(round((color.get("g") or 0) * 255))
        b = int(round((color.get("b") or 0) * 255))
        a = color.get("a")
        if a is not None and a < 1:
            return f"rgba({r},{g},{b},{a:.2f})"
        return f"#{r:02x}{g:02x}{b:02x}"
    return None


def _gradient_summary(fills: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(fills, list):
        return None
    for fill in fills:
        if not isinstance(fill, dict) or fill.get("visible") is False:
            continue
        if fill.get("type") not in {"GRADIENT_LINEAR", "GRADIENT_RADIAL"}:
            continue
        stops = []
        for stop in fill.get("gradientStops") or []:
            if not isinstance(stop, dict):
                continue
            color = stop.get("color") or {}
            r = int(round((color.get("r") or 0) * 255))
            g = int(round((color.get("g") or 0) * 255))
            b = int(round((color.get("b") or 0) * 255))
            stops.append({"position": stop.get("position"), "color": f"#{r:02x}{g:02x}{b:02x}"})
        return {"type": fill.get("type"), "stops": stops}
    return None


def _effects_summary(node: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    effects = node.get("effects")
    if not isinstance(effects, list):
        return None
    out = []
    for eff in effects:
        if not isinstance(eff, dict) or eff.get("visible") is False:
            continue
        entry: Dict[str, Any] = {"type": eff.get("type")}
        if eff.get("radius") is not None:
            entry["radius"] = eff.get("radius")
        if eff.get("offset"):
            entry["offset"] = eff.get("offset")
        out.append(entry)
    return out or None


def _layout_summary(node: Dict[str, Any]) -> Dict[str, Any]:
    layout = {}
    for key in (
        "layoutMode",
        "primaryAxisAlignItems",
        "counterAxisAlignItems",
        "itemSpacing",
        "paddingLeft",
        "paddingRight",
        "paddingTop",
        "paddingBottom",
    ):
        if key in node and node[key] is not None:
            layout[key] = node[key]
    return layout


def _typography(node: Dict[str, Any], *, max_text_len: int = MAX_TEXT_LEN) -> Optional[Dict[str, Any]]:
    if node.get("type") != "TEXT":
        return None
    style = node.get("style") or {}
    out: Dict[str, Any] = {}
    for key in (
        "fontFamily",
        "fontSize",
        "fontWeight",
        "lineHeightPx",
        "letterSpacing",
        "textAlignHorizontal",
        "postScriptName",
    ):
        val = style.get(key)
        if val is not None:
            if key == "fontFamily":
                out[key] = str(val).encode("utf-8", errors="replace").decode("utf-8")
            else:
                out[key] = val
    return out or None


def _box_from_bbox(
    bbox: Dict[str, Any],
    origin_x: float = 0.0,
    origin_y: float = 0.0,
    *,
    relative: bool = True,
) -> Dict[str, float]:
    x = float(bbox.get("x") or 0)
    y = float(bbox.get("y") or 0)
    w = float(bbox.get("width") or 0)
    h = float(bbox.get("height") or 0)
    if relative:
        return {
            "x": round(x - origin_x, 1),
            "y": round(y - origin_y, 1),
            "w": round(w, 1),
            "h": round(h, 1),
        }
    return {"x": round(x, 1), "y": round(y, 1), "w": round(w, 1), "h": round(h, 1)}


def _compact_node(node: Dict[str, Any], depth: int, count: List[int]) -> Optional[Dict[str, Any]]:
    if count[0] >= MAX_NODES:
        return None
    count[0] += 1

    bbox = node.get("absoluteBoundingBox") or {}
    entry: Dict[str, Any] = {
        "id": node.get("id"),
        "name": node.get("name"),
        "type": node.get("type"),
    }
    if bbox:
        entry["box"] = {"w": round(bbox.get("width") or 0, 1), "h": round(bbox.get("height") or 0, 1)}
    fill = _solid_fill_hex(node.get("fills"))
    if fill:
        entry["fill"] = fill
    elif isinstance(node.get("fills"), list):
        for fill_item in node.get("fills") or []:
            if not isinstance(fill_item, dict) or fill_item.get("visible") is False:
                continue
            fill_type = fill_item.get("type")
            if fill_type in {"GRADIENT_LINEAR", "GRADIENT_RADIAL", "IMAGE"}:
                entry["fillType"] = fill_type
                break
    layout = _layout_summary(node)
    if layout:
        entry["layout"] = layout
    typo = _typography(node)
    if typo:
        entry["textStyle"] = typo
        chars = node.get("characters") or ""
        if chars:
            entry["text"] = chars[:MAX_TEXT_LEN] + ("…" if len(chars) > MAX_TEXT_LEN else "")

    children_out = []
    if depth > 0:
        for child in node.get("children") or []:
            if not isinstance(child, dict):
                continue
            child_entry = _compact_node(child, depth - 1, count)
            if child_entry:
                children_out.append(child_entry)
    if children_out:
        entry["children"] = children_out
    return entry


def _full_node(
    node: Dict[str, Any],
    depth: int,
    count: List[int],
    *,
    max_nodes: int,
    max_text_len: int,
    origin_x: float = 0.0,
    origin_y: float = 0.0,
) -> Optional[Dict[str, Any]]:
    if count[0] >= max_nodes:
        return None
    count[0] += 1

    bbox = node.get("absoluteBoundingBox") or {}
    entry: Dict[str, Any] = {
        "id": node.get("id"),
        "name": node.get("name"),
        "type": node.get("type"),
    }
    if bbox:
        entry["box"] = _box_from_bbox(bbox, origin_x, origin_y)

    fill = _solid_fill_hex(node.get("fills"))
    if fill:
        entry["fill"] = fill
    grad = _gradient_summary(node.get("fills"))
    if grad:
        entry["gradient"] = grad
    elif isinstance(node.get("fills"), list):
        for fill_item in node.get("fills") or []:
            if not isinstance(fill_item, dict) or fill_item.get("visible") is False:
                continue
            if fill_item.get("type") == "IMAGE":
                entry["fillType"] = "IMAGE"
                break

    if node.get("cornerRadius") is not None:
        entry["cornerRadius"] = node.get("cornerRadius")
    if node.get("strokeWeight") is not None:
        entry["strokeWeight"] = node.get("strokeWeight")
    effects = _effects_summary(node)
    if effects:
        entry["effects"] = effects

    layout = _layout_summary(node)
    if layout:
        entry["layout"] = layout
    typo = _typography(node, max_text_len=max_text_len)
    if typo:
        entry["textStyle"] = typo
        chars = node.get("characters") or ""
        if chars:
            entry["text"] = chars[:max_text_len] + ("…" if len(chars) > max_text_len else "")

    children_out = []
    if depth > 0:
        for child in node.get("children") or []:
            if not isinstance(child, dict):
                continue
            child_entry = _full_node(
                child,
                depth - 1,
                count,
                max_nodes=max_nodes,
                max_text_len=max_text_len,
                origin_x=origin_x,
                origin_y=origin_y,
            )
            if child_entry:
                children_out.append(child_entry)
    if children_out:
        entry["children"] = children_out
    return entry


def build_compact_spec(
    *,
    file_key: str,
    file_name: str,
    node_id: Optional[str],
    root_node: Dict[str, Any],
    styles: Optional[Dict[str, Any]] = None,
    components: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    count = [0]
    tree = _compact_node(root_node, depth=3, count=count)
    color_tokens = []
    if styles:
        for _sid, style in list(styles.items())[:12]:
            if not isinstance(style, dict):
                continue
            if style.get("styleType") == "FILL" and isinstance(style.get("description"), str):
                color_tokens.append(style.get("description"))
            elif style.get("styleType") == "TEXT":
                color_tokens.append(f"text:{style.get('name')}")

    component_names = []
    if components:
        for _cid, comp in list(components.items())[:20]:
            if isinstance(comp, dict) and comp.get("name"):
                component_names.append(comp["name"])

    return {
        "source": "figma_api",
        "file_key": file_key,
        "file_name": file_name,
        "node_id": node_id,
        "root_name": root_node.get("name"),
        "root_type": root_node.get("type"),
        "node_count": count[0],
        "tree": tree,
        "color_style_hints": color_tokens[:8],
        "component_names": component_names[:15],
    }


def build_full_spec_tree(
    root_node: Dict[str, Any],
    *,
    max_nodes: Optional[int] = None,
    max_depth: int = 20,
    max_text_len: Optional[int] = None,
) -> Tuple[Dict[str, Any], int]:
    """Build a full-fidelity tree for a section/frame."""
    limit = max_nodes or app_config.figma_max_section_nodes
    text_len = max_text_len or app_config.figma_max_text_len
    bbox = root_node.get("absoluteBoundingBox") or {}
    origin_x = float(bbox.get("x") or 0)
    origin_y = float(bbox.get("y") or 0)
    count = [0]
    tree = _full_node(
        root_node,
        max_depth,
        count,
        max_nodes=limit,
        max_text_len=text_len,
        origin_x=origin_x,
        origin_y=origin_y,
    )
    return tree or {}, count[0]


def _section_box(node: Dict[str, Any]) -> Dict[str, float]:
    bbox = node.get("absoluteBoundingBox") or {}
    return _box_from_bbox(bbox, relative=False)


def _is_spacing_helper(name: str) -> bool:
    lower = (name or "").lower()
    return "spacingbox" in lower or lower.startswith("spacing")


def extract_sections(
    root_node: Dict[str, Any],
    *,
    slice_height: Optional[int] = None,
    max_sections: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Split a Figma root into implementable sections.
    Uses explicit SECTION/FRAME children, or vertical slices for tall monolith frames.
    """
    max_sec = max_sections or app_config.figma_max_section_exports
    band_h = slice_height or app_config.figma_section_slice_height
    root_bbox = root_node.get("absoluteBoundingBox") or {}
    root_h = float(root_bbox.get("height") or 0)
    root_w = float(root_bbox.get("width") or 1920)
    root_x = float(root_bbox.get("x") or 0)
    root_y = float(root_bbox.get("y") or 0)

    explicit: List[Dict[str, Any]] = []
    for child in root_node.get("children") or []:
        if not isinstance(child, dict):
            continue
        if _is_spacing_helper(str(child.get("name") or "")):
            continue
        ctype = child.get("type")
        if ctype in {"SECTION", "FRAME", "COMPONENT", "INSTANCE"}:
            bbox = child.get("absoluteBoundingBox") or {}
            h = float(bbox.get("height") or 0)
            if h >= 80:
                explicit.append(child)

    sections: List[Dict[str, Any]] = []

    if len(explicit) >= 2:
        for idx, child in enumerate(explicit[:max_sec]):
            tree, node_count = build_full_spec_tree(child)
            name = str(child.get("name") or f"Section {idx + 1}")
            slug_base = slugify_name(name, f"section-{idx + 1}")
            sections.append(
                {
                    "slug": slug_base,
                    "name": name,
                    "node_id": child.get("id"),
                    "box": _section_box(child),
                    "node_count": node_count,
                    "tree": tree,
                    "source": "explicit_child",
                }
            )
    elif root_h > band_h * 1.2:
        # Auto-slice tall monolith frame into viewport-height bands
        y_cursor = root_y
        band_idx = 0
        while y_cursor < root_y + root_h - 1 and band_idx < max_sec:
            band_bottom = min(y_cursor + band_h, root_y + root_h)
            band_h_actual = band_bottom - y_cursor
            slug = f"band-{band_idx + 1}"
            name = f"Band {band_idx + 1} (y={int(y_cursor - root_y)})"
            # Filter children overlapping this vertical band
            band_children = _filter_nodes_in_band(root_node, y_cursor, band_bottom)
            synthetic = {
                "id": f"{root_node.get('id')}:band-{band_idx}",
                "name": name,
                "type": "FRAME",
                "absoluteBoundingBox": {
                    "x": root_x,
                    "y": y_cursor,
                    "width": root_w,
                    "height": band_h_actual,
                },
                "children": band_children,
            }
            tree, node_count = build_full_spec_tree(synthetic)
            sections.append(
                {
                    "slug": slug,
                    "name": name,
                    "node_id": synthetic["id"],
                    "box": {"x": 0, "y": round(y_cursor - root_y, 1), "w": root_w, "h": round(band_h_actual, 1)},
                    "node_count": node_count,
                    "tree": tree,
                    "source": "vertical_slice",
                }
            )
            y_cursor = band_bottom
            band_idx += 1
    else:
        tree, node_count = build_full_spec_tree(root_node)
        name = str(root_node.get("name") or "root")
        sections.append(
            {
                "slug": slugify_name(name, "root"),
                "name": name,
                "node_id": root_node.get("id"),
                "box": _section_box(root_node),
                "node_count": node_count,
                "tree": tree,
                "source": "root",
            }
        )

    for sec in sections:
        sec["manifest_text"] = _section_manifest_text(sec)
    return sections


def _filter_nodes_in_band(
    node: Dict[str, Any],
    y_top: float,
    y_bottom: float,
) -> List[Dict[str, Any]]:
    """Return shallow copies of children whose bounding box overlaps [y_top, y_bottom]."""
    out: List[Dict[str, Any]] = []
    for child in node.get("children") or []:
        if not isinstance(child, dict):
            continue
        if _is_spacing_helper(str(child.get("name") or "")):
            continue
        bbox = child.get("absoluteBoundingBox") or {}
        cy = float(bbox.get("y") or 0)
        ch = float(bbox.get("height") or 0)
        if cy + ch < y_top or cy > y_bottom:
            continue
        out.append(child)
    return out


def _section_manifest_text(section: Dict[str, Any]) -> str:
    lines = [
        f"## Section: {section.get('name')}",
        f"Slug: {section.get('slug')}",
        f"Node: {section.get('node_id')}",
        f"Box: {json.dumps(section.get('box') or {}, separators=(',', ':'))}",
        f"Nodes: {section.get('node_count')}",
        "",
        "Implement this section to match the staged PNG and JSON spec.",
        "Use assets from ASSET_MANIFEST.json only — no stock photo URLs.",
    ]
    return "\n".join(lines)


def collect_asset_node_ids(
    root: Dict[str, Any],
    *,
    limit: Optional[int] = None,
) -> List[Dict[str, str]]:
    """Collect IMAGE fill nodes and VECTOR nodes for asset export."""
    cap = limit or app_config.figma_max_assets
    found: List[Dict[str, str]] = []

    def walk(node: Dict[str, Any], section_hint: str = "") -> None:
        if len(found) >= cap:
            return
        nid = node.get("id")
        ntype = node.get("type")
        name = str(node.get("name") or "")

        if ntype == "VECTOR" and nid:
            found.append({"node_id": nid, "asset_type": "VECTOR", "name": name, "section_slug": section_hint})
        elif isinstance(node.get("fills"), list):
            for fill in node.get("fills") or []:
                if isinstance(fill, dict) and fill.get("type") == "IMAGE" and nid:
                    found.append(
                        {"node_id": nid, "asset_type": "IMAGE", "name": name, "section_slug": section_hint}
                    )
                    break

        for child in node.get("children") or []:
            if isinstance(child, dict):
                walk(child, section_hint)

    walk(root)
    return found[:cap]


def collect_section_export_ids(sections: List[Dict[str, Any]]) -> List[str]:
    """One PNG export per section (real node ids only)."""
    ids: List[str] = []
    for sec in sections:
        nid = sec.get("node_id")
        if not nid or ":band-" in str(nid):
            continue
        if nid not in ids:
            ids.append(nid)
    return ids[: app_config.figma_max_section_exports]


def build_design_tokens(
    root_node: Dict[str, Any],
    sections: List[Dict[str, Any]],
    styles: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Extract CSS-ready design tokens from the Figma tree."""
    colors: Dict[str, str] = {}
    typography: Dict[str, str] = {}
    spacing: Dict[str, str] = {}
    color_idx = 0
    typo_idx = 0
    space_idx = 0

    def walk(node: Dict[str, Any]) -> None:
        nonlocal color_idx, typo_idx, space_idx
        fill = _solid_fill_hex(node.get("fills"))
        if fill and fill not in colors.values():
            color_idx += 1
            colors[f"--color-{color_idx}"] = fill
        if node.get("type") == "TEXT":
            style = node.get("style") or {}
            family = style.get("fontFamily")
            size = style.get("fontSize")
            if family and f"--font-{slugify_name(str(family), 'font')}" not in typography:
                typography[f"--font-{slugify_name(str(family), 'font')}"] = str(family)
            if size and f"--text-size-{typo_idx + 1}" not in typography:
                typo_idx += 1
                typography[f"--text-size-{typo_idx}"] = f"{size}px"
        layout = _layout_summary(node)
        if layout.get("itemSpacing") and f"--spacing-{space_idx + 1}" not in spacing:
            space_idx += 1
            spacing[f"--spacing-{space_idx}"] = f"{layout['itemSpacing']}px"
        for child in node.get("children") or []:
            if isinstance(child, dict):
                walk(child)

    walk(root_node)
    if styles:
        for _sid, style in list(styles.items())[:20]:
            if isinstance(style, dict) and style.get("styleType") == "FILL":
                desc = style.get("description") or style.get("name")
                if desc and isinstance(desc, str) and desc.startswith("#"):
                    colors[f"--style-{slugify_name(str(style.get('name') or 'fill'), 'fill')}"] = desc

    return {"colors": colors, "typography": typography, "spacing": spacing}


def tokens_to_css(tokens: Dict[str, Any]) -> str:
    lines = [":root {"]
    for group in ("colors", "typography", "spacing"):
        for key, val in (tokens.get(group) or {}).items():
            lines.append(f"  {key}: {val};")
    lines.append("}")
    return "\n".join(lines)


def spec_to_agent_text(
    spec: Dict[str, Any],
    user_notes: Optional[str] = None,
    *,
    sections: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Human-readable spec for raw_text_content and previews."""
    lines = [
        f"Figma: {spec.get('file_name') or spec.get('file_key')}",
        f"Frame: {spec.get('root_name')} ({spec.get('root_type')})",
        f"Extraction: {spec.get('extraction_version') or 'v1'}",
    ]
    if spec.get("node_id"):
        lines.append(f"Node: {spec['node_id']}")
    if user_notes:
        lines.append(f"Notes: {user_notes.strip()}")
    if sections:
        lines.append(f"Sections ({len(sections)}):")
        for sec in sections:
            lines.append(f"  - {sec.get('slug')}: {sec.get('name')} ({sec.get('node_count')} nodes)")
    if spec.get("component_names"):
        lines.append("Components: " + ", ".join(spec["component_names"][:10]))
    tree_json = json.dumps(spec.get("tree") or {}, separators=(",", ":"))
    budget = MAX_SPEC_CHARS - len("\n".join(lines)) - 20
    if len(tree_json) > budget:
        tree_json = tree_json[:budget] + "…}"
    lines.append("Structure:")
    lines.append(tree_json)
    return "\n".join(lines)[:MAX_SPEC_CHARS]


def collect_export_node_ids(root: Dict[str, Any], limit: int = MAX_EXPORT_FRAMES) -> List[str]:
    """Legacy: prefer top-level FRAME / COMPONENT nodes for PNG export."""
    ids: List[str] = []
    root_type = root.get("type")
    root_id = root.get("id")
    if root_type in {"FRAME", "COMPONENT", "INSTANCE", "SECTION"} and root_id:
        ids.append(root_id)
    for child in root.get("children") or []:
        if len(ids) >= limit:
            break
        if not isinstance(child, dict):
            continue
        if child.get("type") in {"FRAME", "COMPONENT", "INSTANCE", "SECTION"} and child.get("id"):
            if child["id"] not in ids:
                ids.append(child["id"])
    return ids[:limit]


class FigmaService:
    def __init__(self, default_token: str = ""):
        self.default_token = default_token

    async def _figma_get(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        headers: dict,
        params: Optional[dict] = None,
        max_attempts: int = 8,
    ) -> httpx.Response:
        delay = 3.0
        response: Optional[httpx.Response] = None
        for attempt in range(max_attempts):
            response = await client.get(url, headers=headers, params=params)
            if response.status_code != 429:
                return response
            retry_after = response.headers.get("Retry-After")
            if retry_after and str(retry_after).replace(".", "", 1).isdigit():
                wait = min(float(retry_after), 120.0)
            else:
                wait = delay
            logger.warning(
                "Figma rate limit (429) on %s — retry %s/%s in %.1fs",
                url,
                attempt + 1,
                max_attempts,
                wait,
            )
            await asyncio.sleep(wait)
            delay = min(delay * 1.5, 120.0)
        if response is not None and response.status_code == 429:
            raise ValueError(
                "Figma API rate limit exceeded. Wait a few minutes and re-import, or reduce "
                "FIGMA_MAX_SECTION_EXPORTS / FIGMA_MAX_ASSETS."
            )
        return response  # type: ignore[return-value]

    def resolve_token(self, override: Optional[str] = None) -> str:
        token = (override or "").strip() or self.default_token.strip()
        if not token:
            raise ValueError(
                "Figma personal access token required. Add it in Settings or set FIGMA_ACCESS_TOKEN."
            )
        return token

    async def validate_token(self, token: str) -> Dict[str, Any]:
        headers = {"X-Figma-Token": token}
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(f"{FIGMA_API}/me", headers=headers)
            if r.status_code == 403:
                raise ValueError("Invalid or expired Figma token")
            r.raise_for_status()
            data = r.json()
            return {"ok": True, "email": data.get("email"), "handle": data.get("handle")}

    async def _get_file_meta(self, client: httpx.AsyncClient, headers: dict, file_key: str) -> Dict[str, Any]:
        r = await self._figma_get(
            client, f"{FIGMA_API}/files/{file_key}", headers=headers, params={"depth": 1}
        )
        if r.status_code == 403:
            raise ValueError("Figma token cannot access this file (check file permissions)")
        if r.status_code == 404:
            raise ValueError("Figma file not found")
        r.raise_for_status()
        return r.json()

    async def _get_nodes(
        self, client: httpx.AsyncClient, headers: dict, file_key: str, node_ids: str
    ) -> Dict[str, Any]:
        r = await self._figma_get(
            client,
            f"{FIGMA_API}/files/{file_key}/nodes",
            headers=headers,
            params={"ids": node_ids},
        )
        r.raise_for_status()
        return r.json()

    async def _export_images(
        self,
        client: httpx.AsyncClient,
        headers: dict,
        file_key: str,
        node_ids: List[str],
        *,
        fmt: str = "png",
        scale: float = 1,
    ) -> Dict[str, str]:
        if not node_ids:
            return {}
        # Figma API limits batch size
        result: Dict[str, str] = {}
        batch_size = 20
        for i in range(0, len(node_ids), batch_size):
            batch = node_ids[i : i + batch_size]
            r = await self._figma_get(
                client,
                f"{FIGMA_API}/images/{file_key}",
                headers=headers,
                params={"ids": ",".join(batch), "format": fmt, "scale": scale},
            )
            r.raise_for_status()
            images = (r.json() or {}).get("images") or {}
            for k, v in images.items():
                if v:
                    result[k] = v
            if i + batch_size < len(node_ids):
                await asyncio.sleep(1.0)
        return result

    async def _download_images(
        self, client: httpx.AsyncClient, image_urls: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        downloaded: List[Dict[str, Any]] = []
        for nid, url in image_urls.items():
            try:
                img_r = await client.get(url)
                img_r.raise_for_status()
                downloaded.append({"node_id": nid, "bytes": img_r.content, "size": len(img_r.content)})
            except Exception as e:
                logger.warning("figma image download failed node=%s: %s", nid, e)
        return downloaded

    async def fetch_design(
        self,
        reference: str,
        *,
        token: Optional[str] = None,
        user_notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fetch Figma file/node and return v2 fidelity spec + section PNGs + assets."""
        access = self.resolve_token(token)
        file_key, node_id = parse_figma_reference(reference)
        headers = {"X-Figma-Token": access}
        use_v2 = (app_config.figma_extraction_version or "v2").lower() == "v2"

        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            file_payload = await self._get_file_meta(client, headers, file_key)
            file_name = file_payload.get("name") or file_key
            styles = file_payload.get("styles")
            components = file_payload.get("components")

            root_node: Optional[Dict[str, Any]] = None
            if node_id:
                nodes_resp = await self._get_nodes(client, headers, file_key, node_id)
                nodes_map = nodes_resp.get("nodes") or {}
                entry = nodes_map.get(node_id) or {}
                doc = entry.get("document") if isinstance(entry, dict) else None
                if not doc:
                    raise ValueError(f"Node {node_id} not found in file")
                root_node = doc
            else:
                document = file_payload.get("document") or {}
                for page in document.get("children") or []:
                    if not isinstance(page, dict):
                        continue
                    kids = page.get("children") or []
                    if kids:
                        root_node = kids[0] if isinstance(kids[0], dict) else page
                        break
                if not root_node:
                    root_node = document

            warnings: List[Dict[str, str]] = []
            if not node_id:
                warnings.append(
                    {
                        "severity": "warning",
                        "message": (
                            "No node-id in Figma URL; imported the first frame on the first page. "
                            "Re-import with node-id= for accurate fidelity."
                        ),
                    }
                )
                if app_config.figma_require_node_id:
                    warnings.append(
                        {
                            "severity": "blocking",
                            "message": "node-id is required (FIGMA_REQUIRE_NODE_ID=true).",
                        }
                    )

            if not use_v2:
                return await self._fetch_design_v1(
                    client,
                    headers,
                    file_key,
                    file_name,
                    node_id,
                    reference,
                    root_node,
                    styles,
                    components,
                    user_notes,
                    warnings,
                )

            sections = extract_sections(root_node)
            full_tree, total_nodes = build_full_spec_tree(root_node)
            tokens = build_design_tokens(root_node, sections, styles)
            font_families = collect_font_families_from_tree(root_node)
            font_resolution = resolve_font_families(
                font_families,
                require_all=app_config.figma_require_resolved_fonts,
            )
            warnings.extend(font_resolution.get("warnings") or [])

            asset_candidates = collect_asset_node_ids(root_node)
            asset_node_ids = [a["node_id"] for a in asset_candidates]
            vector_ids = [a["node_id"] for a in asset_candidates if a["asset_type"] == "VECTOR"]
            image_ids = [a["node_id"] for a in asset_candidates if a["asset_type"] == "IMAGE"]

            section_export_ids = collect_section_export_ids(sections)
            if not section_export_ids and root_node.get("id"):
                section_export_ids = [root_node["id"]]

            all_export_ids = list(dict.fromkeys(section_export_ids + image_ids + vector_ids))
            png_urls = await self._export_images(client, headers, file_key, section_export_ids + image_ids)
            svg_urls = await self._export_images(
                client, headers, file_key, vector_ids, fmt="svg", scale=1
            ) if vector_ids else {}

            section_exports_raw = await self._download_images(
                client, {k: v for k, v in png_urls.items() if k in section_export_ids}
            )
            asset_exports_raw = await self._download_images(
                client,
                {
                    **{k: v for k, v in png_urls.items() if k in image_ids},
                    **svg_urls,
                },
            )

            if not asset_exports_raw and asset_node_ids:
                warnings.append(
                    {
                        "severity": "warning",
                        "message": f"Failed to export {len(asset_node_ids)} image/vector assets from Figma.",
                    }
                )

            spec = {
                "source": "figma_api",
                "extraction_version": "v2",
                "file_key": file_key,
                "file_name": file_name,
                "node_id": node_id,
                "root_name": root_node.get("name"),
                "root_type": root_node.get("type"),
                "node_count": total_nodes,
                "tree": full_tree,
                "sections_count": len(sections),
                "color_style_hints": list((tokens.get("colors") or {}).values())[:8],
                "component_names": [
                    comp.get("name")
                    for comp in (list((components or {}).values())[:20])
                    if isinstance(comp, dict) and comp.get("name")
                ][:15],
            }

            agent_text = spec_to_agent_text(spec, user_notes, sections=sections)
            preview = agent_text[:MAX_PREVIEW_CHARS]

            return {
                "file_key": file_key,
                "file_name": file_name,
                "node_id": node_id,
                "reference": reference.strip(),
                "spec": spec,
                "sections": sections,
                "tokens": tokens,
                "tokens_css": tokens_to_css(tokens),
                "font_resolution": font_resolution,
                "assets": asset_candidates,
                "section_exports": section_exports_raw,
                "asset_exports": asset_exports_raw,
                "agent_text": agent_text,
                "text_preview": preview,
                "user_notes": (user_notes or "").strip() or None,
                "export_images": section_exports_raw,
                "warnings": warnings,
                "extraction_version": "v2",
                "extraction_status": "figma_api_v2_ready",
            }

    async def _fetch_design_v1(
        self,
        client: httpx.AsyncClient,
        headers: dict,
        file_key: str,
        file_name: str,
        node_id: Optional[str],
        reference: str,
        root_node: Dict[str, Any],
        styles: Any,
        components: Any,
        user_notes: Optional[str],
        warnings: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        spec = build_compact_spec(
            file_key=file_key,
            file_name=file_name,
            node_id=node_id,
            root_node=root_node,
            styles=styles,
            components=components,
        )
        export_ids = collect_export_node_ids(root_node)
        image_urls = await self._export_images(client, headers, file_key, export_ids)
        downloaded = await self._download_images(client, image_urls)
        agent_text = spec_to_agent_text(spec, user_notes)
        preview = agent_text[:MAX_PREVIEW_CHARS]
        legacy_warnings = [w["message"] if isinstance(w, dict) else str(w) for w in warnings]
        return {
            "file_key": file_key,
            "file_name": file_name,
            "node_id": node_id,
            "reference": reference.strip(),
            "spec": spec,
            "sections": [],
            "tokens": {},
            "tokens_css": "",
            "font_resolution": {},
            "assets": [],
            "section_exports": downloaded,
            "asset_exports": [],
            "agent_text": agent_text,
            "text_preview": preview,
            "user_notes": (user_notes or "").strip() or None,
            "export_images": downloaded,
            "warnings": legacy_warnings,
            "extraction_version": "v1",
            "extraction_status": "figma_api_ready",
        }


def build_figma_rag_descriptor(
    *,
    file_key: str,
    file_name: str,
    node_id: Optional[str],
    reference: str,
    spec: Dict[str, Any],
    text_preview: str,
    user_notes: Optional[str],
    image_document_ids: List[int],
    sections: Optional[List[Dict[str, Any]]] = None,
    assets: Optional[List[Dict[str, Any]]] = None,
    tokens: Optional[Dict[str, Any]] = None,
    section_export_document_ids: Optional[List[int]] = None,
    asset_document_ids: Optional[List[int]] = None,
    extraction_warnings: Optional[List[Dict[str, str]]] = None,
    extraction_version: str = "v2",
    extraction_status: str = "figma_api_v2_ready",
    font_resolution: Optional[Dict[str, Any]] = None,
    import_source: str = "figma_api",
    tokens_css: Optional[str] = None,
    design_manifest_md: Optional[str] = None,
    sections_order: Optional[List[Dict[str, Any]]] = None,
) -> dict:
    section_entries = []
    if sections:
        ordered_sections = sorted(
            sections,
            key=lambda s: (
                int(s.get("order") or 999),
                float((s.get("box") or {}).get("y") or 0) if isinstance(s.get("box"), dict) else 0,
            ),
        )
        for sec in ordered_sections:
            section_entries.append(
                {
                    "slug": sec.get("slug"),
                    "name": sec.get("name"),
                    "node_id": sec.get("node_id"),
                    "order": sec.get("order"),
                    "position_y": sec.get("position_y"),
                    "section_role": sec.get("section_role"),
                    "section_role_confidence": sec.get("section_role_confidence"),
                    "semantic_elements": sec.get("semantic_elements") or [],
                    "box": sec.get("box"),
                    "node_count": sec.get("node_count"),
                    "manifest_text": sec.get("manifest_text"),
                    "tree": sec.get("tree"),
                    "tree_omitted": sec.get("tree_omitted"),
                    "layout_css": sec.get("layout_css"),
                    "section_export_document_id": sec.get("section_export_document_id"),
                }
            )

    asset_entries = assets or []
    source_label = "plugin" if import_source == "figma_plugin" else "v2"
    return {
        "rag_ready": True,
        "content_kind": "figma_import",
        "source": import_source,
        "figma": {
            "file_key": file_key,
            "file_name": file_name,
            "node_id": node_id,
            "url": reference if "figma.com" in reference else f"https://www.figma.com/design/{file_key}",
        },
        "agent_context": {
            "summary": (
                f"Figma design import ({source_label}): {file_name}"
                + (f" (node {node_id})" if node_id else "")
                + f". {len(section_entries)} sections, {len(asset_entries)} assets."
            ),
            "text_preview": text_preview[:MAX_PREVIEW_CHARS],
            "compact_spec": spec,
            "user_instructions": user_notes,
            "extraction_version": extraction_version,
            "extraction_status": extraction_status,
            "extraction_warnings": extraction_warnings or [],
            "sections": section_entries,
            "sections_order": sections_order or [],
            "assets": asset_entries,
            "tokens": tokens or {},
            "tokens_css": tokens_css,
            "design_manifest_md": design_manifest_md,
            "font_resolution": font_resolution or {},
            "image_document_ids": image_document_ids,
            "section_export_document_ids": section_export_document_ids or [],
            "asset_document_ids": asset_document_ids or [],
            "recommended_processing": [
                "Read sections-order.json for top-to-bottom section sequence and inferred roles (navbar, hero, carousel, etc.).",
                "Read DESIGN_MANIFEST.md and section JSON semantic_elements before UI work.",
                "Position elements using semantic_elements[].box (section-relative x,y,w,h) and sections/{slug}.layout.css skeleton.",
                "Map IMAGE/VECTOR nodes to assets/ files by node_id from ASSET_MANIFEST.json — stock photo URLs are forbidden.",
                "Use sections/{slug}.png for visual verification only, not primary layout inference.",
                "Apply tokens.css variables for colors, typography, and spacing.",
            ],
        },
        "retrieval": {
            "namespace": "project_document",
            "modalities": ["text", "visual_reference"],
            "keywords": [file_name, file_key, "figma", "design", "section"],
        },
    }
