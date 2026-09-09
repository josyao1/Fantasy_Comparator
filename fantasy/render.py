"""HTML board and SMS digest.

The board is set like a sportsbook line sheet: the ledger's net figure reads
as a spread, and lock state is carried by each row's left edge rule rather
than an extra badge, so "can I still act on this" is spatial.
"""
from __future__ import annotations

import html
from datetime import datetime
from zoneinfo import ZoneInfo

from . import config, ledger
from .models import Exposure, LeagueMatchup

ET = ZoneInfo("America/New_York")

CSS = """
:root{
  --ground:#EEF1F5; --surface:#FFFFFF; --rule:#D7DDE5; --rule-soft:#E8ECF1;
  --ink:#10151C; --muted:#68727F; --faint:#95A0AD;
  --against:#C2410C; --against-bg:#FFF1E8;
  --for:#0E7490; --for-bg:#E6F6FA;
  --warn:#9A3412; --warn-bg:#FEF3E7;
}
@media (prefers-color-scheme:dark){
  :root{
    --ground:#0D1117; --surface:#151B23; --rule:#28313D; --rule-soft:#1E2630;
    --ink:#E7EDF4; --muted:#8B95A3; --faint:#69737F;
    --against:#F59156; --against-bg:#2A1810;
    --for:#4FC3DC; --for-bg:#0E2A32;
    --warn:#F0A868; --warn-bg:#2A1D10;
  }
}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--ink);
  font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif;
  -webkit-text-size-adjust:100%;padding-bottom:3rem}
.wrap{max-width:680px;margin:0 auto;padding:0 14px}
.mono{font-family:ui-monospace,"SF Mono",Menlo,monospace;font-variant-numeric:tabular-nums}

/* ── masthead ─────────────────────────────────────── */
.top{padding:22px 0 16px;border-bottom:2px solid var(--ink)}
.eyebrow{font-size:11px;letter-spacing:.16em;text-transform:uppercase;
  color:var(--muted);font-family:ui-monospace,"SF Mono",Menlo,monospace}
.thesis{font-size:27px;line-height:1.12;font-weight:700;letter-spacing:-.025em;margin:8px 0 0}
.thesis b{color:var(--against);font-weight:700}
.tally{display:flex;gap:18px;margin-top:12px;flex-wrap:wrap}
.tally div{font-size:12px;color:var(--muted)}
.tally strong{color:var(--ink);font-size:15px;
  font-family:ui-monospace,"SF Mono",Menlo,monospace}

/* ── sections ─────────────────────────────────────── */
.sect{margin-top:30px}
.sect > h2{font-size:11px;letter-spacing:.19em;text-transform:uppercase;
  color:var(--muted);font-weight:600;margin:0 0 3px;
  font-family:ui-monospace,"SF Mono",Menlo,monospace}
.sect > .note{font-size:12.5px;color:var(--faint);margin:0 0 11px}

/* ── player rows ──────────────────────────────────── */
.row{display:flex;align-items:flex-start;gap:12px;background:var(--surface);
  border:1px solid var(--rule-soft);border-left:3px solid var(--muted);
  padding:11px 13px;margin-bottom:6px;border-radius:3px}
.row.open{border-left-style:solid;border-left-color:var(--against)}
.row.locked{border-left-color:var(--rule);opacity:.62}
.row .body{flex:1;min-width:0}
.nm{font-weight:650;letter-spacing:-.012em;font-size:15.5px}
.meta{font-size:11.5px;color:var(--muted);letter-spacing:.05em;margin-top:1px;
  font-family:ui-monospace,"SF Mono",Menlo,monospace;text-transform:uppercase}
.side{font-size:12.5px;margin-top:6px;display:flex;gap:7px;align-items:baseline}
.side .ar{width:11px;flex:none;font-size:10px}
.side.f{color:var(--for)} .side.a{color:var(--against)}
.side .lg{color:var(--muted)}
.fig{font-family:ui-monospace,"SF Mono",Menlo,monospace;font-variant-numeric:tabular-nums;
  font-size:22px;font-weight:600;line-height:1;flex:none;text-align:right;min-width:52px}
.fig.neg{color:var(--against)} .fig.pos{color:var(--for)} .fig.even{color:var(--muted)}
.fig small{display:block;font-size:9.5px;letter-spacing:.13em;color:var(--faint);
  margin-top:5px;font-weight:500}

/* ── compact league tables ────────────────────────── */
.lg{margin-bottom:9px;background:var(--surface);border:1px solid var(--rule-soft);
  border-radius:3px;overflow:hidden}
.lg > header{display:flex;justify-content:space-between;align-items:baseline;gap:10px;
  padding:10px 13px;border-bottom:1px solid var(--rule-soft)}
.lg h3{margin:0;font-size:13.5px;font-weight:650;letter-spacing:-.01em}
.lg .vs{font-size:10.5px;color:var(--muted);flex:none;max-width:46%;
  font-family:ui-monospace,"SF Mono",Menlo,monospace;text-align:right;line-height:1.35}
.plist{display:grid;grid-template-columns:26px 1fr auto auto;gap:0 9px;
  padding:7px 13px 10px;font-size:13px;align-items:center}
.plist .pos{font-family:ui-monospace,"SF Mono",Menlo,monospace;font-size:10.5px;
  color:var(--faint);letter-spacing:.05em}
.plist .pn{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.plist .tm{font-family:ui-monospace,"SF Mono",Menlo,monospace;font-size:10.5px;
  color:var(--muted);letter-spacing:.05em}
.plist .st{font-family:ui-monospace,"SF Mono",Menlo,monospace;font-size:9.5px;
  letter-spacing:.09em;color:var(--faint);text-align:right}
.plist .st.lk{color:var(--faint);opacity:.7}
.mk{font-family:ui-monospace,"SF Mono",Menlo,monospace;font-size:9px;letter-spacing:.1em;
  margin-left:7px;padding:1.5px 5px;border-radius:2px;vertical-align:1px;font-weight:600}
.mk.mu{background:var(--against-bg);color:var(--against)}
.mk.cf{background:var(--for-bg);color:var(--for)}
.plist > div{padding:2.5px 0}
.plist .dim{opacity:.55}

.err{background:var(--warn-bg);border:1px solid var(--warn);border-left-width:3px;
  color:var(--warn);padding:10px 13px;border-radius:3px;margin-bottom:7px;font-size:13px}
.empty{color:var(--faint);font-size:13.5px;padding:14px 0;font-style:italic}
footer{margin-top:34px;padding-top:14px;border-top:1px solid var(--rule);
  font-size:11px;color:var(--faint);
  font-family:ui-monospace,"SF Mono",Menlo,monospace;letter-spacing:.05em}
"""


