"""Broadcast-style HTML board and SMS digest.

The board reads like a pregame graphics package: near-black ground, cut-out
portraits, condensed caps, and a team-colour rail per player. A face is
recognised faster than a name, which is the whole job of this page.

Three groupings answer three different questions, so they are groupings
rather than sort keys:
  threat  — what is unusual this week (divided / doubled / single)
  kickoff — what is about to happen, with lock state per wave
  league  — how each individual head-to-head looks

The threat view is rendered as real HTML; the others are built by cloning
those cards, so the board degrades to a usable list if scripting fails.
"""
from __future__ import annotations

import html
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from . import config, ledger
from .headshots import rail_color, url_for
from .leagues import assign as assign_leagues
from .models import Exposure, LeagueMatchup

DISPLAY_TZ = ZoneInfo(config.DISPLAY_TIMEZONE)

LEAGUES: dict[str, dict] = {}

CSS = """
:root{
  --bg:#070B10; --card1:#111925; --card2:#0B1119; --rule:#1C2734;
  --ink:#EDF2F7; --mut:#7E8B9C; --faint:#5B6879;
  --against:#FF6B35; --against2:#FF8C42; --for:#48C9E8; --amber:#FFB020;
  --warnbg:#2A1608; --warn:#FF9A52;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);padding-bottom:3.5rem;
  font:15px/1.45 "Barlow Condensed",system-ui,-apple-system,sans-serif}
.mono{font-family:ui-monospace,"SF Mono",Menlo,monospace;font-variant-numeric:tabular-nums}
.wrap{max-width:700px;margin:0 auto;padding:0 13px}

/* ── masthead ─────────────────────────────────────────── */
.top{padding:19px 0 14px;border-bottom:2px solid var(--rule)}
.eyebrow{font:500 10.5px/1 ui-monospace,"SF Mono",Menlo,monospace;letter-spacing:.19em;
  text-transform:uppercase;color:var(--faint)}
.thesis{font-size:41px;font-weight:800;line-height:.92;letter-spacing:-.022em;
  text-transform:uppercase;margin:9px 0 0}
.thesis em{font-style:normal;color:var(--amber)}
.tally{display:flex;gap:16px;margin-top:11px;flex-wrap:wrap;
  font:500 11px/1 ui-monospace,"SF Mono",Menlo,monospace;letter-spacing:.09em;
  text-transform:uppercase;color:var(--faint)}
.tally b{color:var(--ink);font-size:14px;font-weight:700}

/* ── controls ─────────────────────────────────────────── */
.bar{display:flex;gap:6px;align-items:center;flex-wrap:wrap;padding:12px 0 4px}
.bar .cap{font:500 9.5px/1 ui-monospace,"SF Mono",Menlo,monospace;letter-spacing:.19em;
  text-transform:uppercase;color:var(--faint);margin-right:3px}
.bar button{font:600 12px/1 "Barlow Condensed",sans-serif;letter-spacing:.06em;
  text-transform:uppercase;padding:7px 11px;cursor:pointer;background:transparent;
  color:var(--mut);border:1px solid var(--rule);border-radius:3px}
.bar button:hover{color:var(--ink);border-color:var(--mut)}
.bar button[aria-pressed="true"]{background:var(--amber);border-color:var(--amber);color:#0B1119}
.bar button:focus-visible{outline:2px solid var(--for);outline-offset:2px}

/* ── group headers ────────────────────────────────────── */
.grp{margin-top:22px}
.grp > h2{display:flex;align-items:baseline;gap:9px;margin:0 0 3px;
  font:600 11px/1 ui-monospace,"SF Mono",Menlo,monospace;letter-spacing:.19em;
  text-transform:uppercase;color:var(--mut)}
.grp > h2 .n{color:var(--faint);font-weight:400}
.grp > h2 .st{margin-left:auto;font-size:9.5px;letter-spacing:.15em}
.grp > h2 .dot{width:9px;height:9px;border-radius:2px;background:var(--lc);flex:none}
.grp.lg-grp > h2{color:var(--lc)}
.grp > h2 .st.open{color:var(--against)}
.grp > h2 .st.shut{color:var(--faint)}
.grp > .sub{margin:0 0 10px;font-size:12.5px;color:var(--faint);
  font-family:system-ui,sans-serif}

/* ── player card ──────────────────────────────────────── */
.card{position:relative;display:flex;align-items:stretch;gap:0;margin-bottom:6px;
  background:linear-gradient(96deg,var(--card1) 0%,var(--card2) 66%);
  border-left:4px solid var(--tc,#FFB020);overflow:hidden;min-height:74px}
.card.lk{filter:saturate(.2);opacity:.55}
.card .ph{width:70px;flex:none;object-fit:cover;object-position:top center;
  background:#0E1620;align-self:stretch}
.card .noph{width:70px;flex:none;background:#0E1620;display:flex;align-items:center;
  justify-content:center;font:700 21px/1 "Barlow Condensed",sans-serif;color:var(--faint)}
.card .body{flex:1;min-width:0;padding:11px 12px 11px 13px}
.nm{font-size:23px;font-weight:700;line-height:1;text-transform:uppercase;
  letter-spacing:-.012em;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mt{font:500 10.5px/1 ui-monospace,"SF Mono",Menlo,monospace;letter-spacing:.13em;
  color:var(--mut);margin-top:5px}
.side{display:flex;flex-wrap:wrap;gap:5px;align-items:center;margin-top:8px}
.side .ar{font-size:10px;line-height:1}
.side .ar.a{color:var(--against2)} .side .ar.f{color:var(--for)}
.chip{display:inline-block;font:700 10px/1 ui-monospace,"SF Mono",Menlo,monospace;
  letter-spacing:.09em;padding:3.5px 6px;border-radius:2px;color:#070B10;
  background:var(--lc,#CBD5E1);white-space:nowrap}
.chip.ghost{background:transparent;color:var(--lc,#CBD5E1);
  box-shadow:inset 0 0 0 1.5px var(--lc,#CBD5E1)}

/* ── league legend ───────────────────────────────────── */
.legend{display:flex;flex-wrap:wrap;gap:6px;padding:13px 0 2px}
.lgd{display:flex;align-items:center;gap:6px;padding:6px 9px 6px 7px;
  background:var(--card2);border:1px solid var(--rule);border-left:3px solid var(--lc);
  border-radius:3px;min-width:0}
.lgd .code{font:700 10px/1 ui-monospace,"SF Mono",Menlo,monospace;letter-spacing:.09em;
  color:var(--lc)}
.lgd .vs{font:400 11px/1.25 system-ui,sans-serif;color:var(--mut);
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:22ch}
.fig{flex:none;text-align:right;padding:11px 13px 11px 6px;align-self:center}
.fg{font:800 31px/1 "Barlow Condensed",sans-serif;letter-spacing:-.02em}
.fg.neg{color:var(--against)} .fg.pos{color:var(--for)}
.fg.zip{color:var(--faint);font-size:17px}
.fl{font:500 8.5px/1 ui-monospace,"SF Mono",Menlo,monospace;letter-spacing:.18em;
  color:var(--faint);margin-top:5px}

/* ── errors + empties ─────────────────────────────────── */
.err{background:var(--warnbg);border:1px solid var(--warn);border-left-width:4px;
  color:var(--warn);padding:10px 13px;margin-bottom:6px;font-size:13.5px;
  font-family:system-ui,sans-serif}
.err b{font-weight:600}
.empty{color:var(--faint);font-size:13px;padding:11px 0;font-family:system-ui,sans-serif;
  font-style:italic}
footer{margin-top:32px;padding-top:13px;border-top:1px solid var(--rule);
  font:400 10.5px/1.6 ui-monospace,"SF Mono",Menlo,monospace;letter-spacing:.09em;
  color:var(--faint)}
@media (max-width:420px){
  .thesis{font-size:33px} .nm{font-size:20px} .fg{font-size:26px}
  .card .ph,.card .noph{width:58px}
}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
"""

