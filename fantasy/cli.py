"""Entrypoint. Gatekeeper decides whether a wave is due; scan builds the board.

Usage:
  python -m fantasy.cli scan            # scan now, write HTML, print digest
  python -m fantasy.cli run             # gatekeeper: send only if a wave is due
  python -m fantasy.cli run --force     # scan + send regardless of schedule
  python -m fantasy.cli schedule        # show this week's kickoff waves
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone

from . import config, ledger, notify, render, schedule, state
from .adapters import espn, sleeper
from .models import LeagueMatchup


def _waves(season: str, week: int):
    """Alert cadence: one send per game day, or one per kickoff wave."""
    if config.SEND_MODE == "wave":
        return schedule.waves_for_week(season, week)
    return schedule.day_waves(season, week)


def _next_poll(dt: datetime, minutes: int = 30) -> datetime:
    """First coarse Actions poll at or after an alert becomes eligible."""
    poll = dt.replace(second=0, microsecond=0)
    remainder = poll.minute % minutes
    if remainder or poll < dt:
        poll += timedelta(minutes=minutes - remainder)
    return poll


def collect(week: int, season: str) -> list[LeagueMatchup]:
    """Fetch every configured league. One league failing never kills the run."""
    out: list[LeagueMatchup] = []
    for i, lid in enumerate(config.ESPN_LEAGUES):
        try:
            out.append(espn.fetch(lid, week, season, priority=i))
        except Exception as exc:
            out.append(LeagueMatchup("espn", lid, f"ESPN {lid}", i, "", "",
                                     error=f"{type(exc).__name__}: {exc}"))
    base = len(config.ESPN_LEAGUES)
    for i, lid in enumerate(config.SLEEPER_LEAGUES):
        try:
            out.append(sleeper.fetch(lid, week, config.SLEEPER_USER_ID, priority=base + i))
        except Exception as exc:
            out.append(LeagueMatchup("sleeper", lid, f"Sleeper {lid}", base + i, "", "",
                                     error=f"{type(exc).__name__}: {exc}"))
    return sorted(out, key=lambda m: m.priority)


def scan(wave: schedule.Wave | None, now: datetime):
    week, season = schedule.current_week()
    matchups = collect(week, season)
    kickoffs = schedule.kickoff_by_team(season, week)
    table = ledger.build(matchups, kickoffs, now)
    html = render.board(matchups, table, week, wave, now)
    config.OUT.mkdir(parents=True, exist_ok=True)
    path = config.OUT / "index.html"
    path.write_text(html, encoding="utf-8")
    digest = render.sms_text(table, week, wave, matchups)
    return matchups, table, digest, path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="fantasy")
    ap.add_argument("command", choices=["scan", "run", "schedule"])
    ap.add_argument("--force", action="store_true", help="ignore wave timing and dedup")
    ap.add_argument("--dry-run", action="store_true", help="build but do not send")
    ap.add_argument("--as-of", metavar="ISO",
                    help="pretend it is this UTC time — previews lock state for a "
                         "future wave, e.g. 2026-09-13T15:30")
    args = ap.parse_args(argv)

    now = datetime.now(timezone.utc)
    if args.as_of:
        now = datetime.fromisoformat(args.as_of)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
    week, season = schedule.current_week()

    if args.command == "schedule":
        for w in _waves(season, week):
            fire = w.fire_at(config.LEAD_MINUTES).astimezone(schedule.DISPLAY_TZ)
            poll = _next_poll(fire)
            print(f"{w.label:18s} {len(w.games):2d}g  eligible {fire:%a %-I:%M%p} "
                  f"· first poll {poll:%-I:%M%p} {config.DISPLAY_TZ_LABEL}  {w.key}")
        return 0

    wave = None
    if args.as_of:
        upcoming = [w for w in _waves(season, week) if w.kickoff_dt > now]
        wave = upcoming[0] if upcoming else None
    if args.command == "run" and not args.force:
        sent = state.load()
        waves = _waves(season, week)
        wave = schedule.due_wave(waves, now, config.LEAD_MINUTES, sent)
        if wave is None:
            print("no wave due — exiting")
            return 0
        print(f"wave due: {wave.label} ({wave.key})")

    matchups, table, digest, path = scan(wave, now)

    for m in matchups:
        status = f"ERROR {m.error}" if m.error else f"{len(m.my_starters)}v{len(m.opp_starters)} vs {m.opp_team}"
        print(f"  [{m.platform:7s}] {m.league_name[:34]:34s} {status}")
    print(f"\nboard -> {path}\n\n{digest}")

    if args.command == "run" and not args.dry_run:
        notify.send(digest)
        if wave is not None:
            state.mark(wave.key)
        print("\nsent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
