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
NAMES_CACHE = config.DATA / "espn_league_names.json"

POSITIONS = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DST"}
BENCH_SLOTS = {20, 21}


def _names() -> dict:
    if NAMES_CACHE.exists():
        try:
            return json.loads(NAMES_CACHE.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def _remember_name(league_id: str, name: str) -> None:
    """Keep the last known league name so auth failures stay readable."""
    known = _names()
    if known.get(league_id) == name:
        return
    known[league_id] = name
    config.DATA.mkdir(parents=True, exist_ok=True)
    NAMES_CACHE.write_text(json.dumps(known, indent=2, sort_keys=True))


def _proteams() -> dict[int, str]:
    if PROTEAMS_CACHE.exists():
        return {int(k): v for k, v in json.loads(PROTEAMS_CACHE.read_text()).items()}
    r = requests.get(f"{BASE}/{config.SEASON}", params={"view": "proTeamSchedules_wl"}, timeout=25)
    r.raise_for_status()
    table = {t["id"]: t["abbrev"].upper() for t in r.json()["settings"]["proTeams"] if t.get("abbrev")}
    config.DATA.mkdir(parents=True, exist_ok=True)
    PROTEAMS_CACHE.write_text(json.dumps(table, indent=2))
    return table


def fetch(spec: str, week: int, season: str, priority: int) -> LeagueMatchup:
    """`spec` is "leagueId", "leagueId:teamId", or "leagueId:teamId:Display Name".

    Public leagues read without cookies, so auth is attempted opportunistically
    rather than demanded up front. An explicit teamId identifies your team
    without SWID, which also makes the lookup deterministic.

    A display name given here survives a failed fetch, so an expired-cookie
    alert can name the league instead of printing a bare numeric id. It lives
    in the secret rather than a tracked cache so the repo can stay public
    without publishing which leagues you play in.
    """
    parts = spec.split(":")
    league_id = parts[0]
    team_hint = parts[1] if len(parts) > 1 else ""
    given_name = ":".join(parts[2:]).strip() if len(parts) > 2 else ""
    matchup = LeagueMatchup(
        platform="espn",
        league_id=league_id,
        league_name=given_name or _names().get(league_id, f"ESPN {league_id}"),
        priority=priority,
        my_team="",
        opp_team="",
    )

    cookies = {}
    if config.ESPN_S2 and config.SWID:
        cookies = {"espn_s2": config.ESPN_S2, "SWID": config.SWID}

    r = requests.get(
        f"{BASE}/{season}/segments/0/leagues/{league_id}",
        params=[("view", "mTeam"), ("view", "mRoster"), ("view", "mMatchup"),
                ("view", "mSettings"), ("scoringPeriodId", week)],
        cookies=cookies,
        timeout=30,
    )
    if r.status_code in (401, 403):
        matchup.error = ("private league — set ESPN_S2 and SWID" if not cookies
                         else "ESPN sign-in expired — refresh espn_s2 and SWID")
        return matchup
    r.raise_for_status()
    data = r.json()

    name = (data.get("settings") or {}).get("name")
    if name:
        matchup.league_name = given_name or name
        _remember_name(league_id, name)
    teams = {t["id"]: t for t in data.get("teams", [])}
    proteams = _proteams()

    def team_name(tid: int) -> str:
        t = teams.get(tid) or {}
        return t.get("name") or f"{t.get('location','')} {t.get('nickname','')}".strip() or f"Team {tid}"

    my_id = None
    if team_hint.isdigit():
        my_id = int(team_hint)
        if my_id not in teams:
            matchup.error = f"teamId {my_id} not in this league"
            return matchup
    elif config.SWID:
        swid = config.SWID if config.SWID.startswith("{") else "{%s}" % config.SWID
        my_id = next(
            (t["id"] for t in data.get("teams", [])
             if any(o.upper() == swid.upper() for o in (t.get("owners") or []))),
            None,
        )
    if my_id is None:
        matchup.error = "cannot identify your team — add ':teamId' to the league id"
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
