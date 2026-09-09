"""Sleeper league adapter. Public REST API — no authentication required."""
from __future__ import annotations

import json
import time

import requests

from .. import config
from ..models import LeagueMatchup, Player

BASE = "https://api.sleeper.app/v1"
PLAYERS_CACHE = config.DATA / "sleeper_players.json"
PLAYERS_TTL = 24 * 3600


def _get(path: str):
    r = requests.get(f"{BASE}{path}", timeout=30)
    r.raise_for_status()
    return r.json()


def load_players() -> dict:
    """Sleeper's full player table (~14MB). Cached daily; it changes slowly."""
    if PLAYERS_CACHE.exists() and time.time() - PLAYERS_CACHE.stat().st_mtime < PLAYERS_TTL:
        return json.loads(PLAYERS_CACHE.read_text())
    data = _get("/players/nfl")
    config.DATA.mkdir(parents=True, exist_ok=True)
    PLAYERS_CACHE.write_text(json.dumps(data))
    return data


def _to_player(pid: str, players: dict) -> Player | None:
    p = players.get(str(pid))
    if not p:
        return None
    name = p.get("full_name") or " ".join(
        x for x in (p.get("first_name"), p.get("last_name")) if x
    )
    return Player(
        name=name,
        position=(p.get("position") or "").upper(),
        team=(p.get("team") or "FA"),
    )


def fetch(league_id: str, week: int, user_id: str, priority: int) -> LeagueMatchup:
    """Build this week's head-to-head for one Sleeper league."""
    players = load_players()
    league = _get(f"/league/{league_id}")
    matchup = LeagueMatchup(
        platform="sleeper",
        league_id=league_id,
        league_name=league.get("name", league_id),
        priority=priority,
        my_team="",
        opp_team="",
    )

    rosters = _get(f"/league/{league_id}/rosters")
    mine = next((r for r in rosters if r.get("owner_id") == user_id), None)
    if mine is None:
        matchup.error = f"no roster owned by user {user_id}"
        return matchup

    users = {u["user_id"]: u for u in _get(f"/league/{league_id}/users")}

    def team_name(roster) -> str:
        u = users.get(roster.get("owner_id")) or {}
        meta = u.get("metadata") or {}
        return meta.get("team_name") or u.get("display_name") or f"Roster {roster['roster_id']}"

    matchup.my_team = team_name(mine)

    rows = _get(f"/league/{league_id}/matchups/{week}")
    my_row = next((m for m in rows if m["roster_id"] == mine["roster_id"]), None)
    if my_row is None or my_row.get("matchup_id") is None:
        matchup.error = f"week {week} matchup not posted yet"
        return matchup

    opp_row = next(
        (m for m in rows
         if m.get("matchup_id") == my_row["matchup_id"] and m["roster_id"] != mine["roster_id"]),
        None,
    )

    def starters(row) -> list[Player]:
        out = []
        for pid in row.get("starters") or []:
            if not pid or pid == "0":
                continue
            player = _to_player(pid, players)
            if player:
                out.append(player)
        return out

    matchup.my_starters = starters(my_row)
    if opp_row is None:
        matchup.error = "opponent not found (bye week?)"
        return matchup

    opp_roster = next((r for r in rosters if r["roster_id"] == opp_row["roster_id"]), None)
    matchup.opp_team = team_name(opp_roster) if opp_roster else "Opponent"
    matchup.opp_starters = starters(opp_row)
    return matchup
