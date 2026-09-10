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
from .rankings import UNRANKED, label as rank_label
from .models import Exposure, LeagueMatchup

DISPLAY_TZ = ZoneInfo(config.DISPLAY_TIMEZONE)

LEAGUES: dict[str, dict] = {}
NFL_TEAMS = (
    "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE",
    "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
    "LV", "LAC", "LAR", "MIA", "MIN", "NE", "NO", "NYG",
    "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS",
)

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
/* ── game view: one NFL game, all three relationships ─── */
.game-grp{margin-bottom:9px;border:1px solid var(--rule);border-radius:4px;
  background:var(--card2);overflow:hidden}
.game-grp > summary{display:flex;align-items:center;gap:9px;flex-wrap:nowrap;
  padding:10px 12px;cursor:pointer;list-style:none;
  background:linear-gradient(96deg,var(--card1) 0%,var(--card2) 70%)}
.game-grp > summary::-webkit-details-marker{display:none}
.game-grp > summary::before{content:"▸";color:var(--faint);font-size:11px;
  flex:none;transition:transform .12s ease}
.game-grp[open] > summary::before{transform:rotate(90deg)}
.game-grp > summary:hover{background:var(--card1)}
.game-grp > summary:focus-visible{outline:2px solid var(--for);outline-offset:-2px}
.gname{display:flex;align-items:center;gap:6px;font-weight:700;font-size:17px;
  letter-spacing:-.01em;text-transform:uppercase;flex:none}
.tlogo{width:24px;height:24px;object-fit:contain;flex:none}
.tabbr{font:700 15px/1 "Barlow Condensed",sans-serif;letter-spacing:.02em}
.gat{color:var(--faint);font-size:12px;font-weight:500}
.gtime{font:500 10px/1 ui-monospace,"SF Mono",Menlo,monospace;letter-spacing:.06em;
  color:var(--mut);text-transform:uppercase;white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis;min-width:0}
.gtally{margin-left:auto;display:flex;gap:4px;flex-wrap:nowrap;flex:none}
.gt{display:inline-flex;align-items:center;gap:3px;
  font:700 11px/1 ui-monospace,"SF Mono",Menlo,monospace;font-variant-numeric:tabular-nums;
  padding:4px 6px;border-radius:2px;white-space:nowrap}
.gsym{font-size:11px;line-height:1}
.gt.cheer{background:rgba(72,201,232,.16);color:var(--for)}
.gt.divided{background:rgba(255,176,32,.16);color:var(--amber)}
.gt.against{background:rgba(255,107,53,.16);color:var(--against)}
.gt.locked{background:transparent;color:var(--faint);
  box-shadow:inset 0 0 0 1px var(--rule)}
.gt.final{background:transparent;color:var(--faint);
  box-shadow:inset 0 0 0 1px var(--rule)}
.game-grp.done > summary .gname{opacity:.72}
.game-grp.done > summary .tlogo{filter:grayscale(.85)}
.gsec{padding:2px 10px 9px}
.gsec > h3{margin:11px 0 6px;font:600 10px/1 ui-monospace,"SF Mono",Menlo,monospace;
  letter-spacing:.19em;text-transform:uppercase}
.gsec.cheer > h3{color:var(--for)}
.gsec.divided > h3{color:var(--amber)}
.gsec.against > h3{color:var(--against)}
.rk{font:600 9.5px/1 ui-monospace,"SF Mono",Menlo,monospace;letter-spacing:.08em;
  color:var(--faint);padding:2px 4px;border-radius:2px;
  box-shadow:inset 0 0 0 1px var(--rule)}
.err{background:var(--warnbg);border:1px solid var(--warn);border-left-width:4px;
  color:var(--warn);padding:10px 13px;margin-bottom:6px;font-size:13.5px;
  font-family:system-ui,sans-serif}
.err b{font-weight:600}
.empty{color:var(--faint);font-size:13px;padding:11px 0;font-family:system-ui,sans-serif;
  font-style:italic}
footer{margin-top:32px;padding-top:13px;border-top:1px solid var(--rule);
  font:400 10.5px/1.6 ui-monospace,"SF Mono",Menlo,monospace;letter-spacing:.09em;
  color:var(--faint)}
