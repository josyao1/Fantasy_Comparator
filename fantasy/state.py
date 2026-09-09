"""Dedup state so a wave is alerted exactly once, however often the job runs."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from . import config

STATE_FILE = config.DATA / "sent.json"
KEEP = 60


def load() -> set[str]:
    if not STATE_FILE.exists():
        return set()
    try:
        return set(json.loads(STATE_FILE.read_text()).get("sent", []))
    except (json.JSONDecodeError, OSError):
        return set()


def mark(wave_key: str) -> None:
    sent = list(load())
    if wave_key not in sent:
        sent.append(wave_key)
    config.DATA.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({
        "updated": datetime.now(timezone.utc).isoformat(),
        "sent": sent[-KEEP:],
    }, indent=2))
