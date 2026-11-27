from types import SimpleNamespace

from farmbot.game import T
from farmbot.tasks.magic_items import open_inventory


class FakeGame:
    def __init__(self, templates, visible=()):
        self.templates = set(templates)
        self.visible = set(visible)
        self.taps = []
        self.waits = []
        self.refreshed = 0

    def has(self, name):
        return name in self.templates

    def find(self, name):
        return SimpleNamespace(point=(100, 200)) if name in self.visible else None

    def tap(self, x, y):
        self.taps.append((x, y))
        self.visible.add(T.MAGIC_ITEMS_TITLE)

    def wait(self, seconds, exact=False):
        self.waits.append((seconds, exact))

    def refresh(self):
        self.refreshed += 1


def test_inventory_entry_requires_both_templates_before_tapping():
    game = FakeGame({T.MAGIC_ITEMS})
    assert open_inventory(game) is False
    assert game.taps == []


def test_inventory_entry_does_not_tap_when_button_template_is_missing():
    game = FakeGame({T.MAGIC_ITEMS_TITLE})
    assert open_inventory(game) is False
    assert game.taps == []


def test_inventory_entry_recognizes_an_already_open_inventory():
    game = FakeGame({T.MAGIC_ITEMS, T.MAGIC_ITEMS_TITLE}, {T.MAGIC_ITEMS_TITLE})
    assert open_inventory(game) is True
    assert game.taps == []


def test_inventory_entry_taps_only_a_matched_button_and_verifies_title():
    game = FakeGame({T.MAGIC_ITEMS, T.MAGIC_ITEMS_TITLE})
    assert open_inventory(game) is True
    assert game.taps == [(100, 200)]
    assert game.waits == [(1.2, True)]
    assert game.refreshed == 2


def test_inventory_entry_returns_false_if_title_does_not_appear_after_tap():
    game = FakeGame({T.MAGIC_ITEMS, T.MAGIC_ITEMS_TITLE})
    game.tap = lambda x, y: game.taps.append((x, y))
    assert open_inventory(game) is False
    assert game.taps == [(100, 200)]