@media (max-width:440px){
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
.scope-tabs{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:5px;margin:13px 0 0}
.scope-tabs button{min-width:0;min-height:42px;padding:6px 5px;border:1px solid var(--rule);
  border-radius:var(--radius);background:var(--surface);color:var(--mut);cursor:pointer;
  font:800 13px/1.05 var(--display)}
.scope-tabs button[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:var(--bg)}
.scope-tabs small{display:block;margin-top:3px;font:700 9px/1 var(--mono);letter-spacing:.03em}
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
.controls{position:relative;margin:7px 0 0;padding:0 0 10px;background:var(--bg);border-bottom:1px solid var(--rule)}
.control-strip{display:grid;grid-template-columns:repeat(3,minmax(0,1fr)) auto;gap:5px;padding:7px;
  border:1px solid var(--rule);border-radius:var(--radius);background:var(--surface)}
.select-control{display:block;min-width:0}.select-control>span{display:block;margin:0 0 4px;
  color:var(--faint);font:750 9px/1 var(--mono);letter-spacing:.07em;text-transform:uppercase}
.select-control select{width:100%;height:32px;padding:0 23px 0 8px;border:1px solid var(--rule);
  border-radius:var(--radius);background:var(--bg);color:var(--ink);cursor:pointer;
  font:750 12px/1 var(--display)}
.select-control select:focus-visible{outline:3px solid var(--for);outline-offset:1px}
.bar{display:grid;grid-template-columns:55px minmax(0,1fr);gap:7px;align-items:start;padding:3px 0;min-width:0}
.bar .cap{font-size:11px;line-height:44px;font-weight:750;letter-spacing:.08em;color:var(--faint);margin:0}
.choices{display:flex;gap:6px;align-items:center;flex-wrap:wrap;min-width:0;max-width:100%}
.bar button{min-height:44px;padding:9px 12px;background:var(--surface);color:var(--mut);
  border-color:var(--rule);border-radius:var(--radius);font-family:var(--display);
  font-size:13px;line-height:1;font-weight:750;letter-spacing:.025em;text-transform:none}
.bar button[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:var(--bg)}
.filter-drawers{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:5px;margin-top:5px}
.filter-drawer{border:1px solid var(--rule);border-radius:var(--radius);background:var(--surface)}
.filter-drawer[open]{grid-column:1/-1}
.filter-drawer summary{display:flex;align-items:center;justify-content:space-between;gap:8px;min-height:38px;padding:7px 10px;
  cursor:pointer;color:var(--ink);font:800 13px/1 var(--display);list-style-position:inside}
.filter-drawer summary span{margin-left:auto;color:var(--faint);font:700 9px/1 var(--mono);white-space:nowrap}
.filter-drawer[open] summary{border-bottom:1px solid var(--rule)}
.league-filter .legend{display:flex;align-items:center;gap:5px;padding:7px;flex-wrap:wrap}
.league-filter .lgd{min-height:30px;padding:5px 8px 5px 6px;gap:5px;flex:1 1 62px;
  justify-content:center;background:var(--bg);border-left-width:3px}
.league-filter .lgd input{width:15px;height:15px}
.league-filter .lgd .code{font-size:10px}
.team-tools{display:flex;gap:6px;padding:8px 8px 3px}
.team-tools button{min-height:32px;padding:5px 10px;border:1px solid var(--rule);border-radius:var(--radius);
  background:var(--surface2);color:var(--mut);cursor:pointer;font:750 12px/1 var(--display)}
.team-grid{display:grid;grid-template-columns:repeat(8,minmax(0,1fr));gap:4px;padding:6px 8px 9px}
.team-choice{position:relative;min-width:0}.team-choice input{position:absolute;opacity:0;pointer-events:none}
.team-choice span{display:flex;align-items:center;justify-content:center;min-height:30px;padding:3px 1px;
  border:1px solid var(--rule);border-radius:2px;background:var(--bg);color:var(--faint);
  cursor:pointer;font:750 10px/1 var(--mono)}
.team-choice input:checked+span{border-color:var(--for);background:rgba(83,214,238,.12);color:var(--for)}
.team-choice input:focus-visible+span{outline:3px solid var(--for);outline-offset:2px}
.thin-toggle{position:relative;display:flex;align-items:flex-end;min-width:61px;cursor:pointer}
.thin-toggle input{position:absolute;opacity:0;pointer-events:none}
.thin-toggle span{display:flex;align-items:center;justify-content:center;width:100%;height:32px;padding:0 9px;
  border:1px solid var(--rule);border-radius:var(--radius);background:var(--bg);color:var(--mut);
  font:800 12px/1 var(--display)}
.thin-toggle span:before{content:"↔";margin-right:5px;font-family:var(--mono)}
.thin-toggle input:checked+span{border-color:var(--for);background:rgba(83,214,238,.12);color:var(--for)}
.thin-toggle input:focus-visible+span{outline:3px solid var(--for);outline-offset:1px}
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
.card .body{padding:9px 6px 8px 10px}.nm{font-family:var(--display);font-size:21px;font-weight:800;line-height:1.02}
.mt{display:flex;align-items:center;gap:7px;flex-wrap:wrap;font-size:12px;line-height:1.25;
  font-weight:650;letter-spacing:.025em;color:var(--mut);margin-top:4px}
.lock{display:inline-flex;padding:3px 6px;border:1px solid var(--faint);border-radius:3px;
  color:var(--faint);font-size:10px;font-weight:800;letter-spacing:.06em;text-transform:uppercase}
.overlap-badge{display:inline-flex;padding:3px 6px;border:1px solid var(--accent);border-radius:3px;
  color:var(--accent);font-size:10px;font-weight:800;letter-spacing:.05em;text-transform:uppercase}
.overlap-badge[hidden]{display:none!important}
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
body.thin .card{margin-bottom:3px}
body.thin .card-main{grid-template-columns:32px minmax(0,1fr) auto;min-height:38px;cursor:default}
body.thin .card .ph,body.thin .card .noph{min-height:38px;height:38px}
body.thin .card .noph{font-size:13px}
body.thin .card .body{display:flex;align-items:center;gap:5px;min-width:0;padding:4px 6px}
body.thin .nm{flex:1;min-width:55px;font-size:0;line-height:1;white-space:nowrap}
body.thin .nm:after{content:attr(data-short);font-size:16px}
body.thin .mt{flex:none;margin:0}body.thin .mt>span:first-child{display:none}
body.thin .lock,body.thin .overlap-badge{padding:2px 4px;font-size:8px}
body.thin .side{display:flex;flex:none;gap:3px;margin:0;white-space:nowrap}
body.thin .stake-row{flex-wrap:nowrap;gap:2px}
body.thin .stake-kind{display:none}
body.thin .chip,body.thin .chip.ghost{min-height:17px;padding:2px 4px;font-size:8.5px}
body.thin .card.has-overlap .stake-row .chip{position:relative;margin-right:2px}
body.thin .card.has-overlap .stake-row .chip:after{position:absolute;right:-4px;top:-5px;
  display:flex;align-items:center;justify-content:center;width:10px;height:10px;border-radius:50%;
  color:#fff;box-shadow:0 0 0 1px var(--surface);font:900 8px/1 var(--mono)}
body.thin .card.has-overlap .stake-row:has(.stake-kind.for) .chip:after{content:"✓";background:#16A34A}
body.thin .card.has-overlap .stake-row:has(.stake-kind.against) .chip:after{content:"×";background:#EF4444}
body.thin .fig{min-width:36px;padding:4px 6px 4px 2px}body.thin .fg{font-size:18px}
body.thin .fl{font-size:7px;margin-top:2px}body.thin .chev,body.thin .detail{display:none!important}
.empty{color:var(--faint);font-size:14px;padding:15px;background:var(--surface);
  border:1px dashed var(--rule);border-radius:var(--radius);font-family:var(--body);font-style:normal}
.err{font-size:14px;border-radius:var(--radius);font-family:var(--body)}
footer{font-size:12px;letter-spacing:.035em;color:var(--faint)}
@media(max-width:440px){
  .wrap{padding-left:12px;padding-right:12px}.thesis{font-size:35px}.legend{grid-template-columns:1fr}
  .bar{grid-template-columns:48px 1fr}.bar button{padding-left:10px;padding-right:10px}
  .card-main{grid-template-columns:58px minmax(0,1fr) auto 22px}.nm{font-size:19px}.fg{font-size:24px}.fig{min-width:45px}
  /* Four controls across a 390px screen leaves ~94px each, and the base rule's
     23px right padding eats a quarter of that. Two rows of two gives each
     control room for its longest label. */
  .control-strip{grid-template-columns:repeat(2,minmax(0,1fr));padding:6px;gap:6px}
  .select-control select{padding:0 20px 0 7px;font-size:12px;text-overflow:ellipsis}
  .thin-toggle{min-width:0}.thin-toggle span{padding:0 6px;font-size:12px}
  /* "32 of 32 selected" cannot share a row at this width. */
  .filter-drawers{grid-template-columns:1fr;gap:6px}
  /* 8 team chips across is ~40px each; 5 keeps the abbreviations legible. */
  .team-grid{grid-template-columns:repeat(5,minmax(0,1fr))}
  .scope-tabs button{font-size:12px;padding:6px 3px}.scope-tabs small{font-size:8.5px}
}
@media(prefers-reduced-motion:reduce){*{transition:none!important;scroll-behavior:auto!important}}
"""

FONT_LINK = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
             'family=Barlow+Condensed:wght@500;600;700;800&display=swap">')


def _plural(n: int) -> str:
    return f"{n} player" if n == 1 else f"{n} players"


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
    rank_badge = (f'<span class="rk" title="Rest-of-season consensus rank">'
                  f'{rank_label(e.rank)}</span>') if e.rank < UNRANKED else ''
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
                  f'{chips(e.against_leagues)}</div>')

    src = url_for(e.player.name, e.player.position)
    initials = "".join(p[0] for p in e.player.name.split()[:2]).upper()
    name_parts = e.player.name.split()
    short_name = (f'{name_parts[0][0]}. {" ".join(name_parts[1:])}'
                  if len(name_parts) > 1 else e.player.name)
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
    lock_badge = ''   # kickoff time already conveys this; a badge added noise
    overlap_badge = (f'<span class="overlap-badge"'
                     f'{"" if e.is_conflict else " hidden"}>Overlap</span>')

    return (
        f'<article class="card{" lk" if e.locked else ""}{" has-overlap" if e.is_conflict else ""}" '
        f'style="--tc:{rail_color(e.player.team)}"'
        f' data-key="{_esc(e.player.key)}" data-tier="{_tier(e)}"'
        f' data-exp="{len(e.against_leagues)}" data-net="{e.net}"'
        f' data-name="{_esc(e.player.name)}" data-pos="{_esc(e.player.position)}"'
        f' data-team="{_esc(e.player.team)}"'
        f' data-rank="{e.rank}" data-game="{_esc(e.game or "TBD")}"'
        f' data-wave="{_esc(wave)}" data-ts="{kick.isoformat() if kick else "9999"}"'
        f' data-locked="{"1" if e.locked else "0"}"'
        f' data-against="{against_json}" data-for="{for_json}">'
        f'<button class="card-main" type="button" aria-expanded="false" '
        f'aria-label="Show why {_esc(e.player.name)} matters">'
        f'{photo}<div class="body"><div class="nm" data-short="{_esc(short_name)}">{_esc(e.player.name)}</div>'
        f'<div class="mt"><span>{meta}</span>{rank_badge}{lock_badge}{overlap_badge}</div>'
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
    facing = [e for e in table.values() if e.against_leagues]
    multi = sorted((e for e in facing if len(e.against_leagues) >= 2),
                   key=lambda e: (-len(e.against_leagues), e.player.name))
    single = sorted((e for e in facing if len(e.against_leagues) == 1),
                    key=lambda e: e.player.name)
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
    relevant = sorted(
        (e for e in table.values() if e.for_leagues or e.against_leagues),
        key=lambda e: (-len(e.against_leagues), e.player.name),
    )
    cheering = [e for e in relevant if e.for_leagues]

    p = ['<div class="wrap"><div class="top">',
         f'<div class="eyebrow">Week {week} &middot; {_esc(label)} &middot; '
         f'{len(ok)} league{"s" if len(ok) != 1 else ""}</div>',
         f'<h1 class="thesis"><em data-facing-count>{len(facing)}</em> '
         '<span data-scope-copy>can hurt you</span></h1>',
         '<div class="tally">',
         f'<div><b data-divided-count>{len(multi)}</b> <span data-first-label>doubled</span></div>',
         f'<div><b data-doubled-count>{len(single)}</b> <span data-second-label>single</span></div>',
         f'<div><b data-open-count>{open_n}</b> <span>open</span></div>',
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

    p.append('<nav class="scope-tabs" aria-label="Player view">'
             f'<button data-scope="against" aria-pressed="true">Against<small>{_plural(len(facing))}</small></button>'
             f'<button data-scope="cheer" aria-pressed="false">Cheer for<small>{_plural(len(cheering))}</small></button>'
             f'<button data-scope="overlap" aria-pressed="false">Divided<small>{_plural(len(conf))}</small></button>'
             '</nav>')

    if errs:
        p += [f'<div class="err" style="margin-top:12px"><b>{_esc(m.league_name)}</b> &mdash; '
              f'{_esc(m.error)}</div>' for m in errs]

    p += ['<div class="controls">',
          '<div class="control-strip">',
          '<label class="select-control"><span>Group</span><select data-view-select aria-label="Group players">'
          '<option value="threat">Threat</option><option value="kickoff">Kickoff</option>'
          '<option value="league">League</option>'
          '<option value="game" selected>Game</option></select></label>',
          '<label class="select-control"><span>Sort</span><select data-sort-select aria-label="Sort players">'
          '<option value="exp">Impact</option><option value="time">Kickoff</option>'
          '<option value="rank">Ranking</option>'
          '<option value="name">Name</option><option value="pos">Position</option></select></label>',
          '<label class="select-control"><span>Show</span><select data-filter-select aria-label="Filter players">'
          '<option value="all">All</option><option value="open">Open</option><option value="QB">QB</option>'
          '<option value="RB">RB</option><option value="WR">WR</option><option value="TE">TE</option></select></label>',
          '<label class="thin-toggle"><input type="checkbox" data-thin-check>'
          '<span>Slim</span></label></div>',
          '<div class="filter-drawers">',
          f'<details class="filter-drawer league-filter"><summary>Leagues <span data-league-count>{len(ok)} of {len(ok)}</span></summary>',
          '<div class="legend" role="group" aria-label="Leagues shown">']
    for m in ok:
        meta = LEAGUES[m.league_name]
        p.append(f'<label class="lgd" style="--lc:{meta["color"]}" title="{_esc(m.league_name)}">'
                 f'<input type="checkbox" data-league-check="{_esc(m.league_name)}" checked '
                 f'aria-label="Show {_esc(m.league_name)}">'
                 f'<span class="code">{_esc(meta["code"])}</span></label>')
    p += ['</div></details>',
          '<details class="filter-drawer team-filter"><summary>NFL teams <span data-team-count>32 of 32 selected</span></summary>',
          '<div class="team-tools"><button type="button" data-teams="all">Select all</button>'
          '<button type="button" data-teams="none">Clear all</button></div>',
          '<div class="team-grid" role="group" aria-label="NFL teams shown">']
    for team in NFL_TEAMS:
        p.append(f'<label class="team-choice"><input type="checkbox" data-team-check="{team}" checked '
                 f'aria-label="Show {team} players"><span>{team}</span></label>')
    p += ['</div></details></div></div>',
          '<div id="stage">']

    p.append(_group("Doubled up", len(multi),
                    "One big game costs you more than one matchup.",
                    "".join(_card(e) for e in multi),
                    "Nobody is facing you in two leagues."))
    p.append(_group("Facing", len(single), "",
                    "".join(_card(e) for e in single),
                    "No other skill starters against you."))
    p.append('</div>')
    p.append('<template id="card-source">')
    p.extend(_card(e) for e in relevant)
    p.append('</template>')

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
  var source = document.getElementById("card-source");
  if(!stage || !source) return;
  // Every view starts from one immutable set. This includes owned-only players,
  // which are intentionally absent from the no-script Against fallback.
  var sourceCards = Array.prototype.slice.call(source.content.querySelectorAll(".card"))
    .map(function(c){ return c.cloneNode(true); });
  var leagueMeta = JSON.parse(document.getElementById("meta").textContent).leagues;
  var scope = "against", view = "game", sort = "exp", filter = "all";

  function jsonList(card, key){
    try { return JSON.parse(card.dataset[key] || "[]"); }
    catch(e) { return []; }
  }

  function selectedLeagues(){
    return new Set(Array.prototype.slice.call(document.querySelectorAll("[data-league-check]:checked"))
      .map(function(input){ return input.dataset.leagueCheck; }));
  }

  function selectedTeams(){
    return new Set(Array.prototype.slice.call(document.querySelectorAll("[data-team-check]:checked"))
      .map(function(input){ return input.dataset.teamCheck; }));
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

  function belongs(mine, against, wantedScope){
    if(wantedScope === "any") return mine.length > 0 || against.length > 0;
    if(wantedScope === "cheer") return mine.length > 0;
    if(wantedScope === "overlap") return mine.length > 0 && against.length > 0;
    return against.length > 0;
  }

  function prepareCard(sourceCard, selected, scopeOverride){
    var useScope = scopeOverride || scope;
    var mine = jsonList(sourceCard, "for").filter(function(name){ return selected.has(name); });
    var against = jsonList(sourceCard, "against").filter(function(name){ return selected.has(name); });
    if(!belongs(mine, against, useScope)) return null;

    var card = sourceCard.cloneNode(true);
    var conflict = mine.length > 0 && against.length > 0;
    var net = mine.length - against.length;
    card.dataset.for = JSON.stringify(mine);
    card.dataset.against = JSON.stringify(against);
    card.dataset.exp = against.length;
    card.dataset.own = mine.length;
    card.dataset.net = net;
    card.dataset.overlap = conflict ? "1" : "0";
    card.classList.toggle("has-overlap", conflict);
    card.dataset.tier = against.length >= 2 ? "multi" : "single";
    if(scope === "cheer") card.dataset.tier = mine.length >= 2 ? "multi" : "single";
    if(scope === "overlap") card.dataset.tier = net > 0 ? "positive" : (net < 0 ? "negative" : "even");
    card.dataset.impact = scope === "cheer" ? mine.length :
      (scope === "overlap" ? mine.length + against.length : against.length);

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
    var badge = card.querySelector(".overlap-badge");
    if(badge) badge.hidden = !conflict;

    var fig = card.querySelector(".fig");
    fig.replaceChildren();
    if(conflict){
      fig.appendChild(el("div", "fg " + (net === 0 ? "zip" : (net > 0 ? "pos" : "neg")),
        net === 0 ? "even" : (net > 0 ? "+" + net : String(net))));
      fig.appendChild(el("div", "fl", "net"));
    } else if(scope === "cheer") {
      fig.appendChild(el("div", "fg pos", "×" + mine.length));
      fig.appendChild(el("div", "fl", mine.length === 1 ? "start" : "starts"));
    } else {
      fig.appendChild(el("div", "fg neg", "×" + against.length));
      fig.appendChild(el("div", "fl", against.length === 1 ? "matchup" : "matchups"));
    }

    var detail = card.querySelector(".detail");
    detail.replaceChildren();
    addDetail(detail, "You start " + card.dataset.name + " in:", mine, false);
    addDetail(detail, "You face " + card.dataset.name + " in:", against, true);
    var explanation;
    if(conflict) explanation = net === 0 ? "The stakes are even across the leagues currently shown." :
      "Net exposure is " + (net > 0 ? "+" : "") + net + ": starts minus opposing lineups.";
    else if(scope === "cheer") explanation = "You start this player in " + mine.length + " league" + (mine.length === 1 ? "." : "s.");
    else explanation = "This player appears in " + against.length + " opposing starting lineup" + (against.length === 1 ? "." : "s.");
    detail.appendChild(el("div", "detail-row", explanation));
    return card;
  }

  function updateScopeCounts(selected, teams){
    var totals = {against:0, cheer:0, overlap:0};
    sourceCards.forEach(function(card){
      if(!teams.has(card.dataset.team)) return;
      var mine = jsonList(card, "for").filter(function(name){ return selected.has(name); });
      var against = jsonList(card, "against").filter(function(name){ return selected.has(name); });
      Object.keys(totals).forEach(function(kind){ if(belongs(mine, against, kind)) totals[kind] += 1; });
    });
    document.querySelectorAll("[data-scope]").forEach(function(button){
      button.querySelector("small").textContent = totals[button.dataset.scope] + " players";
    });
  }

  function updateSummary(all){
    var first, second, copy, firstLabel, secondLabel;
    if(scope === "cheer"){
      first = all.filter(function(c){ return +c.dataset.own >= 2; }).length;
      second = all.filter(function(c){ return +c.dataset.own === 1; }).length;
      copy = "to cheer for"; firstLabel = "multi-start"; secondLabel = "single-start";
    } else if(scope === "overlap") {
      first = all.filter(function(c){ return +c.dataset.net > 0; }).length;
      second = all.filter(function(c){ return +c.dataset.net < 0; }).length;
      copy = "pull both ways"; firstLabel = "lean for"; secondLabel = "lean against";
    } else {
      first = all.filter(function(c){ return c.dataset.tier === "multi"; }).length;
      second = all.filter(function(c){ return c.dataset.tier === "single"; }).length;
      copy = "can hurt you"; firstLabel = "doubled"; secondLabel = "single";
    }
    var open = all.filter(function(c){ return c.dataset.locked !== "1"; }).length;
    document.querySelector("[data-facing-count]").textContent = all.length;
    document.querySelector("[data-scope-copy]").textContent = copy;
    document.querySelector("[data-divided-count]").textContent = first;
    document.querySelector("[data-first-label]").textContent = firstLabel;
    document.querySelector("[data-doubled-count]").textContent = second;
    document.querySelector("[data-second-label]").textContent = secondLabel;
    document.querySelector("[data-open-count]").textContent = open;

    var upcoming = all.filter(function(c){ return c.dataset.locked !== "1" && c.dataset.ts !== "9999"; })
      .sort(function(a,b){ return a.dataset.ts.localeCompare(b.dataset.ts); });
    var box = document.querySelector(".next-lock");
    var clock = box.querySelector("[data-countdown]");
    var label = box.querySelector("[data-next-label]");
    var nextCopy = box.querySelector("[data-next-copy]");
    if(upcoming.length){
      var ts = upcoming[0].dataset.ts;
      var atWave = upcoming.filter(function(c){ return c.dataset.ts === ts; });
      box.dataset.nextLock = ts;
      label.textContent = upcoming[0].dataset.wave + " · " + atWave.length + " player" + (atWave.length === 1 ? "" : "s");
      nextCopy.textContent = "Still actionable in this kickoff wave";
    } else {
      box.removeAttribute("data-next-lock");
      clock.textContent = "All locked";
      label.textContent = "No upcoming player locks";
      nextCopy.textContent = all.length ? "Every displayed player has kicked off." : "Adjust the league or team filters to show players.";
    }
  }

  function cards(){
    var selected = selectedLeagues();
    var teams = selectedTeams();
    updateScopeCounts(selected, teams);
    document.querySelector("[data-league-count]").textContent = selected.size + " of " + leagueMeta.length;
    document.querySelector("[data-team-count]").textContent = teams.size + " of 32 selected";
    var effective = sourceCards.map(function(c){ return prepareCard(c, selected); })
      .filter(function(c){ return c !== null && teams.has(c.dataset.team); });
    updateSummary(effective);
    return effective.filter(function(c){
      if(filter === "open") return c.dataset.locked !== "1";
      if(filter !== "all") return c.dataset.pos === filter;
      return true;
    });
  }

  // Rest-of-season rank breaks ties. Unranked players carry a sentinel that
  // sorts them last rather than dropping them.
  // An NFL game runs about three hours. Past that it is history, so it sinks
  // below anything still live or upcoming.
  var GAME_RUNTIME_MS = 3 * 60 * 60 * 1000;

  function kickoffMs(ts){
    if(!ts || ts === "9999") return Infinity;
    var t = Date.parse(ts);
    return isNaN(t) ? Infinity : t;
  }

  function isFinished(ts){
    var k = kickoffMs(ts);
    return k !== Infinity && Date.now() >= k + GAME_RUNTIME_MS;
  }

  function byRank(a, b){
    return (+a.dataset.rank - +b.dataset.rank)
        || a.dataset.name.localeCompare(b.dataset.name);
  }

  var CMP = {
    exp:  function(a,b){ return (+b.dataset.impact - +a.dataset.impact)
                             || (+a.dataset.net - +b.dataset.net)
                             || byRank(a,b); },
    time: function(a,b){ return a.dataset.ts.localeCompare(b.dataset.ts)
                             || byRank(a,b); },
    name: function(a,b){ return a.dataset.name.localeCompare(b.dataset.name); },
    rank: byRank,
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

  // ESPN's own abbreviations come straight off the schedule, so they double
  // as logo slugs. WAS is the one normalisation that has to be undone.
  function logoSlug(team){
    var t = (team || "").toLowerCase();
    return t === "was" ? "wsh" : t;
  }

  function teamLogo(team){
    var img = document.createElement("img");
    img.className = "tlogo";
    img.alt = team;
    img.loading = "lazy";
    img.src = "https://a.espncdn.com/i/teamlogos/nfl/500-dark/" + logoSlug(team) + ".png";
    // If the logo will not load, fall back to the abbreviation rather than a gap.
    img.addEventListener("error", function(){
      var span = el("span", "tabbr", team);
      if(img.parentNode) img.parentNode.replaceChild(span, img);
    });
    return img;
  }

  function gameTitle(label){
    var wrap = el("span", "gname", null);
    var parts = String(label).split(" @ ");
    if(parts.length !== 2){ wrap.textContent = label; return wrap; }
    wrap.appendChild(teamLogo(parts[0]));
    wrap.appendChild(el("span", "gat", "@"));
    wrap.appendChild(teamLogo(parts[1]));
    return wrap;
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

  function empty(message){ stage.appendChild(el("div", "empty", message)); }

  function leaguesFor(card){ return jsonList(card, scope === "cheer" ? "for" : "against"); }

  function build(){
    var all = cards();
    all.sort(CMP[sort]);
    stage.replaceChildren();

    if(!all.length){
      var noun = scope === "against" ? "opponents" : (scope === "cheer" ? "starters" : "overlaps");
      empty(filter === "open" ? "No unlocked " + noun + " remain." :
        (filter === "all" ? "No " + noun + " match the current league and team filters." : "No " + filter + " " + noun + " this week."));
      return;
    }

    if(view === "kickoff"){
      var order = [], byWave = {};
      all.forEach(function(c){
        var w = c.dataset.wave;
        if(!byWave[w]){ byWave[w] = []; order.push(w); }
        byWave[w].push(c);
      });
      order.sort(function(a,b){ return byWave[a][0].dataset.ts.localeCompare(byWave[b][0].dataset.ts); });
      order.forEach(function(w){
        var els = byWave[w];
        var shut = els[0].dataset.locked === "1";
        stage.appendChild(group(w, els.length, "", els,
          { cls: shut ? "shut" : "open", text: shut ? "locked" : "still open" }));
      });
      return;
    }

    if(view === "game"){
      // Deliberately ignores the scope selector: the point of this view is to
      // see who you cheer for, who you face, and who is both, in one game.
      var selectedNames = selectedLeagues();
      var teamsPicked = selectedTeams();
      var everyone = sourceCards
        .map(function(c){ return prepareCard(c, selectedNames, "any"); })
        .filter(function(c){ return c !== null && teamsPicked.has(c.dataset.team); })
        .filter(function(c){
          if(filter === "open") return c.dataset.locked !== "1";
          if(filter !== "all") return c.dataset.pos === filter;
          return true;
        });

      var gameOrder = [], byGame = {};
      everyone.forEach(function(c){
        var g = c.dataset.game || "TBD";
        if(!byGame[g]){ byGame[g] = []; gameOrder.push(g); }
        byGame[g].push(c);
      });
      gameOrder.sort(function(a,b){
        var fa = isFinished(byGame[a][0].dataset.ts) ? 1 : 0;
        var fb = isFinished(byGame[b][0].dataset.ts) ? 1 : 0;
        return (fa - fb)
            || byGame[a][0].dataset.ts.localeCompare(byGame[b][0].dataset.ts)
            || a.localeCompare(b);
      });

      if(!gameOrder.length){ empty("No games match the current filters."); return; }

      // Rebuilds are triggered by filters and by the minute tick, so an
      // expanded game must survive them.
      var openGames = new Set(
        Array.prototype.slice.call(stage.querySelectorAll(".game-grp[open]"))
          .map(function(d){ return d.dataset.game; }));

      // data-impact is computed under the active scope, which this view
      // ignores, so each bucket is ranked on the league count that actually
      // applies to it: starts for cheering, opposing shares for against, and
      // both sides for divided. Ranking only breaks the remaining ties.
      function stakeIn(card, bucket){
        var mine = jsonList(card, "for").length;
        var opp = jsonList(card, "against").length;
        if(bucket === "cheer") return mine;
        if(bucket === "against") return opp;
        return mine + opp;
      }
      function bucketOrder(bucket){
        return function(a, b){
          if(sort !== "exp") return CMP[sort](a, b);
          return (stakeIn(b, bucket) - stakeIn(a, bucket)) || byRank(a, b);
        };
      }

      gameOrder.forEach(function(g){
        var els = byGame[g];
        var buckets = { cheer: [], divided: [], against: [] };
        els.forEach(function(c){
          var mine = jsonList(c, "for").length, opp = jsonList(c, "against").length;
          if(mine && opp) buckets.divided.push(c);
          else if(mine) buckets.cheer.push(c);
          else buckets.against.push(c);
        });
        Object.keys(buckets).forEach(function(k){
          buckets[k].sort(bucketOrder(k));
        });

        var det = el("details", "game-grp");
        det.dataset.game = g;
        if(openGames.has(g)) det.open = true;
        if(isFinished(els[0].dataset.ts)) det.classList.add("done");
        var sum = el("summary", null, null);
        sum.appendChild(gameTitle(g));
        sum.appendChild(el("span", "gtime", els[0].dataset.wave));
        var tally = el("span", "gtally");
        // Words wrapped the summary onto three lines on a phone. The symbol
        // carries the same meaning in a quarter of the width; the full wording
        // stays in the title and aria-label for anyone who needs it.
        [["cheer", buckets.cheer.length, "\u2713", "cheering for"],
         ["divided", buckets.divided.length, "=", "divided on"],
         ["against", buckets.against.length, "\u2717", "rooting against"]].forEach(function(t){
          if(!t[1]) return;
          var chip = el("span", "gt " + t[0], null);
          chip.appendChild(el("span", "gsym", t[2]));
          chip.appendChild(document.createTextNode(String(t[1])));
          chip.title = t[1] + " " + t[3];
          chip.setAttribute("aria-label", t[1] + " " + t[3]);
          tally.appendChild(chip);
        });
        if(isFinished(els[0].dataset.ts)){
          var fin = el("span", "gt final", "\u25CF");
          fin.title = "final"; fin.setAttribute("aria-label", "final");
          tally.appendChild(fin);
        }
        sum.appendChild(tally);
        det.appendChild(sum);

        [["cheer", "Cheering for", buckets.cheer],
         ["divided", "Divided", buckets.divided],
         ["against", "Rooting against", buckets.against]].forEach(function(b){
          if(!b[2].length) return;
          var sec = el("div", "gsec " + b[0]);
          sec.appendChild(el("h3", null, b[1] + " · " + b[2].length));
          b[2].forEach(function(c){ sec.appendChild(c); });
          det.appendChild(sec);
        });
        stage.appendChild(det);
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
          if(leaguesFor(c).indexOf(L.name) !== -1) els.push(c.cloneNode(true));
        });
        if(!els.length) return;
        groups += 1;
        var overlaps = els.filter(function(c){ return c.dataset.overlap === "1"; }).length;
        var open = els.filter(function(c){ return c.dataset.locked !== "1"; }).length;
        var summary = scope === "against" ? "vs " + L.opp + " · " + overlaps + " divided · " + open + " open" :
          (scope === "cheer" ? "your starters · " + overlaps + " overlap · " + open + " open" : "both sides · " + open + " open");
        stage.appendChild(group(L.code + " · " + L.name, els.length, summary, els, null, L.color));
      });
      if(!groups) empty("No players match this league view and filter.");
      return;
    }

    var tiers;
    if(scope === "cheer") tiers = [
      ["multi", "Multi-league starts", "You are rooting for him in more than one league."],
      ["single", "Rooting for", ""]
    ];
    else if(scope === "overlap") tiers = [
      ["positive", "Lean for", "You start him in more leagues than you face him."],
      ["even", "Even stake", "Your starts and opposing shares cancel out."],
      ["negative", "Lean against", "You face him in more leagues than you start him."]
    ];
    else tiers = [
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
    if(!groups) empty("No players match this filter.");
  }

  function press(sel, key, val){
    document.querySelectorAll(sel).forEach(function(b){
      b.setAttribute("aria-pressed", String(b.dataset[key] === val));
    });
  }

  function saveHidden(selector, dataKey, storageKey){
    var hidden = Array.prototype.slice.call(document.querySelectorAll(selector + ":not(:checked)"))
      .map(function(box){ return box.dataset[dataKey]; });
    try { localStorage.setItem(storageKey, JSON.stringify(hidden)); } catch(e) {}
  }

  function restoreHidden(selector, dataKey, storageKey){
    try {
      var hidden = JSON.parse(localStorage.getItem(storageKey) || "[]");
      document.querySelectorAll(selector).forEach(function(input){
        input.checked = hidden.indexOf(input.dataset[dataKey]) === -1;
      });
    } catch(e) {}
  }

  function applyThin(enabled){
    document.body.classList.toggle("thin", enabled);
    stage.querySelectorAll(".card-main").forEach(function(button){
      button.setAttribute("aria-expanded", "false");
      var detail = button.nextElementSibling;
      if(detail) detail.hidden = true;
    });
  }

  document.querySelectorAll("[data-scope]").forEach(function(b){
    b.addEventListener("click", function(){
      scope = b.dataset.scope; press("[data-scope]", "scope", scope); build(); updateCountdown();
    });
  });
  var viewSelect = document.querySelector("[data-view-select]");
  // A browser restoring a previous <select> value would otherwise disagree
  // with the default held in `view`.
  if(viewSelect) viewSelect.value = view;
  var sortSelect = document.querySelector("[data-sort-select]");
  var filterSelect = document.querySelector("[data-filter-select]");
  viewSelect.addEventListener("change", function(){ view = viewSelect.value; build(); });
  sortSelect.addEventListener("change", function(){ sort = sortSelect.value; build(); });
  filterSelect.addEventListener("change", function(){ filter = filterSelect.value; build(); });
  document.querySelectorAll("[data-league-check]").forEach(function(input){
    input.addEventListener("change", function(){
      saveHidden("[data-league-check]", "leagueCheck", "fm-hidden-leagues"); build(); updateCountdown();
    });
  });
  document.querySelectorAll("[data-team-check]").forEach(function(input){
    input.addEventListener("change", function(){
      saveHidden("[data-team-check]", "teamCheck", "fm-hidden-teams"); build(); updateCountdown();
    });
  });
  document.querySelectorAll("[data-teams]").forEach(function(button){
    button.addEventListener("click", function(){
      var checked = button.dataset.teams === "all";
      document.querySelectorAll("[data-team-check]").forEach(function(input){ input.checked = checked; });
      saveHidden("[data-team-check]", "teamCheck", "fm-hidden-teams"); build(); updateCountdown();
    });
  });
  var thinCheck = document.querySelector("[data-thin-check]");
  if(thinCheck){
    try { thinCheck.checked = localStorage.getItem("fm-thin-mode") === "1"; } catch(e) {}
    applyThin(thinCheck.checked);
    thinCheck.addEventListener("change", function(){
      applyThin(thinCheck.checked);
      try { localStorage.setItem("fm-thin-mode", thinCheck.checked ? "1" : "0"); } catch(e) {}
    });
  }

  restoreHidden("[data-league-check]", "leagueCheck", "fm-hidden-leagues");
  restoreHidden("[data-team-check]", "teamCheck", "fm-hidden-teams");

  stage.addEventListener("click", function(event){
    var button = event.target.closest(".card-main");
    if(!button) return;
    if(document.body.classList.contains("thin")) return;
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
  // Rebuilding every minute would fight the user by collapsing games, so the
  // tick only rebuilds when a game has actually crossed the finish mark.
  function finishedSignature(){
    return sourceCards.map(function(c){
      return isFinished(c.dataset.ts) ? "1" : "0";
    }).join("");
  }
  var lastFinished = finishedSignature();

  updateCountdown();
  setInterval(function(){
    updateCountdown();
    var now = finishedSignature();
    if(now !== lastFinished){
      lastFinished = now;
      build();
    }
  }, 60000);
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
