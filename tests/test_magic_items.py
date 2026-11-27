from farmbot.tasks.magic_items import ITEMS, UpgradeTarget, choose_target


def target(target_id="target", name="Archer Tower", category="buildings", village="home", **changes):
    values = dict(target_id=target_id, name=name, category=category, village=village)
    values.update(changes)
    return UpgradeTarget(**values)


def test_all_known_books_and_hammers_have_item_specific_capacity():
    assert len(ITEMS) == 9
    assert {item.max_capacity for item in ITEMS.values()} == {1}


def test_item_is_not_used_before_its_own_capacity_is_reached():
    running = target(running=True, remaining_seconds=3600)
    assert choose_target("book-of-building", 0, [running]) is None


def test_book_only_finishes_a_running_matching_upgrade():
    running_building = target(running=True, remaining_seconds=3600)
    idle_building = target("idle", "Cannon", running=False, can_start=True)
    wrong_category = target("troop", "Barbarian", category="troops", running=True, remaining_seconds=7200)
    assert choose_target("book-of-building", 1, [idle_building, wrong_category]) is None
    assert choose_target("book-of-building", 1, [idle_building, running_building]) == running_building


def test_hammer_only_starts_a_valid_non_running_upgrade():
    running = target(running=True, remaining_seconds=3600)
    ready = target("ready", "Cannon", can_start=True)
    assert choose_target("hammer-of-building", 1, [running]) is None
    assert choose_target("hammer-of-building", 1, [running, ready]) == ready


def test_book_of_everything_can_finish_any_category():
    spell = target("spell", "Lightning Spell", category="spells", running=True, remaining_seconds=1200)
    pet = target("pet", "Unicorn", category="pets", village="builder", running=True, remaining_seconds=1800)
    assert choose_target("book-of-everything", 1, [spell, pet]) == pet


def test_spell_items_are_home_village_only():
    builder_spell = target("spell", "Builder Spell", category="spells", village="builder",
                           running=True, remaining_seconds=1800)
    assert choose_target("book-of-spells", 1, [builder_spell]) is None
    assert choose_target("hammer-of-spells", 1, [
        target("home-spell", "Lightning Spell", category="spells", can_start=True)
    ]) is not None


def test_higher_priority_then_longest_timer_wins():
    lower = target("lower", "Archer Tower", priority=0, can_start=True)
    higher_short = target("higher-short", "Cannon", priority=2, remaining_seconds=60, can_start=True)
    higher_long = target("higher-long", "Wizard Tower", priority=2, remaining_seconds=600, can_start=True)
    assert choose_target("hammer-of-building", 1, [lower, higher_short, higher_long]) == higher_long


def test_unknown_locked_maxed_gem_only_and_empty_targets_fail_closed():
    invalid = [
        target("unknown", "?", can_start=True, known=False),
        target("locked", "Locked", can_start=True, unlocked=False),
        target("maxed", "Maxed", can_start=True, maxed=True),
        target("gem", "Gem only", can_start=True, requires_gems=True),
        target("empty", "", can_start=True),
    ]
    assert choose_target("hammer-of-building", 1, invalid) is None
    assert choose_target("future-item", 99, invalid) is None


def test_book_of_heroes_accepts_heroes_and_pets():
    hero = target("hero", "Barbarian King", category="heroes", running=True, remaining_seconds=300)
    pet = target("pet", "Unicorn", category="pets", running=True, remaining_seconds=600)
    assert choose_target("book-of-heroes", 1, [hero, pet]) == pet


def test_running_targets_uses_only_known_home_export_timers(monkeypatch):
    from types import SimpleNamespace
    import farmbot.gamedata as gamedata
    from farmbot.tasks.magic_items import running_targets

    monkeypatch.setattr(gamedata, "BUILDINGS", {1: "Archer Tower"})
    monkeypatch.setattr(gamedata, "TRAPS", {2: "Cannon"})
    monkeypatch.setattr(gamedata, "TROOPS", {3: "Barbarian"})
    monkeypatch.setattr(gamedata, "SPELLS", {4: "Lightning Spell"})
    monkeypatch.setattr(gamedata, "HEROES", {5: "Barbarian King"})
    monkeypatch.setattr(gamedata, "PETS", {6: "Unicorn"})
    village = SimpleNamespace(timestamp=1_000, finishing={
        1: (1_200, 1_800), 3: (1_500,), 4: (900,), 6: (2_400,), 999: (5_000,)
    })

    targets = running_targets(village, 1_000)
    assert {(item.name, item.category, item.remaining_seconds) for item in targets} == {
        ("Archer Tower", "buildings", 200),
        ("Archer Tower", "buildings", 800),
        ("Barbarian", "troops", 500),
        ("Unicorn", "pets", 1_400),
    }
    assert all(item.village == "home" and item.running for item in targets)


