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

ET = ZoneInfo("America/New_York")

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
    kick = e.kickoff.astimezone(ET) if e.kickoff else None
    wave = f"{kick:%a} {kick:%-I:%M%p}".replace("AM", "am").replace("PM", "pm") if kick else "TBD"
    meta = f'{e.player.position} &middot; {e.player.team}'
    if kick:
        meta += f' &middot; {wave}'
    meta += ' &middot; LOCKED' if e.locked else ''

    def chips(names, ghost):
        out = []
        for n in names:
            meta = LEAGUES.get(n, {"code": n[:5].upper(), "color": "#CBD5E1"})
            cls = "chip ghost" if ghost else "chip"
            out.append(f'<span class="{cls}" style="--lc:{meta["color"]}" '
                       f'title="{_esc(n)}">{_esc(meta["code"])}</span>')
        return "".join(out)

    sides = ""
    if e.for_leagues:
        sides += f'<span class="ar f">&#9650;</span>{chips(e.for_leagues, True)}'
    if e.against_leagues:
        sides += f'<span class="ar a">&#9660;</span>{chips(e.against_leagues, False)}'
    if e.for_leagues and e.against_leagues:
        sides = sides  # both sides shown; arrows disambiguate direction

    src = url_for(e.player.name, e.player.position)
    initials = "".join(p[0] for p in e.player.name.split()[:2]).upper()
    photo = (f'<img class="ph" src="{_esc(src)}" alt="" loading="lazy" '
             f'onerror="this.outerHTML=\'<div class=&quot;noph&quot;>{initials}</div>\'">'
             if src else f'<div class="noph">{initials}</div>')

    return (
        f'<div class="card{" lk" if e.locked else ""}" style="--tc:{rail_color(e.player.team)}"'
        f' data-key="{_esc(e.player.key)}" data-tier="{_tier(e)}"'
        f' data-exp="{len(e.against_leagues)}" data-net="{e.net}"'
        f' data-name="{_esc(e.player.name)}" data-pos="{_esc(e.player.position)}"'
        f' data-wave="{_esc(wave)}" data-ts="{kick.isoformat() if kick else "9999"}"'
        f' data-locked="{"1" if e.locked else "0"}"'
        f' data-leagues="{_esc("|".join(e.against_leagues))}">'
        f'{photo}<div class="body"><div class="nm">{_esc(e.player.name)}</div>'
        f'<div class="mt">{meta}</div>'
        f'<div class="side">{sides}</div></div>'
        f'<div class="fig">{_fig(e)}</div></div>'
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
    errs = [m for m in matchups if m.error]
    ok = [m for m in matchups if not m.error]

    label = wave.label if wave else f"{now.astimezone(ET):%a %-I:%M%p}"
    title = f"Week {week} &middot; {_esc(label)}"

    global LEAGUES
    LEAGUES = assign_leagues([m.league_name for m in ok])
    league_meta = [{"name": m.league_name, "opp": m.opp_team,
                    "code": LEAGUES[m.league_name]["code"],
                    "color": LEAGUES[m.league_name]["color"]} for m in ok]

    p = ['<div class="wrap"><div class="top">',
         f'<div class="eyebrow">Week {week} &middot; {_esc(label)} &middot; '
         f'{len(ok)} league{"s" if len(ok) != 1 else ""}</div>',
         f'<h1 class="thesis"><em>{len(facing)}</em> can hurt you</h1>',
         '<div class="tally">',
         f'<div><b>{len(conf)}</b> divided</div>',
         f'<div><b>{len(multi)}</b> doubled</div>',
         f'<div><b>{open_n}</b> open</div>',
         '</div></div>']

    p.append('<div class="legend">')
    for m in ok:
        meta = LEAGUES[m.league_name]
        p.append(f'<div class="lgd" style="--lc:{meta["color"]}" title="{_esc(m.league_name)}">'
                 f'<span class="code">{_esc(meta["code"])}</span>'
                 f'<span class="vs">vs {_esc(m.opp_team)}</span></div>')
    p.append('</div>')

    if errs:
        p += [f'<div class="err" style="margin-top:12px"><b>{_esc(m.league_name)}</b> &mdash; '
              f'{_esc(m.error)}</div>' for m in errs]

    p += ['<div class="bar"><span class="cap">Group</span>',
          '<button data-view="threat" aria-pressed="true">Threat</button>',
          '<button data-view="kickoff" aria-pressed="false">Kickoff</button>',
          '<button data-view="league" aria-pressed="false">League</button>',
          '</div>',
          '<div class="bar"><span class="cap">Sort</span>',
          '<button data-sort="exp" aria-pressed="true">Exposure</button>',
          '<button data-sort="name" aria-pressed="false">Name</button>',
          '<button data-sort="pos" aria-pressed="false">Position</button>',
          '</div>',
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

    p.append(f'<footer>Generated {now.astimezone(ET):%a %b %-d %-I:%M%p} ET &middot; '
             f'ESPN + Sleeper &middot; photos Sleeper CDN</footer></div>')

    # League and team names are written by other league members, so they are
    # untrusted. json.dumps does not escape <, which would let a name
    # containing </script> break out of the block below.
    data = (json.dumps({"leagues": league_meta})
            .replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("&", "\\u0026").replace("\u2028", "\\u2028")
            .replace("\u2029", "\\u2029"))
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
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
  var original = stage.innerHTML;
  var view = "threat", sort = "exp";

  function cards(){ return Array.prototype.slice.call(stage.querySelectorAll(".card")); }

  var CMP = {
    exp:  function(a,b){ return (+b.dataset.exp - +a.dataset.exp)
                             || (+a.dataset.net - +b.dataset.net)
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

  function build(){
    var all = cards().map(function(c){ return c.cloneNode(true); });
    all.sort(CMP[sort]);
    stage.innerHTML = "";

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
      var meta = JSON.parse(document.getElementById("meta").textContent).leagues;
      var seen = {};
      meta.forEach(function(L){
        var els = [];
        all.forEach(function(c){
          if((c.dataset.leagues || "").split("|").indexOf(L.name) !== -1){
            els.push(c.cloneNode(true));
          }
        });
        seen[L.name] = 1;
        stage.appendChild(group(L.code + " · " + L.name, els.length,
          "vs " + L.opp, els, null, L.color));
      });
      return;
    }

    var tiers = [
      ["divided", "Divided", "You start him and you face him. Net is your true stake."],
      ["multi", "Doubled up", "One big game costs you more than one matchup."],
      ["single", "Facing", ""]
    ];
    tiers.forEach(function(t){
      var els = all.filter(function(c){ return c.dataset.tier === t[0]; });
      if(!els.length) return;
      stage.appendChild(group(t[1], els.length, t[2], els, null));
    });
  }

  function press(sel, key, val){
    document.querySelectorAll(sel).forEach(function(b){
      b.setAttribute("aria-pressed", String(b.dataset[key] === val));
    });
  }

  document.querySelectorAll("[data-view]").forEach(function(b){
    b.addEventListener("click", function(){
      view = b.dataset.view; press("[data-view]", "view", view);
      if(view === "threat" && sort === "exp"){ stage.innerHTML = original; }
      else { build(); }
    });
  });
  document.querySelectorAll("[data-sort]").forEach(function(b){
    b.addEventListener("click", function(){
      sort = b.dataset.sort; press("[data-sort]", "sort", sort); build();
    });
  });
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