# The first block is the no-script fallback. These production overrides keep
# the broadcast layout crisp, compact, and readable on a phone.
CSS += """
:root{
  --surface:#0E1620;--surface2:#131E2B;--ink:#F4F7FB;--mut:#B5C0CC;
  --faint:#9AA8B8;--accent:#FFB020;--against:#FF7548;--for:#53D6EE;
  --radius:2px;--card-border:4px;--shadow:none;
  --display:"Barlow Condensed",system-ui,sans-serif;
  --body:system-ui,-apple-system,sans-serif;
  --mono:ui-monospace,"SF Mono",Menlo,monospace;
}
html{background:var(--bg);overflow-x:hidden}
body{background:var(--bg);color:var(--ink);font:15px/1.45 var(--body);
  padding-bottom:calc(3.5rem + env(safe-area-inset-bottom));transition:background .18s ease,color .18s ease;
  overflow-x:hidden}
button{font:inherit}.wrap{width:100%;padding:0 max(14px,env(safe-area-inset-left));overflow:hidden}
.eyebrow,.cap,.mt,.stake-kind,.chip,.tally,.fl,footer{font-family:var(--mono);font-variant-numeric:tabular-nums}
.top{padding:21px 0 16px;border-color:var(--rule)}
.eyebrow{font-size:12px;line-height:1.25;font-weight:650;letter-spacing:.11em;color:var(--faint)}
.thesis{font-family:var(--display);font-size:42px;line-height:.95;color:var(--ink)}
.thesis em{color:var(--accent)}
.tally{gap:18px;margin-top:13px;font-size:12px;line-height:1.2;font-weight:650;
  letter-spacing:.05em;color:var(--faint)}
.tally b{color:var(--ink);font-size:15px;font-weight:800;margin-right:3px}
.next-lock{display:flex;align-items:center;gap:11px;margin:14px 0 0;padding:11px 12px;
  background:var(--surface);border:1px solid var(--rule);border-left:4px solid var(--accent);
  border-radius:var(--radius)}
.next-lock .clock{font-family:var(--display);font-size:20px;font-weight:800;color:var(--accent);white-space:nowrap}
.next-lock .next-copy{min-width:0;font-size:13px;color:var(--mut)}
.next-lock .next-copy b{display:block;color:var(--ink);font-size:14px}
.meaning{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:13px;
  padding:10px 11px;background:var(--surface);border:1px solid var(--rule);border-radius:var(--radius)}
.meaning-label{font-size:13px;color:var(--mut);margin-right:2px}
.stake-kind{display:inline-flex;align-items:center;min-height:24px;padding:4px 7px;border-radius:4px;
  font-size:11px;line-height:1;font-weight:800;letter-spacing:.06em;white-space:nowrap}
.stake-kind.for{color:var(--for);border:1px solid var(--for);background:transparent}
.stake-kind.against{color:var(--bg);border:1px solid var(--against);background:var(--against)}
.legend{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px;padding:9px 0 4px}
.legend-title{margin-top:13px;font:750 12px/1.3 var(--mono);letter-spacing:.07em;
  text-transform:uppercase;color:var(--faint)}
.legend-title span{font-family:var(--body);font-weight:500;letter-spacing:0;text-transform:none}
.lgd{min-height:44px;padding:8px 9px;background:var(--surface);border-color:var(--rule);border-left-width:4px;
  border-radius:var(--radius);cursor:pointer;user-select:none}
.lgd:has(input:not(:checked)){opacity:.58;border-left-color:var(--rule)}
.lgd input{width:18px;height:18px;flex:none;margin:0;accent-color:var(--lc);cursor:pointer}
.lgd .code{font:800 11px/1 var(--mono);letter-spacing:.05em}.lgd .vs{min-width:0;font-size:12px;color:var(--mut);
  max-width:none;white-space:normal;overflow:visible;text-overflow:clip;overflow-wrap:anywhere}
.controls{position:relative;margin:10px -5px 0;padding:7px 5px 9px;
  max-width:calc(100% + 10px);background:var(--bg);border-bottom:1px solid var(--rule)}
.bar{display:grid;grid-template-columns:55px minmax(0,1fr);gap:7px;align-items:start;padding:3px 0;min-width:0}
.bar .cap{font-size:11px;line-height:44px;font-weight:750;letter-spacing:.08em;color:var(--faint);margin:0}
.choices{display:flex;gap:6px;align-items:center;flex-wrap:wrap;min-width:0;max-width:100%}
.bar button{min-height:44px;padding:9px 12px;background:var(--surface);color:var(--mut);
  border-color:var(--rule);border-radius:var(--radius);font-family:var(--display);
  font-size:13px;line-height:1;font-weight:750;letter-spacing:.025em;text-transform:none}
.bar button[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:var(--bg)}
button:focus-visible{outline:3px solid var(--for);outline-offset:2px}
.grp{margin-top:25px}.grp>h2{align-items:center;margin-bottom:5px;font:750 13px/1.2 var(--mono);
  letter-spacing:.09em;color:var(--mut)}
.grp>h2 .n{color:var(--faint);font-weight:600}.grp>h2 .st{font-size:11px;letter-spacing:.05em}
.grp>.sub{margin-bottom:11px;font-size:14px;line-height:1.4;color:var(--faint);font-family:var(--body)}
.card{display:block;min-height:0;margin-bottom:6px;background:var(--surface);border:1px solid var(--rule);
  border-left:max(1px,var(--card-border)) solid var(--tc,#FFB020);border-radius:var(--radius);
  box-shadow:var(--shadow);overflow:hidden;filter:none;opacity:1}
.card-main{display:grid;grid-template-columns:64px minmax(0,1fr) auto 25px;width:100%;max-width:100%;min-height:76px;
  align-items:stretch;padding:0;text-align:left;
  color:inherit;background:transparent;border:0;cursor:pointer}
.card .ph,.card .noph{width:100%;height:100%;min-height:76px;background:var(--surface2)}
.card .ph{object-fit:cover;object-position:top center;align-self:stretch}
.card .noph{display:flex;align-items:center;justify-content:center;font:800 22px/1 var(--display);color:var(--faint)}
.card.lk{filter:none;opacity:1;border-style:dashed}.card.lk .ph{filter:grayscale(1);opacity:.48}
.card.lk .nm{color:var(--mut)}
.card .body{padding:9px 6px 8px 10px}.nm{font-family:var(--display);font-size:21px;font-weight:800;line-height:1.02}
.mt{display:flex;align-items:center;gap:7px;flex-wrap:wrap;font-size:12px;line-height:1.25;
  font-weight:650;letter-spacing:.025em;color:var(--mut);margin-top:4px}
.lock{display:inline-flex;padding:3px 6px;border:1px solid var(--faint);border-radius:3px;
  color:var(--faint);font-size:10px;font-weight:800;letter-spacing:.06em;text-transform:uppercase}
.side{display:grid;gap:3px;margin-top:6px}.stake-row{display:flex;flex-wrap:wrap;gap:4px;align-items:center;min-width:0}
.matchup-ref{display:inline-flex;align-items:center;gap:5px;min-width:0}
.opp{max-width:15ch;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
  color:var(--mut);font-size:11px;line-height:1.2}
.chip,.chip.ghost{display:inline-flex;align-items:center;min-height:20px;font-size:10.5px;line-height:1;
  font-weight:800;letter-spacing:.035em;padding:3px 6px;border-radius:3px;color:var(--bg);
  background:var(--lc,#CBD5E1);box-shadow:none}
.fig{padding:10px 4px;min-width:49px}.fg{font:800 26px/1 var(--display);font-variant-numeric:tabular-nums}
.fg.neg{color:var(--against)}.fg.pos{color:var(--for)}.fg.zip{color:var(--faint);font-size:18px}
.fl{font-size:10px;line-height:1;font-weight:750;letter-spacing:.08em;color:var(--faint);text-transform:uppercase}
.chev{width:25px;display:flex;align-items:center;justify-content:center;color:var(--faint);
  font-size:17px;transition:transform .15s ease}.card-main[aria-expanded="true"] .chev{transform:rotate(180deg)}
.detail{padding:12px 14px 14px;border-top:1px solid var(--rule);background:var(--surface2);
  color:var(--mut);font-size:14px;line-height:1.45}.detail[hidden]{display:none}.detail b{color:var(--ink)}
.detail-row+.detail-row{margin-top:7px}
.empty{color:var(--faint);font-size:14px;padding:15px;background:var(--surface);
  border:1px dashed var(--rule);border-radius:var(--radius);font-family:var(--body);font-style:normal}
.err{font-size:14px;border-radius:var(--radius);font-family:var(--body)}
footer{font-size:12px;letter-spacing:.035em;color:var(--faint)}
@media(max-width:420px){
  .wrap{padding-left:12px;padding-right:12px}.thesis{font-size:35px}.legend{grid-template-columns:1fr}
  .bar{grid-template-columns:48px 1fr}.bar button{padding-left:10px;padding-right:10px}
  .card-main{grid-template-columns:58px minmax(0,1fr) auto 22px}.nm{font-size:19px}.fg{font-size:24px}.fig{min-width:45px}
}
@media(prefers-reduced-motion:reduce){*{transition:none!important;scroll-behavior:auto!important}}
"""

