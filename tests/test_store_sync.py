import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from conftest import fixture
from core.parser import EXPANSION, CollectionItem, Play, PlayPlayer, parse_things
from core.store import Store
from core.sync import run_sync

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)


async def direct(fn, *args):
    return fn(*args)


class FakeClient:
    def __init__(self):
        self.owned = [
            CollectionItem(bgg_id=13, name="Catan", subtype="boardgame", owned=True, user_rating=7.5),
            CollectionItem(bgg_id=325, name="Catan: Seafarers", subtype=EXPANSION, owned=True),
        ]
        self.things = parse_things(fixture("things.xml"))
        self.pages = {1: (2, [
            Play(9002, 13, "2026-10-10", players=[PlayPlayer("Susi", "susi", "10", True),
                                                  PlayPlayer("Anna", None, "8", False)]),
            Play(9001, 13, "2025-01-05", quantity=2),
        ])}
        self.thing_calls: list[list[int]] = []
        self.play_pages: list[int] = []

    async def fetch_owned(self):
        return self.owned

    async def fetch_wishlist(self):
        return [CollectionItem(bgg_id=174430, name="Gloomhaven", subtype="boardgame", wishlist_priority=2)]

    async def fetch_things(self, ids):
        self.thing_calls.append(ids)
        return {i: self.things[i] for i in ids if i in self.things}

    async def fetch_plays(self, page):
        self.play_pages.append(page)
        return self.pages.get(page, (0, []))


@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path / "bgregal.db"))
    yield s
    s.close()


def test_full_sync(store):
    client = FakeClient()
    result = asyncio.run(run_sync(client, store, direct, NOW))
    assert result.games == 2 and result.new_plays == 2
    assert result.new_expansions == []  # erster Abgleich meldet nichts

    games = {g["bgg_id"]: g for g in store.games()}
    catan = games[13]
    assert catan["plays"] == 3 and catan["last_play"] == "2026-10-10"
    assert [p["name"] for p in catan["last_players"]] == ["Susi", "Anna"]
    assert catan["game_types"] == ["family"] and catan["min_players"] == 3
    assert games[325]["expansion"] and games[325]["base_ids"] == [13]
    assert store.wishlist()[0]["name"] == "Gloomhaven"
    assert [p["name"] for p in store.players("susi")] == ["Anna"]


def test_new_expansion_detected_on_refresh(store):
    client = FakeClient()
    asyncio.run(run_sync(client, store, direct, NOW))
    client.things[13].expansions.append((999, "Catan: Neu"))
    later = NOW + timedelta(days=8)  # Spielinfos sind dann veraltet
    result = asyncio.run(run_sync(client, store, direct, later))
    assert result.new_expansions == [{"base_id": 13, "bgg_id": 999, "name": "Catan: Neu"}]
    # 325 und 926 waren beim ersten Abgleich schon bekannt und gelten nicht als neu
    assert [e["bgg_id"] for e in store.new_expansions()] == [999]
    store.dismiss_new_expansions()
    assert store.new_expansions() == []


def test_incremental_plays_stop_at_known_page(store):
    client = FakeClient()
    asyncio.run(run_sync(client, store, direct, NOW))
    client.play_pages.clear()
    client.thing_calls.clear()
    asyncio.run(run_sync(client, store, direct, NOW + timedelta(hours=6)))
    assert client.play_pages == [1]
    assert client.thing_calls == []  # Infos sind frisch


def test_full_plays_removes_deleted(store):
    client = FakeClient()
    asyncio.run(run_sync(client, store, direct, NOW))
    client.pages = {1: (1, [client.pages[1][1][0]])}  # Partie 9001 auf BGG gelöscht
    asyncio.run(run_sync(client, store, direct, NOW + timedelta(days=8)))
    assert store.known_play_ids() == {9002}


def test_meta_survives_sync_and_tags(store):
    client = FakeClient()
    asyncio.run(run_sync(client, store, direct, NOW))
    store.set_game_meta(13, {"shelf": "Regal 1", "compartment": 2, "nfc_tag": "ABC", "bogus": 1})
    asyncio.run(run_sync(client, store, direct, NOW + timedelta(hours=1)))
    catan = store.game(13)
    assert catan["shelf"] == "Regal 1" and catan["compartment"] == 2
    assert store.game_by_tag("abc") == 13


def test_loans(store):
    asyncio.run(run_sync(FakeClient(), store, direct, NOW))
    store.lend(13, "Ben", "2026-08-01")
    assert store.game(13)["loan"] == {"borrower": "Ben", "since": "2026-08-01"}
    store.lend(13, "Clara", "2026-09-01")  # neuer Verleih beendet den alten
    assert [l["borrower"] for l in store.active_loans()] == ["Clara"]
    assert store.return_game(13, "2026-10-01")
    assert store.game(13)["loan"] is None and not store.return_game(13, "2026-10-02")


def test_players_and_evenings(store):
    asyncio.run(run_sync(FakeClient(), store, direct, NOW))
    store.set_player("anna", "anna_bgg", ["cooperative"])
    store.set_player("Ben", None, None)
    players = {p["name"]: p for p in store.players("susi")}
    assert players["Anna"]["bgg_username"] == "anna_bgg" and players["Anna"]["dislikes"] == ["cooperative"]
    assert players["Ben"]["plays"] == 0

    eid = store.add_evening("Freitag", "2026-10-17T19:00:00", 90, "tok", ["Anna", "Ben"], [13])
    store.set_votes(eid, "Anna", [13])
    evening = store.evening_by_token("tok")
    assert evening["guests"] == ["Anna", "Ben"] and evening["votes"] == {"Anna": [13]}
    store.set_candidates(eid, [])
    assert store.evening(eid)["votes"] == {}
    assert store.remove_evening(eid) and store.evenings() == []


def test_session_roundtrip(store):
    assert store.get_session() is None
    store.set_session({"state": "running", "name": "Catan"})
    assert store.get_session()["name"] == "Catan"
    store.set_session(None)
    assert store.get_session() is None