def test_targets_from_build_list_names_respects_categories_and_free_slots(monkeypatch):
    import farmbot.gamedata as gamedata
    from farmbot.tasks.magic_items import targets_from_names

    monkeypatch.setattr(gamedata, "BUILDINGS", {1: "Archer Tower"})
    monkeypatch.setattr(gamedata, "TRAPS", {2: "Giant Bomb"})
    monkeypatch.setattr(gamedata, "HEROES", {3: "Barbarian King"})
    monkeypatch.setattr(gamedata, "TROOPS", {4: "Barbarian"})
    monkeypatch.setattr(gamedata, "SPELLS", {5: "Lightning Spell"})
    monkeypatch.setattr(gamedata, "PETS", {6: "Unicorn"})
    targets = targets_from_names(
        "home",
        {
            "buildings": {"Archer Tower", "Giant Bomb", "Barbarian King", "Unknown OCR"},
            "army": {"Barbarian", "Lightning Spell"},
            "pets": {"Unicorn"},
        },
        priorities={"Archer Tower": 5},
        free_builders=0,
        free_lab=1,
    )
    by_name = {item.name: item for item in targets}
    assert set(by_name) == {"Archer Tower", "Giant Bomb", "Barbarian King", "Barbarian",
                            "Lightning Spell", "Unicorn"}
    assert by_name["Archer Tower"].category == "buildings"
    assert by_name["Giant Bomb"].category == "buildings"
    assert by_name["Barbarian King"].category == "heroes"
    assert by_name["Unicorn"].category == "pets"
    assert by_name["Barbarian"].can_start is True
    assert by_name["Lightning Spell"].can_start is True
    assert by_name["Archer Tower"].can_start is False
    assert by_name["Barbarian King"].can_start is False
    assert by_name["Unicorn"].can_start is False
    assert by_name["Archer Tower"].priority == 5


def test_targets_from_build_list_does_not_guess_unknown_or_equipment(monkeypatch):
    import farmbot.gamedata as gamedata
    from farmbot.tasks.magic_items import targets_from_names

    monkeypatch.setattr(gamedata, "BUILDINGS", {})
    monkeypatch.setattr(gamedata, "TRAPS", {})
    monkeypatch.setattr(gamedata, "HEROES", {})
    monkeypatch.setattr(gamedata, "TROOPS", {})
    monkeypatch.setattr(gamedata, "SPELLS", {})
    monkeypatch.setattr(gamedata, "PETS", {})
    targets = targets_from_names("home", {"buildings": {"Unknown", "Magic Mirror", ""}},
                                 free_builders=5, free_lab=5)
    assert targets == []


def test_builder_base_spell_names_are_not_magic_hammer_targets(monkeypatch):
    import farmbot.gamedata as gamedata
    from farmbot.tasks.magic_items import targets_from_names

    monkeypatch.setattr(gamedata, "SPELLS", {1: "Builder Spell"})
    targets = targets_from_names("builder", {"army": {"Builder Spell"}}, free_lab=1)
    assert targets == []


def test_builder_base_candidates_use_export_slot_counts(monkeypatch):
    from types import SimpleNamespace
    import farmbot.gamedata as gamedata
    from farmbot.tasks.magic_items import targets_from_names

    monkeypatch.setattr(gamedata, "BUILDINGS", {1: "Crusher"})
    monkeypatch.setattr(gamedata, "TRAPS", {})
    monkeypatch.setattr(gamedata, "HEROES", {2: "Battle Machine"})
    monkeypatch.setattr(gamedata, "TROOPS", {3: "Raged Barbarian"})
    monkeypatch.setattr(gamedata, "SPELLS", {})
    monkeypatch.setattr(gamedata, "PETS", {})
    village = SimpleNamespace(builder_base_builders=2, builder_finishing={"builders": (1000,), "lab": ()})
    free_builders = village.builder_base_builders - len(village.builder_finishing["builders"])
    free_lab = 0 if village.builder_finishing["lab"] else 1
    targets = targets_from_names("builder", {"buildings": {"Crusher", "Battle Machine"},
                                             "army": {"Raged Barbarian"}},
                                 free_builders=free_builders, free_lab=free_lab)
    by_name = {item.name: item for item in targets}
    assert by_name["Crusher"].can_start is True
    assert by_name["Battle Machine"].can_start is True
    assert by_name["Raged Barbarian"].can_start is True


