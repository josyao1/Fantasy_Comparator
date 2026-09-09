"""Canonical player identity across ESPN and Sleeper.

Sleeper's `espn_id` field covers only ~36% of startable skill players (Bijan
Robinson, Ja'Marr Chase and Puka Nacua all lack it), so a direct ID join is not
viable. Instead players are keyed on normalized (name, position, team), which
was measured to produce zero collisions across the startable universe.

Because this is name-based, unresolved players are surfaced loudly rather than
dropped — a silently missing player would corrupt the own-vs-face analysis.
"""
from __future__ import annotations

import re
import unicodedata

# ESPN and Sleeper disagree on two abbreviations; unnormalized, every
# Washington player would key as two distinct people.
TEAM_ALIASES = {
    "WSH": "WAS",
    "OAK": "LV",
    "JAC": "JAX",
    "LA": "LAR",
    "SD": "LAC",
    "STL": "LAR",
}

_SUFFIXES = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")
_NONALPHA = re.compile(r"[^a-z ]")
_SPACES = re.compile(r"\s+")


def normalize_team(team: str | None) -> str:
    if not team:
        return "FA"
    t = team.strip().upper()
    return TEAM_ALIASES.get(t, t)


def normalize_name(name: str | None) -> str:
    """Fold accents, strip generational suffixes and punctuation, lowercase."""
    if not name:
        return ""
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    n = n.lower()
    n = _SUFFIXES.sub("", n)
    n = _NONALPHA.sub("", n)
    return _SPACES.sub(" ", n).strip()


def player_key(name: str | None, position: str | None, team: str | None) -> str:
    """Stable cross-platform identity for one player."""
    return f"{normalize_name(name)}|{(position or '').upper()}|{normalize_team(team)}"
