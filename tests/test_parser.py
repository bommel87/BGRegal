import pytest

from conftest import fixture
from core.errors import BggError
from core.parser import parse_collection, parse_plays, parse_things, parse_user_id


def test_collection():
    items = parse_collection(fixture("collection.xml"))
    catan, gloom = items
    assert catan.bgg_id == 13 and catan.name == "Catan" and catan.owned
    assert catan.user_rating == 7.5
    assert catan.version_name == "German edition" and catan.languages == ["German"]
    assert gloom.wishlist and gloom.wishlist_priority == 2 and gloom.user_rating is None


def test_things():
    infos = parse_things(fixture("things.xml"))
    catan = infos[13]
    assert (catan.min_players, catan.max_players, catan.playing_time) == (3, 4, 120)
    assert catan.game_types == ["family"]  # "Not Ranked" zählt nicht
    assert catan.mode == "competitive"
    assert catan.weight == 2.29
    assert catan.expansions == [(325, "Catan: Seafarers"), (926, "Catan: Cities & Knights")]
    seafarers = infos[325]
    assert seafarers.base_ids == [13] and seafarers.expansions == []
    assert seafarers.mode == "cooperative" and seafarers.weight is None


def test_plays():
    total, plays = parse_plays(fixture("plays.xml"))
    assert total == 2
    first = plays[0]
    assert first.play_id == 9002 and first.bgg_id == 13 and first.length == 95
    assert first.comments == "Knapp!"
    assert [p.name for p in first.players] == ["Susi", "Anna"]  # leerer Spieler fällt weg
    assert first.players[0].win and first.players[0].username == "susi"
    assert plays[1].quantity == 2 and plays[1].length is None


def test_user_and_errors():
    assert parse_user_id('<user id="42" name="x"/>') == 42
    assert parse_user_id('<user id="" name="x"/>') is None
    with pytest.raises(BggError):
        parse_collection("<errors><error><message>Invalid username specified</message></error></errors>")
    with pytest.raises(BggError):
        parse_plays("kein xml")
