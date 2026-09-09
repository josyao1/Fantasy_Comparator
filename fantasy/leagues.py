"""Per-league identity: a short code and a colour, used consistently.

Which league a threat lands in is the thing this board exists to answer, but
full names ("Sunday Money League '26 - East") are far too long to repeat on
every card. Each league therefore gets a chip: a short code plus a stable
colour, so a league can be recognised by colour alone once learned.
"""
from __future__ import annotations

import os
import re

# Chosen to stay clear of the board's semantic colours — orange means "against"
# and cyan means "for", so neither can double as a league identity.
PALETTE = ["#A78BFA", "#4ADE80", "#F472B6", "#60A5FA", "#CBD5E1",
           "#FCA5A5", "#67E8F9", "#FDE68A"]

_STOP = {"the", "league", "fantasy", "football", "ff", "of", "and"}


def _code(name: str) -> str:
    words = [w for w in re.split(r"[^A-Za-z0-9]+", name) if w]
    if not words:
        return "??"
    # A short name loses meaning if trimmed ("NU FF" -> "NU"), so keep it whole.
    joined = "".join(words)
    if len(joined) <= 5:
        return joined.upper()
    head = words[0]
    if head.lower() in _STOP and len(words) > 1:
        head = words[1]
    return head.upper()[:5]


def assign(names: list[str]) -> dict[str, dict]:
    """Map each league name to a stable code and colour.

    Codes collide often — two leagues can share a first word — so a colliding
    code is extended with the first distinguishing word of each name.
    """
    override = {}
    for pair in os.environ.get("LEAGUE_LABELS", "").split(","):
        if "=" in pair:
            k, _, v = pair.partition("=")
            override[k.strip()] = v.strip()

    codes: dict[str, str] = {}
    for name in names:
        codes[name] = _code(name)

    seen: dict[str, list[str]] = {}
    for name, code in codes.items():
        seen.setdefault(code, []).append(name)
    for code, group in seen.items():
        if len(group) < 2:
            continue
        for name in group:
            words = [w for w in re.split(r"[^A-Za-z0-9]+", name) if w]
            extra = next((w for w in words[1:] if w.lower() not in _STOP), None)
            if extra is None:
                extra = words[-1] if len(words) > 1 else "X"
            codes[name] = f"{code}·{extra[0].upper()}"

    return {
        name: {"code": override.get(name, codes[name]),
               "color": PALETTE[i % len(PALETTE)]}
        for i, name in enumerate(names)
    }
