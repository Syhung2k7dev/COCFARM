from farmbot import gamedata
from farmbot.tasks import row_names


SQUAD_IDS = tuple(range(4000195, 4000207))


def test_all_exported_squads_are_in_the_research_picker():
    expected = tuple(gamedata.TROOPS[item_id] for item_id in SQUAD_IDS)

    assert row_names.HOME_RESEARCH["Squads"] == expected
    assert set(expected) <= set(row_names.PICKS["research"])


def test_squad_names_are_recognized_as_research_rows():
    for item_id in SQUAD_IDS:
        name = gamedata.TROOPS[item_id]
        assert row_names.building(name, "research") == name