def test_builder_base_candidates_are_not_startable_without_export_slot_data(monkeypatch):
    import farmbot.gamedata as gamedata
    from farmbot.tasks.magic_items import targets_from_names

    monkeypatch.setattr(gamedata, "BUILDINGS", {1: "Crusher"})
    monkeypatch.setattr(gamedata, "TRAPS", {})
    monkeypatch.setattr(gamedata, "HEROES", {})
    monkeypatch.setattr(gamedata, "TROOPS", {})
    monkeypatch.setattr(gamedata, "SPELLS", {})
    monkeypatch.setattr(gamedata, "PETS", {})
    targets = targets_from_names("builder", {"buildings": {"Crusher"}}, free_builders=None, free_lab=None)
    assert len(targets) == 1
    assert targets[0].can_start is False


def test_home_scan_requires_the_build_list_to_be_confirmed(monkeypatch):
    from farmbot.tasks import build_list
    from farmbot.tasks.magic_items import scan_home_targets

    monkeypatch.setattr(build_list, "list_shown", lambda game: False)
    assert scan_home_targets(object()) is None


def test_home_scan_aborts_if_any_tab_or_ocr_is_unverified(monkeypatch):
    from farmbot.tasks import build_list
    from farmbot.tasks.magic_items import scan_home_targets

    monkeypatch.setattr(build_list, "list_shown", lambda game: True)
    monkeypatch.setattr(build_list, "open_tab", lambda *args: None)
    monkeypatch.setattr(build_list, "tab_open", lambda *args: True)
    monkeypatch.setattr(build_list, "busy", lambda game: False)
    calls = []

    def names(game, lst, which):
        calls.append(which)
        return {"Archer Tower"} if len(calls) == 1 else None

    monkeypatch.setattr(build_list, "upgradable_names", names)
    assert scan_home_targets(object()) is None
    assert calls == ["buildings", "research"]


def test_home_scan_uses_only_verified_tabs_and_slot_counters(monkeypatch):
    from farmbot.tasks import build_list
    from farmbot.tasks.magic_items import scan_home_targets

    monkeypatch.setattr(build_list, "list_shown", lambda game: True)
    monkeypatch.setattr(build_list, "open_tab", lambda *args: None)
    monkeypatch.setattr(build_list, "tab_open", lambda *args: True)
    monkeypatch.setattr(build_list, "busy", lambda game: False)
    monkeypatch.setattr(build_list, "upgradable_names", lambda game, lst, which: {
        "buildings": {"Archer Tower"},
        "research": {"Barbarian"},
    }[which])
    monkeypatch.setattr(build_list, "free_builders", lambda game: 1)
    monkeypatch.setattr(build_list, "free_lab", lambda game: 0)

    targets = scan_home_targets(object())
    by_name = {item.name: item for item in targets}
    assert by_name["Archer Tower"].can_start is True
    assert by_name["Barbarian"].can_start is False


def test_builder_scan_requires_export_and_confirmed_build_list(monkeypatch):
    from farmbot.tasks import build_list
    from farmbot.tasks.magic_items import scan_builder_targets
    from types import SimpleNamespace

    monkeypatch.setattr(build_list, "list_shown", lambda game: False)
    village = SimpleNamespace(builder_base_builders=2, builder_finishing={})
    assert scan_builder_targets(object(), village) is None
    assert scan_builder_targets(object(), None) is None


