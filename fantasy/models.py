"""Shared data structures passed between adapters, ledger and renderer."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .crosswalk import player_key


@dataclass(frozen=True)
class Player:
    name: str
    position: str
    team: str
    slot: str = ""

    @property
    def key(self) -> str:
        return player_key(self.name, self.position, self.team)


@dataclass
class LeagueMatchup:
    """One league's head-to-head for the current week."""
    platform: str            # "espn" | "sleeper"
    league_id: str
    league_name: str
    priority: int            # display order; ESPN leagues sort first
    my_team: str
    opp_team: str
    my_starters: list[Player] = field(default_factory=list)
    opp_starters: list[Player] = field(default_factory=list)
    error: str | None = None


@dataclass
class Exposure:
    """Aggregated stake in one player across every scanned league."""
    player: Player
    for_leagues: list[str] = field(default_factory=list)
    against_leagues: list[str] = field(default_factory=list)
    kickoff: datetime | None = None
    locked: bool = False

    @property
    def net(self) -> int:
        return len(self.for_leagues) - len(self.against_leagues)

    @property
    def is_conflict(self) -> bool:
        return bool(self.for_leagues) and bool(self.against_leagues)

    @property
    def is_multi(self) -> bool:
        return len(self.against_leagues) >= 2
