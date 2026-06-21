"""Map Figma font families to loadable web fonts."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set

# Common Figma → Google Fonts mappings (family name case-insensitive)
_GOOGLE_FONT_MAP: Dict[str, str] = {
    "bebas neue": "Bebas+Neue",
    "poppins": "Poppins",
    "inter": "Inter",
    "roboto": "Roboto",
    "open sans": "Open+Sans",
    "lato": "Lato",
    "montserrat": "Montserrat",
    "playfair display": "Playfair+Display",
    "oswald": "Oswald",
    "raleway": "Raleway",
    "nunito": "Nunito",
    "work sans": "Work+Sans",
    "dm sans": "DM+Sans",
    "space grotesk": "Space+Grotesk",
    "source sans pro": "Source+Sans+Pro",
    "source sans 3": "Source+Sans+3",
    "merriweather": "Merriweather",
    "libre baskerville": "Libre+Baskerville",
    "fira sans": "Fira+Sans",
    "rubik": "Rubik",
    "karla": "Karla",
    "cabin": "Cabin",
    "pt sans": "PT+Sans",
    "ubuntu": "Ubuntu",
    "noto sans": "Noto+Sans",
}


def _normalize_family(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip())


def resolve_font_families(
    families: Set[str],
    *,
    require_all: bool = False,
) -> Dict[str, Any]:
    """
    Resolve Figma font family names to Google Fonts URLs where possible.
    Returns resolved map, unresolved list, and warnings.
    """
    resolved: Dict[str, Dict[str, str]] = {}
    unresolved: List[str] = []
    warnings: List[Dict[str, str]] = []

    for raw in sorted(families):
        family = _normalize_family(raw)
        if not family or family in {"?????", "?"}:
            unresolved.append(raw or "(unknown)")
            warnings.append(
                {
                    "severity": "warning",
                    "message": f"Font family could not be read from Figma: {raw!r}",
                }
            )
            continue
        key = family.lower()
        google_slug = _GOOGLE_FONT_MAP.get(key)
        if google_slug:
            resolved[family] = {
                "source": "google_fonts",
                "family": family,
                "url": f"https://fonts.googleapis.com/css2?family={google_slug}:wght@400;500;600;700&display=swap",
            }
        else:
            unresolved.append(family)
            warnings.append(
                {
                    "severity": "warning",
                    "message": f"No Google Fonts mapping for '{family}'; bundle or link manually.",
                }
            )

    if require_all and unresolved:
        warnings.append(
            {
                "severity": "blocking",
                "message": f"Unresolved fonts block import: {', '.join(unresolved)}",
            }
        )

    return {
        "resolved": resolved,
        "unresolved": unresolved,
        "warnings": warnings,
        "google_fonts_url": _build_combined_google_url(resolved),
    }


def _build_combined_google_url(resolved: Dict[str, Dict[str, str]]) -> Optional[str]:
    if not resolved:
        return None
    families = []
    for info in resolved.values():
        slug = info.get("url", "").split("family=")[-1].split("&")[0] if info.get("url") else None
        if slug:
            families.append(slug)
    if not families:
        return None
    return f"https://fonts.googleapis.com/css2?family={'&family='.join(families)}&display=swap"


def collect_font_families_from_tree(node: Optional[Dict[str, Any]], out: Optional[Set[str]] = None) -> Set[str]:
    """Walk a Figma node tree and collect fontFamily values from TEXT nodes."""
    if out is None:
        out = set()
    if not isinstance(node, dict):
        return out
    if node.get("type") == "TEXT":
        style = node.get("style") or {}
        family = style.get("fontFamily")
        if family:
            out.add(str(family))
        ps = style.get("postScriptName")
        if ps:
            out.add(str(ps).split("-")[0].replace(" ", " "))
    for child in node.get("children") or []:
        if isinstance(child, dict):
            collect_font_families_from_tree(child, out)
    return out
