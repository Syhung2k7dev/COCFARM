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
    village = SimpleNamespace(finishing={
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
