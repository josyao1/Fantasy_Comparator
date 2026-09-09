"""Player headshots and team colours for the broadcast board.

Sleeper's CDN carries a portrait for every skill player we surface, including
the ones ESPN has no id for, so it is the single source rather than falling
back between two providers.
"""
from __future__ import annotations

import json

from . import config
from .adapters.sleeper import load_players
from .crosswalk import normalize_name

CDN = "https://sleepercdn.com/content/nfl/players/thumb/{pid}.jpg"
COLORS = config.DATA / "team_colors.json"

_index: dict[tuple[str, str], str] | None = None
_colors: dict | None = None


def _build_index() -> dict[tuple[str, str], str]:
    idx: dict[tuple[str, str], str] = {}
    for pid, p in load_players().items():
        name = p.get("full_name")
        pos = (p.get("position") or "").upper()
        if name and pos in config.SKILL_POSITIONS:
            idx.setdefault((normalize_name(name), pos), pid)
    return idx


def url_for(name: str, position: str) -> str | None:
    global _index
    if _index is None:
        _index = _build_index()
    pid = _index.get((normalize_name(name), (position or "").upper()))
    return CDN.format(pid=pid) if pid else None


def _luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def rail_color(team: str) -> str:
    """Team colour for the card rail, swapped when the primary is too dark.

    Several teams use black as their primary, which is invisible against the
    broadcast ground; those fall through to the alternate.
    """
    global _colors
    if _colors is None:
        _colors = json.loads(COLORS.read_text()) if COLORS.exists() else {}
    entry = _colors.get((team or "").upper())
    if not entry:
        return "#FFB020"
    primary = entry.get("c", "#FFB020")
    if _luminance(primary) < 0.06:
        alt = entry.get("alt")
        if alt and _luminance(alt) >= 0.06:
            return alt
        return "#FFB020"
    return primary