def test_targets_from_names_rejects_names_from_unrelated_tabs(monkeypatch):
    import farmbot.gamedata as gamedata
    from farmbot.tasks.magic_items import targets_from_names

    monkeypatch.setattr(gamedata, "BUILDINGS", {1: "Archer Tower"})
    monkeypatch.setattr(gamedata, "TRAPS", {})
    monkeypatch.setattr(gamedata, "HEROES", {2: "Barbarian King"})
    monkeypatch.setattr(gamedata, "TROOPS", {3: "Barbarian"})
    monkeypatch.setattr(gamedata, "SPELLS", {4: "Lightning Spell"})
    monkeypatch.setattr(gamedata, "PETS", {5: "Unicorn"})
    targets = targets_from_names(
        "home",
        {
            "buildings": {"Archer Tower", "Barbarian", "Lightning Spell", "Unicorn"},
            "army": {"Barbarian King", "Barbarian", "Lightning Spell"},
            "pets": {"Unicorn", "Archer Tower"},
        },
        free_builders=1,
        free_lab=1,
    )
    assert {(item.name, item.category) for item in targets} == {
        ("Archer Tower", "buildings"),
        ("Barbarian King", "heroes"),
        ("Barbarian", "troops"),
        ("Lightning Spell", "spells"),
        ("Unicorn", "pets"),
    }


def test_builder_scan_rejects_stale_or_future_dated_exports(monkeypatch):
    from types import SimpleNamespace
    from farmbot.tasks import build_list
    from farmbot.tasks.magic_items import scan_builder_targets

    monkeypatch.setattr(build_list, "list_shown", lambda game: True)
    assert scan_builder_targets(
        object(), SimpleNamespace(timestamp=1_000, builder_base_builders=2), now=1_301
    ) is None
    assert scan_builder_targets(
        object(), SimpleNamespace(timestamp=1_001, builder_base_builders=2), now=1_000
    ) is None
    assert scan_builder_targets(
        object(), SimpleNamespace(timestamp=0, builder_base_builders=2), now=1_000
    ) is None


def test_builder_scan_accepts_only_fresh_export_and_verified_build_tabs(monkeypatch):
    from types import SimpleNamespace
    import farmbot.gamedata as gamedata
    from farmbot.tasks import build_list
    from farmbot.tasks.magic_items import scan_builder_targets

    monkeypatch.setattr(gamedata, "BUILDINGS", {1: "Crusher"})
    monkeypatch.setattr(gamedata, "TRAPS", {})
    monkeypatch.setattr(gamedata, "HEROES", {})
    monkeypatch.setattr(gamedata, "TROOPS", {2: "Raged Barbarian"})
    monkeypatch.setattr(gamedata, "SPELLS", {})
    monkeypatch.setattr(gamedata, "PETS", {})
    monkeypatch.setattr(build_list, "list_shown", lambda game: True)
    monkeypatch.setattr(build_list, "open_tab", lambda *args: None)
    monkeypatch.setattr(build_list, "tab_open", lambda *args: True)
    monkeypatch.setattr(build_list, "upgradable_names", lambda game, lst, which: {
        "buildings": {"Crusher"}, "research": {"Raged Barbarian"}
    }[which])
    village = SimpleNamespace(
        timestamp=1_000,
        builder_base_builders=2,
        builder_finishing={"builders": (1_100,), "lab": ()},
    )
    targets = scan_builder_targets(object(), village, now=1_200)
    by_name = {item.name: item for item in targets}
    assert by_name["Crusher"].can_start is True
    assert by_name["Raged Barbarian"].can_start is True


def test_builder_base_book_scan_requires_fresh_export_and_known_busy_row(monkeypatch):
    from types import SimpleNamespace
    import farmbot.gamedata as gamedata
    from farmbot.tasks import build_list, row_names
    from farmbot.tasks.magic_items import scan_builder_running_targets

    monkeypatch.setattr(gamedata, "BUILDINGS", {1: "Crusher"})
    monkeypatch.setattr(gamedata, "TRAPS", {})
    monkeypatch.setattr(gamedata, "HEROES", {})
    monkeypatch.setattr(gamedata, "TROOPS", {2: "Raged Barbarian"})
    monkeypatch.setattr(gamedata, "SPELLS", {})
    monkeypatch.setattr(gamedata, "PETS", {})
    monkeypatch.setattr(build_list, "list_shown", lambda game: True)
    monkeypatch.setattr(build_list, "open_tab", lambda *args: None)
    monkeypatch.setattr(build_list, "tab_open", lambda game, tab, lst: True)
    monkeypatch.setattr(build_list, "busy", lambda game: game.current_tab == "buildings")
    monkeypatch.setattr(row_names, "read", lambda game, lst, which, green=False: (
        [(100, "Crusher")] if which == "buildings" else []
    ))
    game = SimpleNamespace(current_tab="buildings")
    # open_tab in this fake also changes the selected tab.
    monkeypatch.setattr(build_list, "open_tab", lambda game, tab, lst: setattr(game, "current_tab", tab))
    village = SimpleNamespace(
        timestamp=1_000,
        builder_finishing={"builders": (2_000,), "lab": ()},
    )

    targets = scan_builder_running_targets(game, village, now=1_200)
    assert len(targets) == 1
    assert targets[0].name == "Crusher"
    assert targets[0].category == "buildings"
    assert targets[0].running is True
    assert targets[0].remaining_seconds == 800
    assert targets[0].village == "builder"


