"""Tests for the parts where a bug produces a wrong board instead of a crash."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fantasy import ledger, schedule
from fantasy.cli import _next_poll
from fantasy.crosswalk import normalize_team, player_key
from fantasy.models import LeagueMatchup, Player

UTC = timezone.utc
NOW = datetime(2026, 9, 13, 15, 0, tzinfo=UTC)   # Sun 11:00am ET


def test_espn_and_sleeper_washington_are_one_player():
    # ESPN says WSH, Sleeper says WAS. Unnormalized this breaks every
    # own-vs-face check for Washington players.
    assert player_key("Jayden Daniels", "QB", "WSH") == player_key("Jayden Daniels", "QB", "WAS")
    assert normalize_team("OAK") == "LV"


def test_suffix_and_punctuation_folding():
    assert player_key("Marvin Harrison Jr.", "WR", "ARI") == player_key("Marvin Harrison", "WR", "ARI")
    assert player_key("Ja'Marr Chase", "WR", "CIN") == player_key("JaMarr Chase", "wr", "cin")


def test_same_name_different_player_stays_distinct():
    # Two active Warrens; collapsing them would invent a phantom exposure.
    assert player_key("Jaylen Warren", "RB", "PIT") != player_key("Tyler Warren", "TE", "IND")


def _matchup(name, mine, theirs, priority=0):
    return LeagueMatchup("sleeper", name, name, priority, "me", "them",
                         my_starters=mine, opp_starters=theirs)


CMC = Player("Christian McCaffrey", "RB", "SF")
CHASE = Player("Ja'Marr Chase", "WR", "CIN")
KICKER = Player("Evan McPherson", "K", "CIN")


def test_conflict_reports_net_stake():
    table = ledger.build([
        _matchup("L1", [CMC], [CHASE]),
        _matchup("L2", [], [CMC]),
        _matchup("L3", [], [CMC]),
    ], {}, NOW)
    conf = ledger.conflicts(table)
    assert [e.player.name for e in conf] == ["Christian McCaffrey"]
    assert conf[0].net == -1                      # start in 1, face in 2
    assert conf[0].for_leagues == ["L1"]
    assert sorted(conf[0].against_leagues) == ["L2", "L3"]


def test_multi_exposure_excludes_conflicts():
    table = ledger.build([
        _matchup("L1", [], [CHASE]),
        _matchup("L2", [], [CHASE]),
        _matchup("L3", [CMC], [CMC]),
    ], {}, NOW)
    assert [e.player.name for e in ledger.multi_exposure(table)] == ["Ja'Marr Chase"]
    # CMC is a conflict, so he must not be double-counted here
    assert [e.player.name for e in ledger.conflicts(table)] == ["Christian McCaffrey"]


def test_kickers_are_excluded_from_skill_scope():
    table = ledger.build([_matchup("L1", [], [KICKER])], {}, NOW)
    assert table == {}


def test_lock_state_follows_kickoff():
    kicks = {"SF": NOW - timedelta(minutes=5), "CIN": NOW + timedelta(hours=2)}
    table = ledger.build([_matchup("L1", [], [CMC, CHASE])], kicks, NOW)
    assert table[CMC.key].locked is True
    assert table[CHASE.key].locked is False


def test_errored_league_contributes_nothing():
    bad = LeagueMatchup("espn", "9", "ESPN 9", 0, "", "", error="auth expired")
    table = ledger.build([bad, _matchup("L1", [], [CMC])], {}, NOW)
    assert len(table) == 1


# ── gatekeeper ────────────────────────────────────────────────────────────
def _wave(dt):
    return schedule.Wave(kickoff=dt.isoformat(), games=())


def test_wave_fires_inside_lead_window_once():
    kickoff = NOW + timedelta(minutes=60)
    waves = [_wave(kickoff)]
    due = schedule.due_wave(waves, NOW, 90, set())
    assert due is not None
    # already sent -> never again
    assert schedule.due_wave(waves, NOW, 90, {due.key}) is None


def test_wave_not_due_before_lead_window():
    assert schedule.due_wave([_wave(NOW + timedelta(hours=4))], NOW, 90, set()) is None


def test_late_run_still_fires_before_kickoff():
    # CI delayed 80 of the 90 lead minutes: must still deliver.
    assert schedule.due_wave([_wave(NOW + timedelta(minutes=10))], NOW, 90, set()) is not None


def test_wave_expires_at_kickoff():
    assert schedule.due_wave([_wave(NOW - timedelta(minutes=1))], NOW, 90, set()) is None


def test_action_poll_time_rounds_up_to_next_half_hour():
    assert _next_poll(NOW.replace(minute=50)).minute == 0
    assert _next_poll(NOW.replace(minute=50)).hour == NOW.hour + 1
    assert _next_poll(NOW.replace(minute=5)).minute == 30
    assert _next_poll(NOW.replace(minute=30)).minute == 30


# ── injection ─────────────────────────────────────────────────────────────
# League and team names come from the ESPN/Sleeper APIs, so they are written
# by other members of the league and must be treated as untrusted input.
from datetime import timezone as _tz

from fantasy import render


def _render_with_name(name: str, opp: str = "them") -> str:
    m = LeagueMatchup("sleeper", "1", name, 0, "me", opp,
                      my_starters=[CMC], opp_starters=[CHASE])
    table = ledger.build([m], {}, NOW)
    return render.board([m], table, 1, None, NOW)


def test_script_breakout_in_league_name_is_neutralised():
    evil = '</script><script>alert(1)</script>'
    html = _render_with_name(evil)
    # the raw closing tag must never appear inside the embedded JSON block
    blob = html.split('<script id="meta" type="application/json">')[1].split("</script>")[0]
    assert "</script" not in blob
    assert "\\u003c" in blob


def test_league_name_is_escaped_in_server_rendered_markup():
    html = _render_with_name('<img src=x onerror=alert(1)>')
    assert "<img src=x onerror" not in html
    assert "&lt;img src=x onerror" in html


def test_opponent_name_cannot_inject_markup():
    html = _render_with_name("safe", opp='"><script>alert(1)</script>')
    blob = html.split('<script id="meta" type="application/json">')[1].split("</script>")[0]
    assert "</script" not in blob


def test_client_side_grouping_never_uses_innerhtml_for_names():
    # the group builder must construct DOM nodes, not concatenate markup
    assert "innerHTML" not in render.JS.split("function group(")[1].split("return d;")[0]
    assert "textContent" in render.JS


def test_board_has_clear_relationship_labels_and_controls():
    html = _render_with_name("safe")
    assert '<span class="stake-kind for">Start</span>' in html
    assert '<span class="stake-kind against">Against</span>' in html
    assert '<button data-theme=' not in html
    assert 'data-filter="open"' in html
    assert 'data-sort="time"' in html
    assert 'data-league-check="safe"' in html
    assert '<span class="opp">vs them</span>' in html
    assert 'aria-expanded="false"' in html


def test_derived_views_always_rebuild_from_immutable_cards():
    # League view repeats a player once per opposing league. Reading cards
    # back from that rendered view caused exponential duplication on re-sort.
    assert "var sourceCards" in render.JS
    build = render.JS.split("function build()")[1].split("function press(")[0]
    assert "var all = cards()" in build
    assert 'stage.querySelectorAll(".card")' not in build


def test_league_toggles_recompute_exposure_instead_of_only_hiding_cards():
    assert "function prepareCard" in render.JS
    assert 'card.dataset.tier = conflict ? "divided"' in render.JS
    assert "card.dataset.exp = against.length" in render.JS
    assert "updateSummary(effective)" in render.JS
