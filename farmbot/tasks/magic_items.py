"""Fail-closed policy for automatically using instant-upgrade magic items.

This module deliberately contains no screen coordinates or device actions.
The live executor must identify the item and target on-screen, translate that
observation into these typed records, re-identify the target immediately
before tapping, and verify the resulting game state afterwards.

Magic-item capacity and applicability were checked against the MIT-licensed
clash-of-clans-data dataset (reviewed 2026-11-28):
https://github.com/chiefpansancolt/clash-of-clans-data/tree/main/data/magic-items
Unknown items are ignored rather than guessed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ItemKind = Literal["book", "hammer"]
Village = Literal["home", "builder"]
Category = Literal["buildings", "troops", "spells", "heroes", "pets"]


@dataclass(frozen=True)
class MagicItemSpec:
    item_id: str
    name: str
    kind: ItemKind
    applies_to: frozenset[Category]
    villages: frozenset[Village]
    max_capacity: int = 1


# The current game-data source reports a capacity of one for each of these
# books and hammers. Keep capacities item-specific: do not apply this table
# to potions, snacks, runes, or future/unknown items.
ITEMS: dict[str, MagicItemSpec] = {
    "book-of-building": MagicItemSpec("book-of-building", "Book of Building", "book",
                                      frozenset({"buildings"}), frozenset({"home", "builder"})),
    "book-of-everything": MagicItemSpec("book-of-everything", "Book of Everything", "book",
                                        frozenset({"buildings", "troops", "spells", "heroes", "pets"}),
                                        frozenset({"home", "builder"})),
    "book-of-fighting": MagicItemSpec("book-of-fighting", "Book of Fighting", "book",
                                      frozenset({"troops"}), frozenset({"home", "builder"})),
    "book-of-heroes": MagicItemSpec("book-of-heroes", "Book of Heroes", "book",
                                    frozenset({"heroes", "pets"}), frozenset({"home", "builder"})),
    "book-of-spells": MagicItemSpec("book-of-spells", "Book of Spells", "book",
                                    frozenset({"spells"}), frozenset({"home"})),
    "hammer-of-building": MagicItemSpec("hammer-of-building", "Hammer of Building", "hammer",
                                        frozenset({"buildings"}), frozenset({"home", "builder"})),
    "hammer-of-fighting": MagicItemSpec("hammer-of-fighting", "Hammer of Fighting", "hammer",
                                        frozenset({"troops"}), frozenset({"home", "builder"})),
    "hammer-of-heroes": MagicItemSpec("hammer-of-heroes", "Hammer of Heroes", "hammer",
                                      frozenset({"heroes", "pets"}), frozenset({"home", "builder"})),
    "hammer-of-spells": MagicItemSpec("hammer-of-spells", "Hammer of Spells", "hammer",
                                      frozenset({"spells"}), frozenset({"home"})),
}


@dataclass(frozen=True)
class UpgradeTarget:
    """A positively identified upgrade row/timer, not a raw OCR guess."""

    target_id: str
    name: str
    category: Category
    village: Village
    remaining_seconds: int = 0
    running: bool = False
    can_start: bool = False
    priority: int = 0
    known: bool = True
    unlocked: bool = True
    maxed: bool = False
    requires_gems: bool = False


def choose_target(item_id: str, quantity: int, targets: list[UpgradeTarget]) -> UpgradeTarget | None:
    """Choose a valid target only when the known item's own storage is full.

    Books finish an existing matching timer. Hammers start an eligible next
    level and therefore require a free/usable worker slot. Unknown, locked,
    maxed, unreadable, gem-only, wrong-village, and wrong-category targets
    are rejected. Higher configured priority wins, then the longest timer;
    name/id provide deterministic tie-breaking.
    """
    item = ITEMS.get(item_id)
    if item is None or quantity < item.max_capacity:
        return None

    eligible: list[UpgradeTarget] = []
    for target in targets:
        if (not target.known or not target.name.strip() or not target.target_id
                or not target.unlocked or target.maxed or target.requires_gems):
            continue
        if target.category not in item.applies_to or target.village not in item.villages:
            continue
        if item.kind == "book":
            if not target.running or target.remaining_seconds <= 0:
                continue
        elif target.running or not target.can_start:
            continue
        eligible.append(target)

    if not eligible:
        return None
    return min(eligible, key=lambda target: (-target.priority, -target.remaining_seconds,
                                             target.name.casefold(), target.target_id))


def plan_uses(quantities: dict[str, int], targets: list[UpgradeTarget]) -> list[tuple[str, UpgradeTarget]]:
    """Plan distinct item/target pairs without consuming anything.

    Specific items are assigned before universal books/hammers, preserving
    universal items for categories with no narrower match. Each target is
    reserved at most once. Unknown inventory entries and unreadable quantities
    are ignored.
    """
    candidates = sorted(
        (item for item_id, item in ITEMS.items()
         if isinstance(quantities.get(item_id), int)
         and quantities[item_id] >= item.max_capacity),
        key=lambda item: (len(item.applies_to), item.item_id),
    )
    remaining = list(targets)
    planned: list[tuple[str, UpgradeTarget]] = []
    for item in candidates:
        chosen = choose_target(item.item_id, quantities[item.item_id], remaining)
        if chosen is None:
            continue
        planned.append((item.item_id, chosen))
        remaining = [target for target in remaining if target.target_id != chosen.target_id]
    return planned


def _fresh_export(village_data, now: float, max_age: int | None = None) -> bool:
    """Whether the village export is recent enough for target/timer decisions."""
    from farmbot.tasks import export

    stamp = getattr(village_data, "timestamp", 0)
    max_age = export.FRESH if max_age is None else max_age
    return (
        isinstance(stamp, (int, float))
        and stamp > 0
        and isinstance(now, (int, float))
        and 0 <= now - stamp <= max_age
    )


def running_targets(village, now: float, max_export_age: int | None = None) -> list[UpgradeTarget] | None:
    """Turn the account export's confirmed Home Village timers into book targets.

    The export stores end timestamps by game item ID. Only IDs present in
    COCFARM's own current game-data maps are emitted; unknown IDs are skipped.
    Builder Base timers in the export are slot-only (no item identity), so
    they are deliberately not guessed here.
    """
    if village is None or not _fresh_export(village, now, max_export_age):
        return None

    from farmbot import gamedata

    categories = {
        "buildings": (gamedata.BUILDINGS, gamedata.TRAPS),
        "troops": (gamedata.TROOPS,),
        "spells": (gamedata.SPELLS,),
        "heroes": (gamedata.HEROES,),
        "pets": (gamedata.PETS,),
    }
    by_id = {
        game_id: (category, name)
        for category, maps in categories.items()
        for mapping in maps
        for game_id, name in mapping.items()
    }
    found: list[UpgradeTarget] = []
    for game_id, endings in village.finishing.items():
        known = by_id.get(game_id)
        if known is None:
            continue
        category, name = known
        for index, end in enumerate(endings):
            remaining = int(end - now)
            if remaining <= 0:
                continue
            found.append(UpgradeTarget(
                target_id=f"home:{game_id}:{index}",
                name=name,
                category=category,
                village="home",
                remaining_seconds=remaining,
                running=True,
                known=True,
                unlocked=True,
            ))
    return found


def targets_from_names(village: Village, names_by_tab: dict[str, set[str]],
                       priorities: dict[str, int] | None = None,
                       free_builders: int | None = None,
                       free_lab: int | None = None) -> list[UpgradeTarget]:
    """Convert fully-read Build-list names into Hammer candidates.

    A missing/unknown name is never guessed. A worker/research slot must be
    positively read as free before a candidate is marked startable. The
    caller should pass only names from a complete successful OCR pass.
    """
    from farmbot import gamedata

    priorities = priorities or {}
    buildings = set(gamedata.BUILDINGS.values()) | set(gamedata.TRAPS.values())
    heroes = set(gamedata.HEROES.values())
    troops = set(gamedata.TROOPS.values())
    spells = set(gamedata.SPELLS.values())
    pets = set(gamedata.PETS.values())

    found: dict[tuple[str, str], UpgradeTarget] = {}
    for tab, names in names_by_tab.items():
        for name in names:
            if not name or not name.strip():
                continue
            # Names are accepted only from tabs whose OCR dictionary can
            # legitimately contain that kind of upgrade. This prevents a
            # coincidental/incorrect OCR match in another tab from becoming
            # a Hammer target.
            if name in heroes and tab in {"buildings", "army"}:
                category: Category = "heroes"
                slot_free = free_builders
            elif name in pets and tab in {"pets", "army"}:
                category = "pets"
                slot_free = free_builders
            elif name in spells and tab == "army":
                category = "spells"
                slot_free = free_lab
            elif name in troops and tab == "army":
                category = "troops"
                slot_free = free_lab
            elif name in buildings and tab == "buildings":
                category = "buildings"
                slot_free = free_builders
            else:
                # Equipment, unknown OCR names, and names in an unexpected
                # tab are not valid Hammer candidates.
                continue
            if village == "builder" and category == "spells":
                continue
            target_id = f"{village}:{tab}:{name.casefold()}"
            found[(category, name)] = UpgradeTarget(
                target_id=target_id,
                name=name,
                category=category,
                village=village,
                can_start=slot_free is not None and slot_free > 0,
                priority=priorities.get(name, 0),
                known=True,
                unlocked=True,
            )
    return sorted(found.values(), key=lambda target: (target.category, target.name.casefold()))



def _exclude_busy_row(game: Game, names: set[str]) -> set[str]:
    """Skip a whole tab while its first row is upgrading.

    The OCR list includes the active row. Rather than risk mistaking a later
    row for it when the first line is clipped or unreadable, don't offer any
    Hammer targets from a tab whose busy marker is visible. Other tabs remain
    usable if their own workers are free.
    """
    from farmbot.tasks import build_list

    return set() if build_list.busy(game) else names


def scan_home_targets(game: Game, priorities: dict[str, int] | None = None) -> list[UpgradeTarget] | None:
    """Read Home Village Hammer candidates from an already-open Build list.

    This routine only changes tabs inside the confirmed Build list. It never
    opens an unknown screen, taps an upgrade row, or presses an upgrade/paid
    button. None means the list/screen/OCR/slot counters were not positively
    identified; callers must then leave all Hammers unused.
    """
    from farmbot.tasks import build_list

    if not build_list.list_shown(game):
        return None

    names_by_tab: dict[str, set[str]] = {}
    for tab, which in (("buildings", "buildings"), ("army", "research"), ("pets", "research")):
        build_list.open_tab(game, tab, build_list.HOME)
        if build_list.tab_open(game, tab, build_list.HOME) is not True:
            return None
        names = build_list.upgradable_names(game, build_list.HOME, which)
        if names is None:
            return None
        names = _exclude_busy_row(game, names)
        if names is None:
            return None
        names_by_tab[tab] = names

    # A missing counter is not treated as an idle worker. That leaves the
    # candidates visible for diagnostics but makes every relevant Hammer
    # ineligible until the counter can be read.
    builders = build_list.free_builders(game)
    lab = build_list.free_lab(game)
    return targets_from_names("home", names_by_tab, priorities, builders, lab)


def scan_builder_targets(game: Game, village_data,
                         priorities: dict[str, int] | None = None,
                         now: float | None = None,
                         max_export_age: int | None = None) -> list[UpgradeTarget] | None:
    """Read Builder Base Hammer candidates from its already-open Build list.

    Builder availability comes from the account export: Master Builder + OTTO
    minus the currently occupied builder slots; the Star Laboratory is one
    slot. If the export is missing or the list/OCR cannot be verified, return
    None so no Hammer is used on a guess.
    """
    import time

    from farmbot.tasks import build_list

    if village_data is None or not build_list.list_shown(game):
        return None
    now = time.time() if now is None else now
    # Builder Base worker slots come from the export, not live counters.
    # Never use an old or future-dated snapshot to claim a worker is free.
    if not _fresh_export(village_data, now, max_export_age):
        return None
    total_builders = getattr(village_data, "builder_base_builders", 0)
    if total_builders <= 0:
        return None

    names_by_tab: dict[str, set[str]] = {}
    for tab, which in (("buildings", "buildings"), ("army", "research")):
        build_list.open_tab(game, tab, build_list.BUILDER)
        if build_list.tab_open(game, tab, build_list.BUILDER) is not True:
            return None
        names = build_list.upgradable_names(game, build_list.BUILDER, which)
        if names is None:
            return None
        names = _exclude_busy_row(game, names)
        if names is None:
            return None
        names_by_tab[tab] = names

    busy = getattr(village_data, "builder_finishing", {}) or {}
    active_builders = len(busy.get("builders", ()))
    free_builders = max(0, total_builders - active_builders)
    free_lab = 0 if busy.get("lab") else 1
    return targets_from_names("builder", names_by_tab, priorities, free_builders, free_lab)




def open_inventory(game: Game) -> bool:
    """Open the Magic Items inventory only through verified templates.

    Both templates must be supplied through the Pictures page. If the
    inventory is already open, return True. Otherwise tap only the positively
    matched village inventory button and verify the inventory title afterwards.
    No item is selected or consumed here.
    """
    from farmbot.game import T

    if not game.has(T.MAGIC_ITEMS_TITLE):
        return False

    game.refresh()
    if game.find(T.MAGIC_ITEMS_TITLE) is not None:
        return True
    if not game.has(T.MAGIC_ITEMS):
        return False

    button = game.find(T.MAGIC_ITEMS)
    if button is None:
        return False
    game.tap(*button.point)
    game.wait(1.2, exact=True)
    game.refresh()
    return game.find(T.MAGIC_ITEMS_TITLE) is not None