def test_builder_base_book_scan_refuses_multiple_slot_timers(monkeypatch):
    from types import SimpleNamespace
    from farmbot.tasks import build_list
    from farmbot.tasks.magic_items import scan_builder_running_targets

    monkeypatch.setattr(build_list, "list_shown", lambda game: True)
    monkeypatch.setattr(build_list, "open_tab", lambda *args: None)
    monkeypatch.setattr(build_list, "tab_open", lambda *args: True)
    monkeypatch.setattr(build_list, "busy", lambda game: True)
    village = SimpleNamespace(
        timestamp=1_000,
        builder_finishing={"builders": (2_000, 3_000), "lab": ()},
    )
    assert scan_builder_running_targets(object(), village, now=1_200) is None


def test_builder_base_book_scan_refuses_unreadable_or_unknown_busy_row(monkeypatch):
    from types import SimpleNamespace
    import farmbot.gamedata as gamedata
    from farmbot.tasks import build_list, row_names
    from farmbot.tasks.magic_items import scan_builder_running_targets

    monkeypatch.setattr(gamedata, "BUILDINGS", {1: "Crusher"})
    monkeypatch.setattr(gamedata, "TRAPS", {})
    monkeypatch.setattr(gamedata, "HEROES", {})
    monkeypatch.setattr(gamedata, "TROOPS", {})
    monkeypatch.setattr(gamedata, "SPELLS", {})
    monkeypatch.setattr(gamedata, "PETS", {})
    monkeypatch.setattr(build_list, "list_shown", lambda game: True)
    monkeypatch.setattr(build_list, "open_tab", lambda *args: None)
    monkeypatch.setattr(build_list, "tab_open", lambda *args: True)
    monkeypatch.setattr(build_list, "busy", lambda game: True)
    monkeypatch.setattr(row_names, "read", lambda *args, **kwargs: [(100, None)])
    village = SimpleNamespace(timestamp=1_000, builder_finishing={"builders": (2_000,), "lab": ()})
    assert scan_builder_running_targets(object(), village, now=1_200) is None


def test_builder_base_book_scan_returns_empty_only_after_both_tabs_confirmed_idle(monkeypatch):
    from types import SimpleNamespace
    from farmbot.tasks import build_list
    from farmbot.tasks.magic_items import scan_builder_running_targets

    monkeypatch.setattr(build_list, "list_shown", lambda game: True)
    monkeypatch.setattr(build_list, "open_tab", lambda *args: None)
    monkeypatch.setattr(build_list, "tab_open", lambda *args: True)
    monkeypatch.setattr(build_list, "busy", lambda game: False)
    village = SimpleNamespace(timestamp=1_000, builder_finishing={})
    assert scan_builder_running_targets(object(), village, now=1_200) == []


def test_home_book_targets_require_a_fresh_village_export():
    from types import SimpleNamespace
    from farmbot.tasks.magic_items import running_targets

    stale = SimpleNamespace(timestamp=1_000, finishing={1: (2_000,)})
    future = SimpleNamespace(timestamp=1_201, finishing={1: (2_000,)})
    missing = SimpleNamespace(finishing={1: (2_000,)})
    assert running_targets(stale, 1_301) is None
    assert running_targets(future, 1_200) is None
    assert running_targets(missing, 1_200) is None


def test_home_book_targets_return_empty_for_a_fresh_export_with_no_active_timers():
    from types import SimpleNamespace
    from farmbot.tasks.magic_items import running_targets

    village = SimpleNamespace(timestamp=1_000, finishing={})
    assert running_targets(village, 1_200) == []


