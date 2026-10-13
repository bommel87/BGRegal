"""Integrationstests in einem echten Home Assistant (pytest-homeassistant-custom-component)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.config_entries import ConfigEntryState  # noqa: E402
from homeassistant.core import HomeAssistant  # noqa: E402
from homeassistant.data_entry_flow import FlowResultType  # noqa: E402
from homeassistant.exceptions import ServiceValidationError  # noqa: E402
from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402

from custom_components.bgregal.const import DOMAIN  # noqa: E402
from custom_components.bgregal.core.errors import BggAuthError  # noqa: E402
from custom_components.bgregal.core.parser import (  # noqa: E402
    EXPANSION,
    CollectionItem,
    Play,
    PlayPlayer,
    ThingInfo,
)

OWNED = [
    CollectionItem(bgg_id=13, name="Catan", subtype="boardgame", owned=True, user_rating=7.5),
    CollectionItem(bgg_id=822, name="Carcassonne", subtype="boardgame", owned=True),
    CollectionItem(bgg_id=325, name="Catan: Seafarers", subtype=EXPANSION, owned=True),
]
THINGS = {
    13: ThingInfo(13, 3, 4, playing_time=90, game_types=["family"], expansions=[(325, "Seafarers")]),
    822: ThingInfo(822, 2, 5, playing_time=45, game_types=["family"]),
    325: ThingInfo(325, 3, 4, base_ids=[13]),
}
PLAYS = [Play(1, 13, "2026-10-10", players=[PlayPlayer("Susi", "susi", "10", True), PlayPlayer("Anna", None, "8")])]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def bgg():
    """Ersetzt alle BGG-Abfragen."""
    with (
        patch("custom_components.bgregal.core.client.BggClient.validate_user", AsyncMock()),
        patch("custom_components.bgregal.core.client.BggClient.user_exists", AsyncMock(return_value=True)),
        patch("custom_components.bgregal.core.client.BggClient.fetch_owned", AsyncMock(return_value=OWNED)),
        patch("custom_components.bgregal.core.client.BggClient.fetch_wishlist", AsyncMock(return_value=[])),
        patch("custom_components.bgregal.core.client.BggClient.fetch_things",
              AsyncMock(side_effect=lambda ids: {i: THINGS[i] for i in ids if i in THINGS})),
        patch("custom_components.bgregal.core.client.BggClient.fetch_plays",
              AsyncMock(side_effect=lambda page: (1, PLAYS) if page == 1 else (1, []))),
    ):
        yield


@pytest.fixture
async def regal(hass: HomeAssistant, bgg, tmp_path):
    hass.config.config_dir = str(tmp_path)
    entry = MockConfigEntry(domain=DOMAIN, data={"username": "susi", "token": "t"}, title="BGRegal (susi)")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)  # erster Sync läuft im Hintergrund
    assert entry.state is ConfigEntryState.LOADED
    return entry.runtime_data.regal


async def test_config_flow(hass: HomeAssistant, bgg) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM
    with (
        patch("custom_components.bgregal.async_setup_entry", return_value=True),
        patch("custom_components.bgregal.async_unload_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"username": "susi", "token": "t"}
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["data"] == {"username": "susi", "token": "t"}
        await hass.config_entries.async_remove(result["result"].entry_id)


async def test_config_flow_bad_token(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    with patch(
        "custom_components.bgregal.core.client.BggClient.validate_user",
        AsyncMock(side_effect=BggAuthError("nope")),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"username": "susi", "token": "bad"}
        )
    assert result["errors"] == {"base": "invalid_auth"}


async def test_entities_after_sync(hass: HomeAssistant, regal) -> None:
    assert hass.states.get("sensor.bgregal_sammlung").state == "2"
    assert hass.states.get("sensor.bgregal_partien").state == "1"
    assert hass.states.get("sensor.bgregal_sitzung").state == "idle"
    assert hass.states.get("sensor.bgregal_vorschlag").state == "idle"
    assert hass.states.get("sensor.bgregal_verliehen").state == "0"
    sammlung = hass.states.get("sensor.bgregal_sammlung").attributes
    assert sammlung["expansions"] == 1 and sammlung["pile_of_shame_games"] == ["Carcassonne"]
    assert hass.states.get("button.bgregal_sync") is not None
    assert hass.states.get("calendar.bgregal_spieleabende") is not None


async def test_nfc_session_and_bgstats(hass: HomeAssistant, regal) -> None:
    await hass.services.async_call(
        DOMAIN, "set_game", {"name": "Catan", "nfc_tag": "TAG1", "shelf": "Regal 1", "compartment": 2},
        blocking=True,
    )
    game = regal.find_game(13)
    assert game["shelf"] == "Regal 1" and game["compartment"] == 2

    hass.bus.async_fire("tag_scanned", {"tag_id": "TAG1"})
    await hass.async_block_till_done()
    state = hass.states.get("sensor.bgregal_sitzung")
    assert state.state == "running" and state.attributes["location"] == "Regal 1, Fach 2"

    await hass.services.async_call(DOMAIN, "set_order", {"order": ["Anna", "susi"]}, blocking=True)
    await hass.services.async_call(DOMAIN, "next_player", {}, blocking=True)
    assert hass.states.get("sensor.bgregal_sitzung").attributes["current_player"] == "susi"

    hass.bus.async_fire("tag_scanned", {"tag_id": "TAG1"})  # zweiter Scan beendet
    await hass.async_block_till_done()
    assert hass.states.get("sensor.bgregal_sitzung").state == "finished"

    result = await hass.services.async_call(
        DOMAIN, "finish_session",
        {"players": [{"name": "susi", "score": "40"}, {"name": "Anna", "score": "42"}], "note": "knapp"},
        blocking=True, return_response=True,
    )
    assert result["url"].startswith("https://app.bgstatsapp.com/createPlay.html?data=")
    assert result["qr_svg"].startswith("<svg")
    assert regal.snapshot["session"]["result"]["players"][1]["winner"] is True

    await hass.services.async_call(DOMAIN, "cancel_session", {}, blocking=True)
    assert hass.states.get("sensor.bgregal_sitzung").state == "idle"


async def test_tag_must_be_unique(hass: HomeAssistant, regal) -> None:
    await hass.services.async_call(DOMAIN, "set_game", {"bgg_id": 13, "nfc_tag": "X"}, blocking=True)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "set_game", {"bgg_id": 822, "nfc_tag": "x"}, blocking=True)


async def test_suggestion_flow(hass: HomeAssistant, regal) -> None:
    res = await hass.services.async_call(
        DOMAIN, "suggest", {"players": 2}, blocking=True, return_response=True
    )
    assert res["phase"] == "suggested" and res["game"]["name"] == "Carcassonne"  # Catan erst ab 3
    await hass.services.async_call(DOMAIN, "accept_suggestion", {}, blocking=True, return_response=True)
    assert hass.states.get("sensor.bgregal_vorschlag").state == "accepted"
    await hass.services.async_call(DOMAIN, "start_session", {}, blocking=True)
    assert hass.states.get("sensor.bgregal_sitzung").attributes["name"] == "Carcassonne"
    assert hass.states.get("sensor.bgregal_vorschlag").state == "idle"


async def test_loans_and_players(hass: HomeAssistant, regal) -> None:
    await hass.services.async_call(DOMAIN, "lend_game", {"name": "Catan", "borrower": "Ben"}, blocking=True)
    assert hass.states.get("sensor.bgregal_verliehen").state == "1"
    await hass.services.async_call(DOMAIN, "return_game", {"name": "Catan"}, blocking=True)
    assert hass.states.get("sensor.bgregal_verliehen").state == "0"

    await hass.services.async_call(
        DOMAIN, "set_player", {"name": "Anna", "dislikes": ["cooperative"]}, blocking=True
    )
    anna = next(p for p in regal.snapshot["players"] if p["name"] == "Anna")
    assert anna["dislikes"] == ["cooperative"] and anna["plays"] == 1


async def test_websocket_data(hass: HomeAssistant, regal, hass_ws_client) -> None:
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "bgregal/data"})
    msg = await client.receive_json()
    assert msg["success"]
    data = msg["result"]
    assert data["me"] == "susi" and len(data["games"]) == 3
    assert data["stats"]["pile_of_shame"] == [822]

    await client.send_json({"id": 2, "type": "bgregal/game", "bgg_id": 13})
    msg = await client.receive_json()
    assert msg["result"]["plays"][0]["players"][0]["name"] == "Susi"


async def test_evening_public_vote(hass: HomeAssistant, regal, hass_client_no_auth) -> None:
    res = await hass.services.async_call(
        DOMAIN, "plan_evening",
        {"title": "Freitag", "start": "2099-01-01 19:00:00", "guests": ["Anna"], "candidates": [13, 822]},
        blocking=True, return_response=True,
    )
    token = res["vote_url"].rsplit("/", 1)[1]
    client = await hass_client_no_auth()

    page = await client.get(f"/api/bgregal/vote/{token}")
    assert page.status == 200 and "<html" in await page.text()
    assert (await client.get("/api/bgregal/vote/falscherschluessel123")).status == 404

    resp = await client.post(f"/api/bgregal/vote/{token}/data", json={"voter": "Anna", "games": [822]})
    assert resp.status == 200
    body = await resp.json()
    assert body["votes"] == {"Anna": [822]} and body["open"] is True
    assert {c["name"] for c in body["candidates"]} == {"Catan", "Carcassonne"}

    bad = await client.post(f"/api/bgregal/vote/{token}/data", json={"voter": "Fremder", "games": [822]})
    assert bad.status == 400
    assert hass.states.get("calendar.bgregal_spieleabende").attributes["message"] == "Freitag"


async def test_unload(hass: HomeAssistant, regal) -> None:
    entry = regal.entry
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
