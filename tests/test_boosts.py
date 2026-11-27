from __future__ import annotations

import pytest

from farmbot.boosts import (
    BoostInterval,
    MaintenanceInterval,
    POTIONS,
    estimate_completion,
    extend_repeated_potion,
    potion_interval,
)


def test_documented_potions_have_verified_effects_and_durations():
    assert POTIONS["builder-potion"].multiplier == 10
    assert POTIONS["builder-potion"].duration_seconds == 3600
    assert POTIONS["research-potion"].multiplier == 24
    assert POTIONS["pet-potion"].multiplier == 24
    assert all(item.duration_seconds == 3600 for item in POTIONS.values())


def test_unknown_or_unmodelled_potion_is_not_guessed():
    assert potion_interval("clock-tower-potion", 100) is None
    assert potion_interval("future-potion", 100) is None


def test_builder_potion_accelerates_only_home_builder_work():
    boost = potion_interval("builder-potion", 1000)
    assert boost is not None
    assert estimate_completion(7200, "home_builders", 1000, [boost]) == pytest.approx(1720)
    assert estimate_completion(7200, "laboratory", 1000, [boost]) == pytest.approx(8200)


def test_work_extending_past_the_boost_returns_to_normal_speed():
    boost = potion_interval("builder-potion", 1000)
    assert boost is not None
    # 1h at 10x consumes 36,000 baseline seconds; 4,000 remain.
    assert estimate_completion(40000, "home_builders", 1000, [boost]) == pytest.approx(8600)


def test_future_boost_does_not_accelerate_work_before_it_starts():
    boost = potion_interval("research-potion", 2000)
    assert boost is not None
    # 1,000 normal seconds, then 6,000 seconds of work at 24x.
    assert estimate_completion(7000, "laboratory", 1000, [boost]) == pytest.approx(2250)


def test_reusing_same_potion_extends_duration_without_increasing_multiplier():
    first = potion_interval("research-potion", 1000)
    assert first is not None
    extended = extend_repeated_potion([first], "research-potion", 1500)
    assert extended is not None
    assert len(extended) == 1
    assert extended[0].starts_at == 1000
    assert extended[0].ends_at == 8200
    assert extended[0].multiplier == 24


def test_reusing_potion_after_expiry_starts_a_new_interval():
    first = potion_interval("pet-potion", 1000)
    assert first is not None
    next_intervals = extend_repeated_potion([first], "pet-potion", 5000)
    assert next_intervals is not None
    assert len(next_intervals) == 2
    assert sorted((item.starts_at, item.ends_at) for item in next_intervals) == [
        (1000, 4600), (5000, 8600)
    ]


def test_maintenance_pauses_only_boosts_marked_to_pause():
    paused = BoostInterval(
        "clock", "builder_base_builders", 0, 3600, 10, "clock", True
    )
    maintenance = MaintenanceInterval(0, 1800)
    # First 30 minutes at 1x during maintenance, then 10x afterwards.
    assert estimate_completion(7200, "builder_base_builders", 0, [paused], [maintenance]) == pytest.approx(2340)


def test_work_continues_during_maintenance_when_boost_does_not_pause():
    boost = potion_interval("builder-potion", 0)
    assert boost is not None
    maintenance = MaintenanceInterval(0, 1800)
    # Builder Potion is not paused by maintenance per Supercell support.
    assert estimate_completion(7200, "home_builders", 0, [boost], [maintenance]) == pytest.approx(720)


def test_same_stacking_group_uses_strongest_effect_not_product():
    a = BoostInterval("a", "laboratory", 0, 1000, 10, "lab-speed")
    b = BoostInterval("b", "laboratory", 0, 1000, 24, "lab-speed")
    assert estimate_completion(2400, "laboratory", 0, [a, b]) == pytest.approx(100)


def test_distinct_stacking_groups_are_composed_explicitly():
    a = BoostInterval("a", "laboratory", 0, 1000, 2, "potion")
    b = BoostInterval("b", "laboratory", 0, 1000, 3, "snack")
    assert estimate_completion(6000, "laboratory", 0, [a, b]) == pytest.approx(1000)


def test_invalid_intervals_and_work_values_are_rejected():
    with pytest.raises(ValueError):
        BoostInterval("bad", "laboratory", 2, 1, 24, "lab")
    with pytest.raises(ValueError):
        estimate_completion(-1, "laboratory", 0)
    with pytest.raises(ValueError):
        MaintenanceInterval(10, 10)
