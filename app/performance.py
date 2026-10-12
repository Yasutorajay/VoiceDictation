from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class PerformanceMode(str, Enum):
    SPEED = "speed"
    BALANCED = "balanced"
    LOW_MEMORY = "low_memory"


@dataclass(frozen=True)
class PerformanceProfile:
    mode: PerformanceMode
    load_main_on_start: bool
    load_punctuation_on_start: bool
    use_subprocess: bool
    idle_unload_seconds: int


_PROFILES = {
    PerformanceMode.SPEED: PerformanceProfile(
        mode=PerformanceMode.SPEED,
        load_main_on_start=True,
        load_punctuation_on_start=True,
        use_subprocess=False,
        idle_unload_seconds=0,
    ),
    PerformanceMode.BALANCED: PerformanceProfile(
        mode=PerformanceMode.BALANCED,
        load_main_on_start=True,
        load_punctuation_on_start=False,
        use_subprocess=False,
        idle_unload_seconds=0,
    ),
    PerformanceMode.LOW_MEMORY: PerformanceProfile(
        mode=PerformanceMode.LOW_MEMORY,
        load_main_on_start=False,
        load_punctuation_on_start=False,
        use_subprocess=True,
        idle_unload_seconds=600,
    ),
}


def resolve_performance_profile(cfg: dict[str, Any]) -> PerformanceProfile:
    performance = cfg.get("performance", {})
    try:
        mode = PerformanceMode(str(performance.get("mode", "balanced")))
    except ValueError:
        mode = PerformanceMode.BALANCED
    profile = _PROFILES[mode]
    if mode is not PerformanceMode.LOW_MEMORY:
        return profile
    try:
        minutes = int(performance.get("idle_unload_minutes", 10))
    except (TypeError, ValueError):
        minutes = 10
    bounded_minutes = min(max(minutes, 1), 120)
    return PerformanceProfile(
        mode=profile.mode,
        load_main_on_start=profile.load_main_on_start,
        load_punctuation_on_start=profile.load_punctuation_on_start,
        use_subprocess=profile.use_subprocess,
        idle_unload_seconds=bounded_minutes * 60,
    )

