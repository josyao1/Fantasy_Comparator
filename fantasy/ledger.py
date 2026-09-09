"""Aggregate per-player stake across every scanned league.

All three highlight tiers derive from one structure: for each player, which
leagues you start him in and which leagues your opponent starts him in.
"""
from __future__ import annotations

from datetime import datetime

from .models import Exposure, LeagueMatchup
from . import config


def build(matchups: list[LeagueMatchup], kickoffs: dict[str, datetime],
          now: datetime) -> dict[str, Exposure]:
    """Collapse every league's lineups into one exposure table keyed by player."""
    table: dict[str, Exposure] = {}

    def touch(player, league_name: str, side: str) -> None:
        if player.position not in config.SKILL_POSITIONS:
            return
        exp = table.get(player.key)
        if exp is None:
            kickoff = kickoffs.get(player.team)
            exp = Exposure(
                player=player,
                kickoff=kickoff,
                locked=bool(kickoff and now >= kickoff),
            )
            table[player.key] = exp
        target = exp.for_leagues if side == "for" else exp.against_leagues
        if league_name not in target:
            target.append(league_name)

    for m in matchups:
        if m.error:
            continue
        for p in m.my_starters:
            touch(p, m.league_name, "for")
        for p in m.opp_starters:
            touch(p, m.league_name, "against")
    return table


def conflicts(table: dict[str, Exposure]) -> list[Exposure]:
    """Players you start AND face — sorted by how badly you're underwater."""
    # A wash is the least actionable row on the board, so lopsided stakes
    # sort first (most underwater leading), and even ones trail.
    return sorted(
        (e for e in table.values() if e.is_conflict),
        key=lambda e: (e.net == 0, e.net, -len(e.against_leagues)),
    )


def multi_exposure(table: dict[str, Exposure]) -> list[Exposure]:
    """Players facing you in 2+ leagues at once, excluding ones already flagged."""
    return sorted(
        (e for e in table.values() if e.is_multi and not e.is_conflict),
        key=lambda e: (-len(e.against_leagues), e.player.name),
    )


def single_exposure(table: dict[str, Exposure]) -> list[Exposure]:
    return sorted(
        (e for e in table.values()
         if len(e.against_leagues) == 1 and not e.is_conflict),
        key=lambda e: (e.against_leagues[0], e.player.position, e.player.name),
    )
