"""Pure, opt-in boost interval and upgrade ETA calculations.

This module has no device actions and is not wired into the farming loop.
It models only potion effects whose multiplier and duration are documented
by Supercell. Unknown boost types are deliberately unsupported.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal, Sequence

WorkGroup = Literal[
    "home_builders",
    "laboratory",
    "pets",
    "builder_base_builders",
    "star_laboratory",
]


@dataclass(frozen=True)
class PotionSpec:
    item_id: str
    name: str
    group: WorkGroup
    multiplier: float
    duration_seconds: int
    pauses_during_maintenance: bool = False
    stacking_group: str = ""


# Official Supercell support documents these three upgrade accelerators.
# Clock Tower Potion is intentionally omitted until its current effect can be
# represented against COCFARM's Builder Base timer/export model.
POTIONS: dict[str, PotionSpec] = {
    "builder-potion": PotionSpec(
        "builder-potion", "Builder Potion", "home_builders", 10.0, 3600,
        stacking_group="home_builder_speed",
    ),
    "research-potion": PotionSpec(
        "research-potion", "Research Potion", "laboratory", 24.0, 3600,
        stacking_group="laboratory_speed",
    ),
    "pet-potion": PotionSpec(
        "pet-potion", "Pet Potion", "pets", 24.0, 3600,
        stacking_group="pet_speed",
    ),
}


@dataclass(frozen=True)
class BoostInterval:
    boost_id: str
    group: WorkGroup
    starts_at: float
    ends_at: float
    multiplier: float
    stacking_group: str
    pauses_during_maintenance: bool = False

    def __post_init__(self) -> None:
        if not self.boost_id or not self.stacking_group:
            raise ValueError("boost_id and stacking_group must be non-empty")
        if not isfinite(self.starts_at) or not isfinite(self.ends_at) or self.ends_at <= self.starts_at:
            raise ValueError("boost interval must have finite, increasing timestamps")
        if not isfinite(self.multiplier) or self.multiplier < 1.0:
            raise ValueError("boost multiplier must be finite and at least 1")


@dataclass(frozen=True)
class MaintenanceInterval:
    starts_at: float
    ends_at: float

    def __post_init__(self) -> None:
        if not isfinite(self.starts_at) or not isfinite(self.ends_at) or self.ends_at <= self.starts_at:
            raise ValueError("maintenance interval must have finite, increasing timestamps")


def potion_interval(item_id: str, starts_at: float) -> BoostInterval | None:
    """Create a planned interval for a known potion; None for unsupported IDs."""
    spec = POTIONS.get(item_id)
    if spec is None:
        return None
    if not isfinite(starts_at):
        raise ValueError("starts_at must be finite")
    return BoostInterval(
        boost_id=spec.item_id,
        group=spec.group,
        starts_at=starts_at,
        ends_at=starts_at + spec.duration_seconds,
        multiplier=spec.multiplier,
        stacking_group=spec.stacking_group,
        pauses_during_maintenance=spec.pauses_during_maintenance,
    )


def extend_repeated_potion(
    existing: Sequence[BoostInterval], item_id: str, activated_at: float
) -> list[BoostInterval] | None:
    """Use of the same potion extends its duration, not its strength.

    If its effect is active at activation time, add one potion duration to the
    current end. Otherwise begin a fresh interval. Unrelated intervals remain.
    Returns None for an unsupported potion ID.
    """
    new = potion_interval(item_id, activated_at)
    if new is None:
        return None
    if not isfinite(activated_at):
        raise ValueError("activated_at must be finite")

    matching = [
        interval for interval in existing
        if interval.boost_id == item_id and interval.starts_at <= activated_at <= interval.ends_at
    ]
    if not matching:
        return [*existing, new]

    first = min(matching, key=lambda interval: interval.starts_at)
    last_end = max(interval.ends_at for interval in matching)
    extended = BoostInterval(
        boost_id=new.boost_id,
        group=new.group,
        starts_at=first.starts_at,
        ends_at=max(last_end, activated_at) + POTIONS[item_id].duration_seconds,
        multiplier=new.multiplier,
        stacking_group=new.stacking_group,
        pauses_during_maintenance=new.pauses_during_maintenance,
    )
    kept = [
        interval for interval in existing
        if interval.boost_id != item_id or interval not in matching
    ]
    return [*kept, extended]


def _rate_at(
    group: WorkGroup,
    at: float,
    boosts: Sequence[BoostInterval],
    maintenance: Sequence[MaintenanceInterval],
) -> float:
    in_maintenance = any(item.starts_at <= at < item.ends_at for item in maintenance)
    by_stack: dict[str, float] = {}
    for boost in boosts:
        if boost.group != group or not boost.starts_at <= at < boost.ends_at:
            continue
        if in_maintenance and boost.pauses_during_maintenance:
            continue
        by_stack[boost.stacking_group] = max(
            by_stack.get(boost.stacking_group, 1.0), boost.multiplier
        )
    # Within one stacking group the strongest effect wins; distinct groups
    # multiply. The catalogue currently defines only independently verified
    # single-potion groups, so no unverified potion-combination rule is assumed.
    rate = 1.0
    for multiplier in by_stack.values():
        rate *= multiplier
    return rate


def estimate_completion(
    remaining_work_seconds: float,
    group: WorkGroup,
    now: float,
    boosts: Sequence[BoostInterval] = (),
    maintenance: Sequence[MaintenanceInterval] = (),
) -> float:
    """Return the Unix timestamp when baseline work completes.

    remaining_work_seconds is the amount of unboosted work left at now.
    Work itself continues during maintenance; only intervals explicitly marked
    pause_during_maintenance are suspended. The function integrates each
    interval boundary exactly and never assumes a boost lasts beyond its end.
    """
    if not isfinite(remaining_work_seconds) or remaining_work_seconds < 0:
        raise ValueError("remaining work must be finite and non-negative")
    if not isfinite(now):
        raise ValueError("now must be finite")
    if remaining_work_seconds == 0:
        return now

    current = now
    remaining = float(remaining_work_seconds)
    boundaries = sorted({
        point
        for interval in (*boosts, *maintenance)
        for point in (interval.starts_at, interval.ends_at)
        if point > now
    })

    for boundary in [*boundaries, float("inf")]:
        rate = _rate_at(group, current, boosts, maintenance)
        if boundary == float("inf"):
            return current + remaining / rate
        available_work = (boundary - current) * rate
        if remaining <= available_work:
            return current + remaining / rate
        remaining -= available_work
        current = boundary

    raise AssertionError("unreachable")
