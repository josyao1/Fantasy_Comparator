"""Tests for the parts where a bug produces a wrong board instead of a crash."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fantasy import ledger, schedule
from fantasy.cli import _next_poll
from fantasy.crosswalk import normalize_team, player_key
from fantasy.leagues import assign as assign_leagues
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


def test_known_league_labels_and_colours_are_fixed():
    names = ["Nueva Fantasy Football League", "NU FF", "Substation",
             "IXL Fantasy Football", "IXL Champions League ‘26 - Kiwi"]
    assigned = assign_leagues(names)
    assert assigned["Nueva Fantasy Football League"] == {"code": "N", "color": "#3B82F6"}
    assert assigned["NU FF"] == {"code": "N", "color": "#A855F7"}
    assert assigned["Substation"] == {"code": "SF", "color": "#EF4444"}
    assert assigned["IXL Fantasy Football"] == {"code": "IXL", "color": "#A16207"}
    assert assigned["IXL Champions League ‘26 - Kiwi"] == {"code": "CL", "color": "#FBBF24"}


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
    assert '<option value="open">Open</option>' in html
    assert '<option value="time">Kickoff</option>' in html
    assert 'data-league-check="safe"' in html
    assert '<span class="opp">vs them</span>' not in html
    assert "safe — vs them" in html  # still available in the expanded explanation
    assert 'aria-expanded="false"' in html
    assert "data-thin-check" in html
    assert 'data-short="C. McCaffrey"' in html
    assert 'data-view-select' in html
    assert 'data-sort-select' in html
    assert 'data-filter-select' in html
    assert '<div class="meaning">' not in html


def test_derived_views_always_rebuild_from_immutable_cards():
    # League view repeats a player once per opposing league. Reading cards
    # back from that rendered view caused exponential duplication on re-sort.
    assert "var sourceCards" in render.JS
    build = render.JS.split("function build()")[1].split("function press(")[0]
    assert "var all = cards()" in build
    assert 'stage.querySelectorAll(".card")' not in build


def test_league_toggles_recompute_exposure_instead_of_only_hiding_cards():
    assert "function prepareCard" in render.JS
    assert 'card.dataset.tier = against.length >= 2 ? "multi" : "single"' in render.JS
    assert 'if(scope === "cheer") card.dataset.tier = mine.length >= 2' in render.JS
    assert "card.dataset.exp = against.length" in render.JS
    assert "updateSummary(effective)" in render.JS


def test_board_has_three_player_scopes_and_owned_only_source_cards():
    html = _render_with_name("safe")
    assert 'data-scope="against"' in html
    assert 'data-scope="cheer"' in html
    assert 'data-scope="overlap"' in html
    source = html.split('<template id="card-source">')[1].split("</template>")[0]
    # CMC is only on our lineup in this fixture, but the Cheer view still needs him.
    assert 'data-name="Christian McCaffrey"' in source
    assert 'data-name="Ja&#x27;Marr Chase"' in source
    assert "function belongs" in render.JS


def test_board_has_all_32_persistent_nfl_team_filters():
    html = _render_with_name("safe")
    assert html.count("data-team-check=") == 32
    assert 'data-team-check="ARI"' in html
    assert 'data-team-check="WAS"' in html
    assert 'data-teams="all"' in html
    assert 'data-teams="none"' in html
    assert '"fm-hidden-teams"' in render.JS


def test_overlap_badge_is_recomputed_after_league_filters():
    assert 'card.dataset.overlap = conflict ? "1" : "0"' in render.JS
    assert 'card.classList.toggle("has-overlap", conflict)' in render.JS
    assert "badge.hidden = !conflict" in render.JS
    assert ".overlap-badge[hidden]{display:none!important}" in render.CSS


def test_divided_players_are_only_separated_in_the_divided_scope():
    html = _render_with_name("safe")
    stage = html.split('<div id="stage">')[1].split('<template id="card-source">')[0]
    assert "<h2>Divided" not in stage
    assert '>Divided<small>' in html
    against_tiers = render.JS.split('else tiers = [')[1].split('];')[0]
    cheer_tiers = render.JS.split('if(scope === "cheer") tiers = [')[1].split('];')[0]
    assert '"divided"' not in against_tiers
    assert '"divided"' not in cheer_tiers
    against_summary = render.JS.split('} else {')[2].split('var open =')[0]
    assert 'firstLabel = "overlaps"' not in against_summary


def test_thin_mode_is_persistent_and_disables_card_dropdowns():
    assert 'localStorage.getItem("fm-thin-mode")' in render.JS
    assert 'localStorage.setItem("fm-thin-mode"' in render.JS
    assert 'document.body.classList.contains("thin")' in render.JS
    assert "body.thin .chev,body.thin .detail{display:none!important}" in render.CSS
    assert "body.thin .stake-kind{display:none}" in render.CSS
    assert 'body.thin .card.has-overlap .stake-row:has(.stake-kind.for) .chip:after{content:"✓"' in render.CSS
    assert 'body.thin .card.has-overlap .stake-row:has(.stake-kind.against) .chip:after{content:"×"' in render.CSS
