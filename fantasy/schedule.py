"""NFL schedule scraping and kickoff-wave computation.

Game days are never hardcoded. The season schedule is scraped from ESPN's
public scoreboard API and cached to disk, so Wednesday openers, Thanksgiving,
Black Friday, Saturday Week 15-18 games and 9:30am London kickoffs are all
handled without a code change.

The cache is refreshed on a TTL because the NFL flexes game times mid-season;
a stale cache would fire alerts at the wrong hour.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

from . import config

ET = ZoneInfo("America/New_York")
SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
STATE_URL = "https://api.sleeper.app/v1/state/nfl"
CACHE = config.DATA / "schedule.json"
CACHE_TTL_SECONDS = 6 * 3600
REGULAR_SEASON_WEEKS = 18


@dataclass(frozen=True)
class Game:
    kickoff: str          # ISO-8601 UTC
    away: str             # team abbreviation
    home: str
    short_name: str

    @property
    def kickoff_dt(self) -> datetime:
        return datetime.fromisoformat(self.kickoff)

    @property
    def teams(self) -> tuple[str, str]:
        return (self.away, self.home)


@dataclass(frozen=True)
class Wave:
    """All games sharing one kickoff timestamp — e.g. the Sunday 1:00pm slate."""
    kickoff: str
    games: tuple[Game, ...]

    @property
    def kickoff_dt(self) -> datetime:
        return datetime.fromisoformat(self.kickoff)

    @property
    def key(self) -> str:
        """Stable dedup identifier, e.g. '2026-09-13T17:00+0000'."""
        return self.kickoff_dt.strftime("%Y-%m-%dT%H:%M%z")

    @property
    def label(self) -> str:
        local = self.kickoff_dt.astimezone(ET)
        return f"{local:%a} {local:%-I:%M%p}".replace("AM", "am").replace("PM", "pm")

    def fire_at(self, lead_minutes: int) -> datetime:
        return self.kickoff_dt - timedelta(minutes=lead_minutes)


def current_week() -> tuple[int, str]:
    """Ask Sleeper what NFL week it is — it tracks the fantasy-relevant week."""
    r = requests.get(STATE_URL, timeout=20)
    r.raise_for_status()
    state = r.json()
    return int(state["week"]), str(state["season"])


def _fetch_week(season: str, week: int) -> list[Game]:
    r = requests.get(
        SCOREBOARD,
        params={"dates": season, "seasontype": 2, "week": week},
        timeout=25,
    )
    r.raise_for_status()
    games = []
    for event in r.json().get("events", []):
        competitors = event.get("competitions", [{}])[0].get("competitors", [])
        away = home = "?"
        for c in competitors:
            abbr = c.get("team", {}).get("abbreviation", "?")
            if c.get("homeAway") == "home":
                home = abbr
            else:
                away = abbr
        kickoff = datetime.strptime(event["date"], "%Y-%m-%dT%H:%MZ").replace(
            tzinfo=timezone.utc
        )
        games.append(
            Game(
                kickoff=kickoff.isoformat(),
                away=away,
                home=home,
                short_name=event.get("shortName", f"{away} @ {home}"),
            )
        )
    return games


def load_schedule(season: str, force: bool = False) -> dict[int, list[Game]]:
    """Full regular-season schedule, cached on disk with a TTL."""
    if not force and CACHE.exists():
        age = time.time() - CACHE.stat().st_mtime
        cached = json.loads(CACHE.read_text())
        if age < CACHE_TTL_SECONDS and cached.get("season") == season:
            return {
                int(w): [Game(**g) for g in games]
                for w, games in cached["weeks"].items()
            }

    weeks: dict[int, list[Game]] = {}
    for week in range(1, REGULAR_SEASON_WEEKS + 1):
        weeks[week] = _fetch_week(season, week)

    config.DATA.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(
        json.dumps(
            {
                "season": season,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "weeks": {str(w): [asdict(g) for g in gs] for w, gs in weeks.items()},
            },
            indent=2,
        )
    )
    return weeks


def waves_for_week(season: str, week: int, force: bool = False) -> list[Wave]:
    """Distinct kickoff times in a week, each with its games, in time order."""
    games = load_schedule(season, force=force).get(week, [])
    grouped: dict[str, list[Game]] = {}
    for g in games:
        grouped.setdefault(g.kickoff, []).append(g)
    return [
        Wave(kickoff=k, games=tuple(grouped[k]))
        for k in sorted(grouped, key=lambda x: datetime.fromisoformat(x))
    ]


def kickoff_by_team(season: str, week: int) -> dict[str, datetime]:
    """Map each NFL team abbreviation to its kickoff — drives per-player lock state."""
    out: dict[str, datetime] = {}
    for game in load_schedule(season).get(week, []):
        for team in game.teams:
            out[team] = game.kickoff_dt
    return out


def due_wave(
    waves: list[Wave], now: datetime, lead_minutes: int, already_sent: set[str]
) -> Wave | None:
    """The wave we owe an alert for right now, if any.

    Fires once the lead window opens and stays eligible until kickoff, so a
    delayed CI run still delivers before lineups lock rather than skipping.
    """
    for wave in waves:
        if wave.key in already_sent:
            continue
        if wave.fire_at(lead_minutes) <= now < wave.kickoff_dt:
            return wave
    return None