def _esc(s) -> str:
    return html.escape(str(s or ""))


def _fig_net(net: int) -> str:
    """Divided players only: the true stake, set as a spread."""
    cls = "pos" if net > 0 else "neg" if net < 0 else "even"
    txt = "EVEN" if net == 0 else f"{net:+d}"
    size = ' style="font-size:14px"' if net == 0 else ""
    return f'<div class="fig {cls}"{size}>{txt}<small>NET</small></div>'


def _fig_count(n: int) -> str:
    """Doubled-up players: exposure count, not a net position."""
    return f'<div class="fig neg">&times;{n}<small>LEAGUES</small></div>'


def _row(e: Exposure, mode: str = "net") -> str:
    lock = "locked" if e.locked else "open"
    kick = ""
    if e.kickoff:
        kick = f" · {e.kickoff.astimezone(ET):%-I:%M%p}".replace("AM", "am").replace("PM", "pm")
    sides = ""
    if mode == "net" and e.for_leagues:
        sides += (f'<div class="side f"><span class="ar">&#9650;</span>'
                  f'<span>start <span class="lg">{_esc(", ".join(e.for_leagues))}</span></span></div>')
    if e.against_leagues:
        sides += (f'<div class="side a"><span class="ar">&#9660;</span>'
                  f'<span>face <span class="lg">{_esc(", ".join(e.against_leagues))}</span></span></div>')
    return (
        f'<div class="row {lock}"><div class="body">'
        f'<div class="nm">{_esc(e.player.name)}</div>'
        f'<div class="meta">{_esc(e.player.position)} &middot; {_esc(e.player.team)}'
        f'{_esc(kick)} &middot; {"locked" if e.locked else "open"}</div>'
        f'{sides}</div>'
        + (_fig_net(e.net) if mode == "net" else _fig_count(len(e.against_leagues)))
        + '</div>'
    )


def _kick(exp: Exposure | None) -> str:
    """When he plays — or LOCKED once his game has started."""
    if exp is None or exp.kickoff is None:
        return "&mdash;"
    if exp.locked:
        return "LOCKED"
    t = exp.kickoff.astimezone(ET)
    return f"{t:%-I:%M}{'a' if t.hour < 12 else 'p'}"