FONT_LINK = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
             'family=Barlow+Condensed:wght@500;600;700;800&display=swap">')


def _esc(s) -> str:
    return html.escape(str(s or ""))


def _fig(e: Exposure) -> str:
    """Exposure count for pure threats, net spread once you also own him."""
    if e.is_conflict:
        if e.net == 0:
            return '<div class="fg zip">even</div><div class="fl">net</div>'
        cls = "pos" if e.net > 0 else "neg"
        return f'<div class="fg {cls}">{e.net:+d}</div><div class="fl">net</div>'
    n = len(e.against_leagues)
    return f'<div class="fg neg">&times;{n}</div><div class="fl">league{"s" if n > 1 else ""}</div>'


def _tier(e: Exposure) -> str:
    if e.is_conflict:
        return "divided"
    return "multi" if e.is_multi else "single"


def _card(e: Exposure) -> str:
    kick = e.kickoff.astimezone(DISPLAY_TZ) if e.kickoff else None
    wave = (f"{kick:%a} {kick:%-I:%M%p} {config.DISPLAY_TZ_LABEL}"
            .replace("AM", "am").replace("PM", "pm") if kick else "TBD")
    meta = f'{e.player.position} &middot; {e.player.team}'
    if kick:
        meta += f' &middot; {wave}'

    def chips(names, show_opponent=False):
        out = []
        for n in names:
            league = LEAGUES.get(n, {"code": n[:5].upper(), "color": "#CBD5E1"})
            chip = (f'<span class="chip" style="--lc:{league["color"]}" '
                    f'title="{_esc(n)}" aria-label="{_esc(n)}">'
                    f'{_esc(league["code"])}</span>')
            if show_opponent and league.get("opp"):
                chip = (f'<span class="matchup-ref">{chip}'
                        f'<span class="opp">vs {_esc(league["opp"])}</span></span>')
            out.append(chip)
        return "".join(out)

    sides = ""
    if e.for_leagues:
        sides += (f'<div class="stake-row"><span class="stake-kind for">Start</span>'
                  f'{chips(e.for_leagues)}</div>')
    if e.against_leagues:
        sides += (f'<div class="stake-row"><span class="stake-kind against">Against</span>'
                  f'{chips(e.against_leagues, True)}</div>')

    src = url_for(e.player.name, e.player.position)
    initials = "".join(p[0] for p in e.player.name.split()[:2]).upper()
    photo = (f'<img class="ph" src="{_esc(src)}" alt="" loading="lazy" '
             f'onerror="this.outerHTML=\'<div class=&quot;noph&quot;>{_esc(initials)}</div>\'">'
             if src else f'<div class="noph">{_esc(initials)}</div>')

    detail = []
    if e.for_leagues:
        detail.append(f'<div class="detail-row"><b>You start { _esc(e.player.name) } in:</b> '
                      f'{", ".join(_esc(n) for n in e.for_leagues)}</div>')
    if e.against_leagues:
        opponents = [f'{n} — vs {LEAGUES.get(n, {}).get("opp", "Opponent")}'
                     for n in e.against_leagues]
        detail.append(f'<div class="detail-row"><b>You face { _esc(e.player.name) } in:</b> '
                      f'{", ".join(_esc(n) for n in opponents)}</div>')
    if e.is_conflict:
        explanation = ("The stakes are even across your leagues." if e.net == 0 else
                       f'Your net exposure is {e.net:+d}: starts minus opposing lineups.')
    else:
        explanation = f'This player appears in {len(e.against_leagues)} opposing starting lineup'
        explanation += 's.' if len(e.against_leagues) != 1 else '.'
    detail.append(f'<div class="detail-row">{_esc(explanation)}</div>')

    against_json = _esc(json.dumps(e.against_leagues))
    for_json = _esc(json.dumps(e.for_leagues))
    lock_badge = '<span class="lock">Locked</span>' if e.locked else ''

    return (
        f'<article class="card{" lk" if e.locked else ""}" style="--tc:{rail_color(e.player.team)}"'
        f' data-key="{_esc(e.player.key)}" data-tier="{_tier(e)}"'
        f' data-exp="{len(e.against_leagues)}" data-net="{e.net}"'
        f' data-name="{_esc(e.player.name)}" data-pos="{_esc(e.player.position)}"'
        f' data-wave="{_esc(wave)}" data-ts="{kick.isoformat() if kick else "9999"}"'
        f' data-locked="{"1" if e.locked else "0"}"'
        f' data-against="{against_json}" data-for="{for_json}">'
        f'<button class="card-main" type="button" aria-expanded="false" '
        f'aria-label="Show why {_esc(e.player.name)} matters">'
        f'{photo}<div class="body"><div class="nm">{_esc(e.player.name)}</div>'
        f'<div class="mt"><span>{meta}</span>{lock_badge}</div>'
        f'<div class="side">{sides}</div></div>'
        f'<div class="fig">{_fig(e)}</div><span class="chev" aria-hidden="true">⌄</span></button>'
        f'<div class="detail" hidden>{"".join(detail)}</div></article>'
    )


