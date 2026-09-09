"""ESPN fantasy league adapter.

Private leagues require the espn_s2 and SWID cookies from a logged-in browser
session. Those expire every few months, so auth failures are reported as an
explicit error on the matchup rather than yielding an empty lineup that would
quietly understate your exposure.
"""
from __future__ import annotations

import json

import requests

from .. import config
from ..models import LeagueMatchup, Player

BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons"
PROTEAMS_CACHE = config.DATA / "espn_proteams.json"

POSITIONS = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DST"}
BENCH_SLOTS = {20, 21}


class ESPNAuthError(RuntimeError):
    pass


def _proteams() -> dict[int, str]:
    if PROTEAMS_CACHE.exists():
        return {int(k): v for k, v in json.loads(PROTEAMS_CACHE.read_text()).items()}
    r = requests.get(f"{BASE}/{config.SEASON}", params={"view": "proTeamSchedules_wl"}, timeout=25)
    r.raise_for_status()
    table = {t["id"]: t["abbrev"].upper() for t in r.json()["settings"]["proTeams"] if t.get("abbrev")}
    config.DATA.mkdir(parents=True, exist_ok=True)
    PROTEAMS_CACHE.write_text(json.dumps(table, indent=2))
    return table


def fetch(league_id: str, week: int, season: str, priority: int) -> LeagueMatchup:
    matchup = LeagueMatchup(
        platform="espn",
        league_id=league_id,
        league_name=f"ESPN {league_id}",
        priority=priority,
        my_team="",
        opp_team="",
    )
    if not (config.ESPN_S2 and config.SWID):
        matchup.error = "ESPN_S2 / SWID not configured"
        return matchup

    r = requests.get(
        f"{BASE}/{season}/segments/0/leagues/{league_id}",
        params=[("view", "mTeam"), ("view", "mRoster"), ("view", "mMatchup"),
                ("scoringPeriodId", week)],
        cookies={"espn_s2": config.ESPN_S2, "SWID": config.SWID},
        timeout=30,
    )
    if r.status_code in (401, 403):
        matchup.error = "ESPN auth rejected — espn_s2/SWID expired"
        return matchup
    r.raise_for_status()
    data = r.json()

    matchup.league_name = (data.get("settings") or {}).get("name") or f"ESPN {league_id}"
    teams = {t["id"]: t for t in data.get("teams", [])}
    proteams = _proteams()

    def team_name(tid: int) -> str:
        t = teams.get(tid) or {}
        return t.get("name") or f"{t.get('location','')} {t.get('nickname','')}".strip() or f"Team {tid}"

    swid = config.SWID if config.SWID.startswith("{") else "{%s}" % config.SWID
    my_id = next(
        (t["id"] for t in data.get("teams", [])
         if any(o.upper() == swid.upper() for o in (t.get("owners") or []))),
        None,
    )
    if my_id is None:
        matchup.error = "could not identify your team from SWID"
        return matchup
    matchup.my_team = team_name(my_id)

    game = next(
        (m for m in data.get("schedule", [])
         if m.get("matchupPeriodId") == week
         and my_id in ((m.get("home") or {}).get("teamId"), (m.get("away") or {}).get("teamId"))),
        None,
    )
    if game is None:
        matchup.error = f"week {week} matchup not found"
        return matchup

    home, away = game.get("home") or {}, game.get("away") or {}
    opp_id = away.get("teamId") if home.get("teamId") == my_id else home.get("teamId")
    matchup.opp_team = team_name(opp_id) if opp_id else "Opponent"

    def starters(tid: int) -> list[Player]:
        team = teams.get(tid) or {}
        entries = ((team.get("roster") or {}).get("entries")) or []
        out = []
        for e in entries:
            if e.get("lineupSlotId") in BENCH_SLOTS:
                continue
            p = (e.get("playerPoolEntry") or {}).get("player") or {}
            if not p:
                continue
            out.append(Player(
                name=p.get("fullName", "?"),
                position=POSITIONS.get(p.get("defaultPositionId"), "?"),
                team=proteams.get(p.get("proTeamId"), "FA"),
            ))
        return out

    matchup.my_starters = starters(my_id)
    if opp_id:
        matchup.opp_starters = starters(opp_id)
    return matchup