def _league_block(m: LeagueMatchup, table: dict[str, Exposure]) -> str:
    if m.error:
        return (f'<div class="err"><strong>{_esc(m.league_name)}</strong> &mdash; '
                f'{_esc(m.error)}</div>')
    rows = []
    for p in sorted(m.opp_starters,
                    key=lambda x: (config.SKILL_POSITIONS.index(x.position)
                                   if x.position in config.SKILL_POSITIONS else 9, x.name)):
        if p.position not in config.SKILL_POSITIONS:
            continue
        exp = table.get(p.key)
        mark = ""
        if exp is not None:
            if exp.is_conflict:
                mark = '<span class="mk cf" title="you also start him">DIVIDED</span>'
            elif exp.is_multi:
                mark = f'<span class="mk mu" title="facing you in {len(exp.against_leagues)} leagues">&times;{len(exp.against_leagues)}</span>'
        locked = exp.locked if exp is not None else False
        rows.append(
            f'<div class="pos">{_esc(p.position)}</div>'
            f'<div class="pn{" dim" if locked else ""}">{_esc(p.name)}{mark}</div>'
            f'<div class="tm">{_esc(p.team)}</div>'
            f'<div class="st{" lk" if locked else ""}">{_kick(exp)}</div>'
        )
    body = "".join(rows) or '<div style="grid-column:1/-1" class="pos">no skill starters</div>'
    return (
        f'<div class="lg"><header><h3>{_esc(m.league_name)}</h3>'
        f'<div class="vs">{_esc(m.my_team)}<br>vs {_esc(m.opp_team)}</div></header>'
        f'<div class="plist">{body}</div></div>'
    )


def board(matchups: list[LeagueMatchup], table: dict[str, Exposure], week: int,
          wave, now: datetime) -> str:
    conf = ledger.conflicts(table)
    multi = ledger.multi_exposure(table)
    facing = [e for e in table.values() if e.against_leagues]
    open_count = sum(1 for e in facing if not e.locked)
    errs = [m for m in matchups if m.error]

    wave_label = wave.label if wave else f"{now.astimezone(ET):%a %-I:%M%p}"
    title = f"Week {week} &middot; {_esc(wave_label)}"

    parts = [
        '<div class="wrap"><div class="top">',
        f'<div class="eyebrow">Week {week} &middot; {_esc(wave_label)} &middot; '
        f'{len(matchups) - len(errs)} leagues</div>',
        f'<h1 class="thesis"><b>{len(facing)}</b> players can hurt you</h1>',
        '<div class="tally">',
        f'<div><strong>{len(conf)}</strong> divided</div>',
        f'<div><strong>{len(multi)}</strong> doubled up</div>',
        f'<div><strong>{open_count}</strong> still open</div>',
        '</div></div>',
    ]

    if errs:
        parts.append('<div class="sect">')
        parts += [f'<div class="err"><strong>{_esc(m.league_name)}</strong> &mdash; '
                  f'{_esc(m.error)}</div>' for m in errs]
        parts.append('</div>')

    parts.append('<div class="sect"><h2>Divided</h2>')
    if conf:
        parts.append('<p class="note">You start him and you face him. '
                     'Net is your true stake.</p>')
        parts.append("".join(_row(e) for e in conf))
    else:
        parts.append('<div class="empty">Nobody you start is playing against you.</div>')
    parts.append('</div>')

    parts.append('<div class="sect"><h2>Doubled up</h2>')
    if multi:
        parts.append('<p class="note">One big game costs you more than one matchup.</p>')
        parts.append("".join(_row(e, mode="count") for e in multi))
    else:
        parts.append('<div class="empty">Nobody is facing you in two leagues.</div>')
    parts.append('</div>')

    parts.append('<div class="sect"><h2>By league</h2>'
                 '<p class="note">Every skill starter lined up against you.</p>')
    parts += [_league_block(m, table) for m in matchups]
    parts.append('</div>')

    parts.append(f'<footer>Generated {now.astimezone(ET):%a %b %-d %-I:%M%p ET} &middot; '
                 f'ESPN + Sleeper</footer></div>')

    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="color-scheme" content="light dark">'
            f'<title>{title}</title><style>{CSS}</style></head><body>'
            + "".join(parts) + "</body></html>")


def sms_text(table: dict[str, Exposure], week: int, wave, matchups) -> str:
    """Short digest for the gateway. Kept tight — carriers split long bodies."""
    conf = ledger.conflicts(table)
    multi = ledger.multi_exposure(table)
    facing = [e for e in table.values() if e.against_leagues]
    label = wave.label if wave else "now"

    lines = [f"FM W{week} {label}", f"Facing {len(facing)}"]
    if multi:
        names = ", ".join(e.player.name.split()[-1] for e in multi[:3])
        lines.append(f"x2: {names}")
    for e in conf[:2]:
        lines.append(f"! {e.player.name.split()[-1]} {e.net:+d}")
    errs = [m for m in matchups if m.error]
    if errs:
        lines.append(f"{len(errs)} league(s) failed")
    if config.BOARD_BASE_URL:
        lines.append(config.BOARD_BASE_URL)
    return "\n".join(lines)