def _group(title: str, count: int, sub: str, cards: str, empty: str) -> str:
    n = f'<span class="n">{count}</span>' if count else ""
    body = cards or f'<div class="empty">{empty}</div>'
    subline = f'<p class="sub">{sub}</p>' if sub and cards else ""
    return f'<div class="grp"><h2>{title} {n}</h2>{subline}{body}</div>'


def board(matchups: list[LeagueMatchup], table: dict[str, Exposure], week: int,
          wave, now: datetime) -> str:
    conf = ledger.conflicts(table)
    multi = ledger.multi_exposure(table)
    single = ledger.single_exposure(table)
    facing = [e for e in table.values() if e.against_leagues]
    open_n = sum(1 for e in facing if not e.locked)
    next_times = sorted(e.kickoff for e in facing if not e.locked and e.kickoff)
    next_at = next_times[0] if next_times else None
    next_n = sum(1 for e in facing if next_at and e.kickoff == next_at)
    errs = [m for m in matchups if m.error]
    ok = [m for m in matchups if not m.error]

    label = (wave.label if wave else
             f"{now.astimezone(DISPLAY_TZ):%a %-I:%M%p} {config.DISPLAY_TZ_LABEL}")
    title = f"Week {week} &middot; {_esc(label)}"

    global LEAGUES
    LEAGUES = assign_leagues([m.league_name for m in ok])
    for matchup in ok:
        LEAGUES[matchup.league_name]["opp"] = matchup.opp_team
    league_meta = [{"name": m.league_name, "opp": m.opp_team,
                    "code": LEAGUES[m.league_name]["code"],
                    "color": LEAGUES[m.league_name]["color"]} for m in ok]

    p = ['<div class="wrap"><div class="top">',
         f'<div class="eyebrow">Week {week} &middot; {_esc(label)} &middot; '
         f'{len(ok)} league{"s" if len(ok) != 1 else ""}</div>',
         f'<h1 class="thesis"><em data-facing-count>{len(facing)}</em> can hurt you</h1>',
         '<div class="tally">',
         f'<div><b data-divided-count>{len(conf)}</b> divided</div>',
         f'<div><b data-doubled-count>{len(multi)}</b> doubled</div>',
         f'<div><b data-open-count>{open_n}</b> open</div>',
         '</div>']

    if next_at:
        next_local = next_at.astimezone(DISPLAY_TZ)
        next_label = (f'{next_local:%a %-I:%M%p} {config.DISPLAY_TZ_LABEL}'
                      .replace("AM", "am").replace("PM", "pm"))
        p.append(f'<div class="next-lock" data-next-lock="{next_at.isoformat()}">'
                 f'<div class="clock" data-countdown>Next lock</div>'
                 f'<div class="next-copy"><b data-next-label>{_esc(next_label)} &middot; {next_n} player'
                 f'{"s" if next_n != 1 else ""}</b><span data-next-copy>Still actionable in this kickoff wave</span></div></div>')
    else:
        p.append('<div class="next-lock"><div class="clock" data-countdown>All locked</div>'
                 '<div class="next-copy"><b data-next-label>No upcoming player locks</b>'
                 '<span data-next-copy>Every current threat has kicked off.</span></div></div>')
    p.append('</div>')

    p.append('<div class="meaning"><span class="meaning-label">Card key:</span>'
             '<span class="stake-kind for">Start</span><span class="meaning-label">on your lineup</span>'
             '<span class="stake-kind against">Against</span><span class="meaning-label">on theirs</span></div>')

    p.append('<div class="legend-title">Leagues shown <span>— uncheck any league to remove it from every comparison</span></div>')
    p.append('<div class="legend" role="group" aria-label="Leagues shown">')
    for m in ok:
        meta = LEAGUES[m.league_name]
        p.append(f'<label class="lgd" style="--lc:{meta["color"]}" title="{_esc(m.league_name)}">'
                 f'<input type="checkbox" data-league-check="{_esc(m.league_name)}" checked '
                 f'aria-label="Show {_esc(m.league_name)}">'
                 f'<span class="code">{_esc(meta["code"])}</span>'
                 f'<span class="vs">vs {_esc(m.opp_team)}</span></label>')
    p.append('</div>')

    if errs:
        p += [f'<div class="err" style="margin-top:12px"><b>{_esc(m.league_name)}</b> &mdash; '
              f'{_esc(m.error)}</div>' for m in errs]

    p += ['<div class="controls">',
          '<div class="bar"><span class="cap">Group</span><div class="choices" role="group" aria-label="Group players">',
          '<button data-view="threat" aria-pressed="true">Threat</button>',
          '<button data-view="kickoff" aria-pressed="false">Kickoff</button>',
          '<button data-view="league" aria-pressed="false">League</button>',
          '</div></div>',
          '<div class="bar"><span class="cap">Sort</span><div class="choices" role="group" aria-label="Sort players">',
          '<button data-sort="exp" aria-pressed="true">Most impact</button>',
          '<button data-sort="time" aria-pressed="false">Kickoff</button>',
          '<button data-sort="name" aria-pressed="false">Name</button>',
          '<button data-sort="pos" aria-pressed="false">Position</button>',
          '</div></div>',
          '<div class="bar"><span class="cap">Show</span><div class="choices" role="group" aria-label="Filter players">',
          '<button data-filter="all" aria-pressed="true">All</button>',
          '<button data-filter="open" aria-pressed="false">Open only</button>',
          '<button data-filter="QB" aria-pressed="false">QB</button>',
          '<button data-filter="RB" aria-pressed="false">RB</button>',
          '<button data-filter="WR" aria-pressed="false">WR</button>',
          '<button data-filter="TE" aria-pressed="false">TE</button>',
          '</div></div></div>',
          '<div id="stage">']

    p.append(_group("Divided", len(conf),
                    "You start him and you face him. Net is your true stake.",
                    "".join(_card(e) for e in conf),
                    "Nobody you start is playing against you."))
    p.append(_group("Doubled up", len(multi),
                    "One big game costs you more than one matchup.",
                    "".join(_card(e) for e in multi),
                    "Nobody is facing you in two leagues."))
    p.append(_group("Facing", len(single), "",
                    "".join(_card(e) for e in single),
                    "No other skill starters against you."))
    p.append('</div>')

    p.append(f'<footer>Generated {now.astimezone(DISPLAY_TZ):%a %b %-d %-I:%M%p} '
             f'{_esc(config.DISPLAY_TZ_LABEL)} &middot; '
             f'ESPN + Sleeper &middot; photos Sleeper CDN</footer></div>')

    # League and team names are written by other league members, so they are
    # untrusted. json.dumps does not escape <, which would let a name
    # containing </script> break out of the block below.
    data = (json.dumps({"leagues": league_meta})
            .replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("&", "\\u0026").replace("\u2028", "\\u2028")
            .replace("\u2029", "\\u2029"))
    return (f'<!doctype html><html lang="en" data-theme="broadcast"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="color-scheme" content="dark">'
            f'<title>{title}</title>{FONT_LINK}<style>{CSS}</style></head><body>'
            + "".join(p)
            + f'<script id="meta" type="application/json">{data}</script>'
            + f'<script>{JS}</script></body></html>')