def test_home_hammer_scan_excludes_the_currently_upgrading_row(monkeypatch):
    import farmbot.gamedata as gamedata
    from farmbot.tasks import build_list, row_names
    from farmbot.tasks.magic_items import scan_home_targets

    monkeypatch.setattr(gamedata, "BUILDINGS", {1: "Archer Tower", 2: "Cannon"})
    monkeypatch.setattr(gamedata, "TRAPS", {})
    monkeypatch.setattr(gamedata, "HEROES", {})
    monkeypatch.setattr(gamedata, "TROOPS", {})
    monkeypatch.setattr(gamedata, "SPELLS", {})
    monkeypatch.setattr(gamedata, "PETS", {})
    monkeypatch.setattr(build_list, "list_shown", lambda game: True)
    monkeypatch.setattr(build_list, "open_tab", lambda *args: None)
    monkeypatch.setattr(build_list, "tab_open", lambda *args: True)
    monkeypatch.setattr(build_list, "busy", lambda game: game.current_tab == "buildings")
    monkeypatch.setattr(build_list, "upgradable_names", lambda game, lst, which: {
        "buildings": {"Archer Tower", "Cannon"},
        "research": set(),
    }[which])
    monkeypatch.setattr(build_list, "free_builders", lambda game: 1)
    monkeypatch.setattr(build_list, "free_lab", lambda game: 1)
    monkeypatch.setattr(row_names, "read", lambda game, lst, which, green=False: (
        [(100, "Archer Tower")] if which == "buildings" else []
    ))
    game = type("FakeGame", (), {"current_tab": "buildings"})()
    monkeypatch.setattr(build_list, "open_tab", lambda game, tab, lst: setattr(game, "current_tab", tab))

    targets = scan_home_targets(game)
    assert {target.name for target in targets} == {"Cannon"}


def test_hammer_scan_aborts_when_busy_row_name_is_unknown(monkeypatch):
    from farmbot.tasks import build_list, row_names
    from farmbot.tasks.magic_items import _exclude_busy_row

    monkeypatch.setattr(build_list, "busy", lambda game: True)
    monkeypatch.setattr(row_names, "read", lambda *args, **kwargs: [(100, None)])
    assert _exclude_busy_row(object(), build_list.HOME, "buildings", {"Archer Tower"}) is None


def test_builder_hammer_scan_excludes_currently_upgrading_row(monkeypatch):
    from types import SimpleNamespace
    import farmbot.gamedata as gamedata
    from farmbot.tasks import build_list, row_names
    from farmbot.tasks.magic_items import scan_builder_targets

    monkeypatch.setattr(gamedata, "BUILDINGS", {1: "Crusher", 2: "Cannon"})
    monkeypatch.setattr(gamedata, "TRAPS", {})
    monkeypatch.setattr(gamedata, "HEROES", {})
    monkeypatch.setattr(gamedata, "TROOPS", {})
    monkeypatch.setattr(gamedata, "SPELLS", {})
    monkeypatch.setattr(gamedata, "PETS", {})
    monkeypatch.setattr(build_list, "list_shown", lambda game: True)
    monkeypatch.setattr(build_list, "open_tab", lambda game, tab, lst: setattr(game, "current_tab", tab))
    monkeypatch.setattr(build_list, "tab_open", lambda *args: True)
    monkeypatch.setattr(build_list, "busy", lambda game: game.current_tab == "buildings")
    monkeypatch.setattr(build_list, "upgradable_names", lambda game, lst, which: {
        "buildings": {"Crusher", "Cannon"},
        "research": set(),
    }[which])
    monkeypatch.setattr(build_list, "free_builders", lambda game: 1)
    monkeypatch.setattr(build_list, "free_lab", lambda game: 1)
    monkeypatch.setattr(row_names, "read", lambda game, lst, which, green=False: (
        [(100, "Crusher")] if which == "buildings" else []
    ))
    village = SimpleNamespace(
        timestamp=1_000,
        builder_base_builders=2,
        builder_finishing={"builders": (1_100,), "lab": ()},
    )
    game = SimpleNamespace(current_tab="buildings")
    targets = scan_builder_targets(game, village, now=1_200)
    assert {target.name for target in targets} == {"Cannon"}
