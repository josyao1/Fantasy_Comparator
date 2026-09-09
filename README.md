# Fantasy Matchups

Scans every fantasy league you play in before each NFL kickoff wave, works out
who can hurt you, and texts you a link to a board you can read on your phone.

Built for the case that no single fantasy app handles: **you play in several
leagues at once**, so the same player can threaten you two or three times over,
and sometimes you are starting the guy you are also playing against.

## What it tells you

| Tier | Meaning |
|---|---|
| **Divided** | You start him *and* face him. Shows the net stake: start in 1, face in 2 → `−1`. |
| **Doubled up** | He is in more than one opposing lineup at the same time. One big game costs you several matchups. |
| **By league** | Every skill starter lined up against you, with kickoff time and lock state. |

Scope is QB / RB / WR / TE, starters only.

## How the schedule works

Game days are never hardcoded. The full season is scraped from ESPN's public
scoreboard API and cached, then grouped into kickoff **waves** (Sunday 1:00pm,
Sunday 4:25pm, SNF, …). A cheap gatekeeper runs every 30 minutes and asks
whether a wave is due; if not it exits in seconds.

That matters — the 2026 season has eight games a Thu/Sun/Mon cron would miss:

```
wk 1  Wed 09/09  NE @ SEA        wk15  Sat 12/19  SEA @ PHI, CHI @ BUF
wk12  Wed 11/25  GB @ LAR        wk16  Fri 12/25  GB @ CHI, BUF @ DEN, LAR @ SEA
wk12  Fri 11/27  DEN @ PIT       (Black Friday)
```

A wave stays eligible from `kickoff − LEAD_MINUTES` until kickoff, so a delayed
CI run still delivers before lineups lock. `data/sent.json` guarantees one
alert per wave no matter how often the job runs.

## Setup

### 1. Sleeper

No auth. Find your user id and leagues:

```bash
curl -s https://api.sleeper.app/v1/user/YOUR_USERNAME | jq .user_id
curl -s https://api.sleeper.app/v1/user/USER_ID/leagues/nfl/2026 | jq '.[] | {league_id, name}'
```

### 2. ESPN

League ids come from each league's URL:

```
https://fantasy.espn.com/football/team?leagueId=123456789&teamId=4
                                                 ^^^^^^^^^
```

**Public leagues need no cookies at all.** If you set a league's visibility to
public in ESPN's league settings, it reads without credentials — which removes
the whole cookie-expiry problem. Check with:

```bash
curl -s -o /dev/null -w "%{http_code}\n" \
  "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026/segments/0/leagues/LEAGUE_ID?view=mTeam"
```

`200` means public, `401` means it needs cookies.

Private leagues need cookies from a logged-in browser:

1. Open **fantasy.espn.com**, then **Cmd+Option+I**
2. **Application → Storage → Cookies → https://fantasy.espn.com**
3. Copy **`espn_s2`** (long, `%`-escaped) and **`SWID`** (keep the curly braces)

These expire every few months. When they do, the board renders an explicit
"ESPN sign-in expired" banner and the text says how many leagues failed —
it never silently reports a smaller threat list than is real.

Write league ids as `leagueId:teamId` (the `teamId` is in the same URL). The
explicit team id makes identification deterministic and is what lets public
leagues work with no credentials at all:

```
ESPN_LEAGUES=944591:12,302220592:1,370831240:6
```

Without the `:teamId` suffix your team is matched via `SWID` instead, which
requires cookies even for a public league.

### 3. Texting

Gmail SMTP into Verizon's email-to-SMS gateway. Free, delivers a real text.

1. Google Account → Security → 2-Step Verification → **App passwords**
2. Generate one, use the 16 characters as `GMAIL_APP_PW`
3. `SMS_TO` is `<your10digitnumber>@vtext.com`

> Verizon retires this gateway on **2027-03-31**. `notify.py` is a swappable
> seam — set `NOTIFY_BACKEND=ntfy` and `NTFY_TOPIC=...` to move to push
> notifications without touching anything else.

### 4. Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env        # fill it in
.venv/bin/python -m fantasy.cli schedule          # this week's waves
.venv/bin/python -m fantasy.cli scan              # build the board, print digest
.venv/bin/python -m fantasy.cli run --force --dry-run   # full path, no send
.venv/bin/python -m fantasy.cli run               # what CI runs
```

### 5. GitHub Actions

Put the `.env` values in **Settings → Secrets and variables → Actions**:

*Secrets* — `SLEEPER_USER_ID`, `SLEEPER_LEAGUES`, `ESPN_LEAGUES`, `ESPN_S2`,
`SWID`, `GMAIL_USER`, `GMAIL_APP_PW`, `SMS_TO`, and for publishing
`VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID`.

*Variables* — `BOARD_BASE_URL`, optionally `LEAD_MINUTES` (default 90) and
`NOTIFY_BACKEND`.

Or run `./setup_actions.sh` after `gh auth login`, which reads `.env` and pipes
each value into `gh secret set` without printing it. `VERCEL_TOKEN` comes from
[vercel.com/account/tokens](https://vercel.com/account/tokens):

```bash
VERCEL_TOKEN=xxx ./setup_actions.sh
```

**Set Settings → Actions → General → Workflow permissions to "Read and write".**
The job commits `data/sent.json` back to the repo; without write access the
dedup state never persists and every run re-sends.

Trigger a one-off:

```bash
gh workflow run "fantasy matchup scan" -f force=true
gh run watch
```

Two Actions caveats: scheduled runs can be delayed 5-15 minutes under load,
which is why a wave stays eligible from `kickoff - LEAD_MINUTES` right up to
kickoff rather than firing in a narrow window; and GitHub disables scheduled
workflows after 60 days of repo inactivity, so the job goes dormant over the
offseason and needs re-enabling in August.

## Player identity

ESPN and Sleeper share no usable player id — Sleeper's `espn_id` is missing for
about 64% of startable skill players, including Bijan Robinson, Ja'Marr Chase
and Puka Nacua. Players are therefore keyed on normalized
`(name, position, team)`, which was measured to produce **zero collisions**
across the startable universe.

Two normalizations are load-bearing: ESPN says `WSH` where Sleeper says `WAS`,
and Sleeper still emits legacy `OAK`. Without those, every Washington player
would key as two different people and the Divided tier would miss them.

## Layout

```
fantasy/
  schedule.py    scrape + cache NFL schedule, group waves, decide what's due
  crosswalk.py   canonical player identity across platforms
  models.py      Player, LeagueMatchup, Exposure
  ledger.py      for/against aggregation -> the three tiers
  render.py      HTML board + SMS digest
  notify.py      delivery seam (sms | ntfy)
  state.py       per-wave dedup
  cli.py         scan / run / schedule
  adapters/      espn.py, sleeper.py
```

```bash
.venv/bin/python -m pytest tests/ -q
```