JS = r"""
(function(){
  var stage = document.getElementById("stage");
  if(!stage) return;
  // Every derived view starts from this immutable set. League view repeats a
  // multi-exposed player by design, so reading back from the current DOM would
  // multiply cards every time the user changed a control.
  var sourceCards = Array.prototype.slice.call(stage.querySelectorAll(".card"))
    .map(function(c){ return c.cloneNode(true); });
  var leagueMeta = JSON.parse(document.getElementById("meta").textContent).leagues;
  var view = "threat", sort = "exp", filter = "all";

  function jsonList(card, key){
    try { return JSON.parse(card.dataset[key] || "[]"); }
    catch(e) { return []; }
  }

  function selectedLeagues(){
    return new Set(Array.prototype.slice.call(document.querySelectorAll("[data-league-check]:checked"))
      .map(function(input){ return input.dataset.leagueCheck; }));
  }

  function opponentFor(name){
    var league = leagueMeta.find(function(item){ return item.name === name; });
    return league ? league.opp : "Opponent";
  }

  function addDetail(detail, lead, names, showOpponents){
    if(!names.length) return;
    var row = el("div", "detail-row");
    row.appendChild(el("b", null, lead));
    var labels = names.map(function(name){
      return showOpponents ? name + " — vs " + opponentFor(name) : name;
    });
    row.appendChild(document.createTextNode(" " + labels.join(", ")));
    detail.appendChild(row);
  }

  function prepareCard(source, selected){
    var mine = jsonList(source, "for").filter(function(name){ return selected.has(name); });
    var against = jsonList(source, "against").filter(function(name){ return selected.has(name); });
    if(!against.length) return null;

    var card = source.cloneNode(true);
    var conflict = mine.length && against.length;
    var net = mine.length - against.length;
    card.dataset.for = JSON.stringify(mine);
    card.dataset.against = JSON.stringify(against);
    card.dataset.exp = against.length;
    card.dataset.net = net;
    card.dataset.tier = conflict ? "divided" : (against.length >= 2 ? "multi" : "single");

    card.querySelectorAll(".stake-row").forEach(function(row){
      var shown = 0;
      row.querySelectorAll(".chip").forEach(function(chip){
        chip.hidden = !selected.has(chip.title);
        var ref = chip.closest(".matchup-ref");
        if(ref) ref.hidden = chip.hidden;
        if(!chip.hidden) shown += 1;
      });
      row.hidden = shown === 0;
    });

    var fig = card.querySelector(".fig");
    fig.replaceChildren();
    if(conflict){
      fig.appendChild(el("div", "fg " + (net === 0 ? "zip" : (net > 0 ? "pos" : "neg")),
        net === 0 ? "even" : (net > 0 ? "+" + net : String(net))));
      fig.appendChild(el("div", "fl", "net"));
    } else {
      fig.appendChild(el("div", "fg neg", "×" + against.length));
      fig.appendChild(el("div", "fl", against.length === 1 ? "matchup" : "matchups"));
    }

    var detail = card.querySelector(".detail");
    detail.replaceChildren();
    addDetail(detail, "You start " + card.dataset.name + " in:", mine, false);
    addDetail(detail, "You face " + card.dataset.name + " in:", against, true);
    var explanation = conflict ? (net === 0 ? "The stakes are even across the leagues currently shown." :
      "Net exposure is " + (net > 0 ? "+" : "") + net + ": starts minus opposing lineups.") :
      "This player appears in " + against.length + " opposing starting lineup" + (against.length === 1 ? "." : "s.");
    detail.appendChild(el("div", "detail-row", explanation));
    return card;
  }

  function updateSummary(all){
    var divided = all.filter(function(c){ return c.dataset.tier === "divided"; }).length;
    var doubled = all.filter(function(c){ return c.dataset.tier === "multi"; }).length;
    var open = all.filter(function(c){ return c.dataset.locked !== "1"; }).length;
    document.querySelector("[data-facing-count]").textContent = all.length;
    document.querySelector("[data-divided-count]").textContent = divided;
    document.querySelector("[data-doubled-count]").textContent = doubled;
    document.querySelector("[data-open-count]").textContent = open;

    var upcoming = all.filter(function(c){ return c.dataset.locked !== "1" && c.dataset.ts !== "9999"; })
      .sort(function(a,b){ return a.dataset.ts.localeCompare(b.dataset.ts); });
    var box = document.querySelector(".next-lock");
    var clock = box.querySelector("[data-countdown]");
    var label = box.querySelector("[data-next-label]");
    var copy = box.querySelector("[data-next-copy]");
    if(upcoming.length){
      var ts = upcoming[0].dataset.ts;
      var atWave = upcoming.filter(function(c){ return c.dataset.ts === ts; });
      box.dataset.nextLock = ts;
      label.textContent = upcoming[0].dataset.wave + " · " + atWave.length + " player" + (atWave.length === 1 ? "" : "s");
      copy.textContent = "Still actionable in this kickoff wave";
    } else {
      box.removeAttribute("data-next-lock");
      clock.textContent = "All locked";
      label.textContent = "No upcoming player locks";
      copy.textContent = all.length ? "Every displayed threat has kicked off." : "Select a league to show its threats.";
    }
  }

  function cards(){
    var selected = selectedLeagues();
    var effective = sourceCards.map(function(c){ return prepareCard(c, selected); })
      .filter(function(c){ return c !== null; });
    updateSummary(effective);
    return effective.filter(function(c){
      if(filter === "open") return c.dataset.locked !== "1";
      if(filter !== "all") return c.dataset.pos === filter;
      return true;
    });
  }

  var CMP = {
    exp:  function(a,b){ return (+b.dataset.exp - +a.dataset.exp)
                             || (+a.dataset.net - +b.dataset.net)
                             || a.dataset.name.localeCompare(b.dataset.name); },
    time: function(a,b){ return a.dataset.ts.localeCompare(b.dataset.ts)
                             || a.dataset.name.localeCompare(b.dataset.name); },
    name: function(a,b){ return a.dataset.name.localeCompare(b.dataset.name); },
    pos:  function(a,b){ var o={QB:0,RB:1,WR:2,TE:3};
                         return (o[a.dataset.pos]-o[b.dataset.pos])
                             || a.dataset.name.localeCompare(b.dataset.name); }
  };

  function el(tag, cls, text){
    var n = document.createElement(tag);
    if(cls) n.className = cls;
    if(text != null) n.textContent = text;   // never innerHTML: names are untrusted
    return n;
  }

  function group(title, count, note, els, status, color){
    var d = el("div", "grp");
    if(color){ d.className = "grp lg-grp"; d.style.setProperty("--lc", color); }
    var h = el("h2", null, null);
    if(color){ h.appendChild(el("span", "dot")); }
    h.appendChild(document.createTextNode(title));
    h.appendChild(document.createTextNode(" "));
    h.appendChild(el("span", "n", count));
    if(status){ h.appendChild(el("span", "st " + status.cls, status.text)); }
    d.appendChild(h);
    if(note){ d.appendChild(el("p", "sub", note)); }
    els.forEach(function(e){ d.appendChild(e); });
    return d;
  }

  function empty(message){
    stage.appendChild(el("div", "empty", message));
  }

  function leaguesFor(card){
    return jsonList(card, "against");
  }

  function build(){
    var all = cards();
    all.sort(CMP[sort]);
    stage.replaceChildren();

    if(!all.length){
      empty(filter === "open" ? "No unlocked threats remain." :
        (filter === "all" ? "No opposing skill starters were found." : "No " + filter + " threats this week."));
      return;
    }

    if(view === "kickoff"){
      var order = [], byWave = {};
      all.forEach(function(c){
        var w = c.dataset.wave;
        if(!byWave[w]){ byWave[w] = []; order.push(w); }
        byWave[w].push(c);
      });
      order.sort(function(a,b){
        return byWave[a][0].dataset.ts.localeCompare(byWave[b][0].dataset.ts); });
      order.forEach(function(w){
        var els = byWave[w];
        var shut = els[0].dataset.locked === "1";
        stage.appendChild(group(w, els.length, "", els,
          { cls: shut ? "shut" : "open", text: shut ? "locked" : "still open" }));
      });
      return;
    }

    if(view === "league"){
      var selected = selectedLeagues();
      var groups = 0;
      leagueMeta.forEach(function(L){
        if(!selected.has(L.name)) return;
        var els = [];
        all.forEach(function(c){
          if(leaguesFor(c).indexOf(L.name) !== -1){
            els.push(c.cloneNode(true));
          }
        });
        if(!els.length) return;
        groups += 1;
        var divided = els.filter(function(c){ return c.dataset.tier === "divided"; }).length;
        var open = els.filter(function(c){ return c.dataset.locked !== "1"; }).length;
        var summary = "vs " + L.opp + " · " + divided + " divided · " + open + " open";
        stage.appendChild(group(L.code + " · " + L.name, els.length,
          summary, els, null, L.color));
      });
      if(!groups) empty("No players match this league view and filter.");
      return;
    }

    var tiers = [
      ["divided", "Divided", "You start him and you face him. Net is your true stake."],
      ["multi", "Doubled up", "One big game costs you more than one matchup."],
      ["single", "Facing", ""]
    ];
    var groups = 0;
    tiers.forEach(function(t){
      var els = all.filter(function(c){ return c.dataset.tier === t[0]; });
      if(!els.length) return;
      groups += 1;
      stage.appendChild(group(t[1], els.length, t[2], els, null));
    });
    if(!groups) empty("No threats match this filter.");
  }

  function press(sel, key, val){
    document.querySelectorAll(sel).forEach(function(b){
      b.setAttribute("aria-pressed", String(b.dataset[key] === val));
    });
  }

  document.querySelectorAll("[data-view]").forEach(function(b){
    b.addEventListener("click", function(){
      view = b.dataset.view; press("[data-view]", "view", view);
      build();
    });
  });
  document.querySelectorAll("[data-sort]").forEach(function(b){
    b.addEventListener("click", function(){
      sort = b.dataset.sort; press("[data-sort]", "sort", sort); build();
    });
  });
  document.querySelectorAll("[data-filter]").forEach(function(b){
    b.addEventListener("click", function(){
      filter = b.dataset.filter; press("[data-filter]", "filter", filter); build();
    });
  });
  document.querySelectorAll("[data-league-check]").forEach(function(input){
    input.addEventListener("change", function(){
      var hidden = Array.prototype.slice.call(document.querySelectorAll("[data-league-check]:not(:checked)"))
        .map(function(box){ return box.dataset.leagueCheck; });
      try { localStorage.setItem("fm-hidden-leagues", JSON.stringify(hidden)); } catch(e) {}
      build();
      updateCountdown();
    });
  });

  try {
    var hiddenLeagues = JSON.parse(localStorage.getItem("fm-hidden-leagues") || "[]");
    document.querySelectorAll("[data-league-check]").forEach(function(input){
      input.checked = hiddenLeagues.indexOf(input.dataset.leagueCheck) === -1;
    });
  } catch(e) {}

  stage.addEventListener("click", function(event){
    var button = event.target.closest(".card-main");
    if(!button) return;
    var detail = button.nextElementSibling;
    var open = button.getAttribute("aria-expanded") === "true";
    button.setAttribute("aria-expanded", String(!open));
    detail.hidden = open;
  });

  function updateCountdown(){
    var box = document.querySelector("[data-next-lock]");
    if(!box) return;
    var target = new Date(box.dataset.nextLock).getTime();
    var mins = Math.max(0, Math.ceil((target - Date.now()) / 60000));
    var label = box.querySelector("[data-countdown]");
    if(mins <= 0) label.textContent = "Locking now";
    else if(mins < 60) label.textContent = mins + "m to lock";
    else label.textContent = Math.floor(mins / 60) + "h " + (mins % 60) + "m";
  }
  build();
  updateCountdown();
  setInterval(updateCountdown, 60000);
})();
"""


def sms_text(table: dict[str, Exposure], week: int, wave, matchups) -> str:
    """Short digest for the gateway. Kept tight — carriers split long bodies."""
    conf = ledger.conflicts(table)
    multi = ledger.multi_exposure(table)
    facing = [e for e in table.values() if e.against_leagues]
    label = wave.label if wave else "now"

    lines = [f"FM W{week} {label}", f"Facing {len(facing)}"]
    if multi:
        names = ", ".join(e.player.name.split()[-1] for e in multi[:3])
        lines.append(f"x2+: {names}")
    for e in conf[:2]:
        stake = "EVEN" if e.net == 0 else f"{e.net:+d}"
        lines.append(f"! {e.player.name.split()[-1]} {stake}")
    for m in [x for x in matchups if x.error]:
        why = "AUTH" if ("sign-in" in m.error or "private" in m.error) else "FAIL"
        lines.append(f"[{why}] {m.league_name}")
    if config.BOARD_BASE_URL:
        lines.append(config.BOARD_BASE_URL)
    return "\n".join(lines)
