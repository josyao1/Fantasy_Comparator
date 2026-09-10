"""Rest-of-season consensus rankings, used only to break ties.

Two players with identical exposure are otherwise ordered arbitrarily, which
makes the board feel unstable between runs. Ranking breaks that tie so the
more valuable player always sits higher within a section.

The file is a plain "Name|POS" list in rank order, so refreshing it is a
copy-paste rather than a code change. Unranked players sort last.
"""
from __future__ import annotations

from . import config
from .crosswalk import normalize_name

SOURCE = config.DATA / "rankings_ros.txt"
UNRANKED = 9999

_ranks: dict[tuple[str, str], int] | None = None


def _load() -> dict[tuple[str, str], int]:
    table: dict[tuple[str, str], int] = {}
    if not SOURCE.exists():
        return table
    rank = 0
    for line in SOURCE.read_text().splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        name, _, pos = line.partition("|")
        rank += 1
        table.setdefault((normalize_name(name), pos.strip().upper()), rank)
    return table


def rank_for(name: str, position: str) -> int:
    global _ranks
    if _ranks is None:
        _ranks = _load()
    return _ranks.get((normalize_name(name), (position or "").upper()), UNRANKED)


def label(rank: int) -> str:
    return "" if rank >= UNRANKED else f"#{rank}"
