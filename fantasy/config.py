"""Configuration loaded from environment (.env for local runs, Actions secrets in CI)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "out"

# ESPN's fantasy lineup slots that mean "not started".
BENCH_SLOTS = {20, 21}
SKILL_POSITIONS = ("QB", "RB", "WR", "TE")


def _load_dotenv() -> None:
    """Minimal .env reader so local runs match CI without extra deps."""
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


_load_dotenv()


def _csv(name: str) -> list[str]:
    return [x.strip() for x in os.environ.get(name, "").split(",") if x.strip()]


SLEEPER_USER_ID = os.environ.get("SLEEPER_USER_ID", "")
SLEEPER_LEAGUES = _csv("SLEEPER_LEAGUES")
ESPN_LEAGUES = _csv("ESPN_LEAGUES")
ESPN_S2 = os.environ.get("ESPN_S2", "")
SWID = os.environ.get("SWID", "")

NOTIFY_BACKEND = os.environ.get("NOTIFY_BACKEND", "sms")
GMAIL_USER = os.environ.get("GMAIL_USER", "")
GMAIL_APP_PW = os.environ.get("GMAIL_APP_PW", "")
SMS_TO = os.environ.get("SMS_TO", "")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
BOARD_BASE_URL = os.environ.get("BOARD_BASE_URL", "").rstrip("/")

LEAD_MINUTES = int(os.environ.get("LEAD_MINUTES", "90"))
SEASON = os.environ.get('SEASON', '2026')
