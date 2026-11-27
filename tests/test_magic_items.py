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
