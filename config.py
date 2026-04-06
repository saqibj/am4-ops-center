"""User settings that affect extraction and queries."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class GameMode(Enum):
    EASY = "easy"
    REALISM = "realism"


@dataclass
class UserConfig:
    """Player-specific settings that affect calculations."""

    game_mode: GameMode = GameMode.EASY
    cost_index: int = 200
    reputation: float = 87.0
    fuel_price: float = 700.0
    co2_price: float = 120.0
    total_planes_owned: int = 50

    fuel_training: int = 0
    co2_training: int = 0
    repair_training: int = 0

    #: Minimum runway (m) for adding a hub via dashboard upsert; not used when bulk-extracting airports.
    min_runway: int = 0
    min_profit_per_day: float = 0.0
    max_flight_time_hours: float = -1.0
    include_stopovers: bool = True
    aircraft_filter: list[str] = field(default_factory=list)
    hub_filter: list[str] = field(default_factory=list)

    hubs: list[str] = field(default_factory=list)

    max_workers: int = 4

    #: Exclusive upper bound for am4 aircraft ID scan (``range(0, aircraft_id_max)``).
    aircraft_id_max: int = 1000
    #: Exclusive upper bound for am4 airport ID scan (``range(0, airport_id_max)``).
    airport_id_max: int = 8000
