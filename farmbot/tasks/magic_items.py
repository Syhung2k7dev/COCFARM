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
