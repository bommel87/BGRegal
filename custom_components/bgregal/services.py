"""Dienste von BGRegal."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .core.store import GAME_SORTS
from .core.suggest import DISLIKE_OPTIONS, GAME_TYPES, MODES
from .runtime import BgRegal

GAME = {vol.Optional("bgg_id"): vol.Coerce(int), vol.Optional("name"): cv.string}
NAMES = vol.All(cv.ensure_list, [cv.string])
IDS = vol.All(cv.ensure_list, [vol.Coerce(int)])
BASE_URL = vol.All(cv.string, vol.Match(r"^https?://[^/\s]+/?$"))  # nur Schema, Host und Port

SCHEMAS: dict[str, vol.Schema] = {
    "sync_now": vol.Schema({}),
    "set_game": vol.Schema(
        {
            **GAME,
            vol.Optional("shelf"): vol.Any(None, cv.string),
            vol.Optional("compartment"): vol.Any(None, "", vol.All(vol.Coerce(int), vol.Range(min=0, max=50))),
            vol.Optional("in_base"): cv.boolean,
            vol.Optional("nfc_tag"): vol.Any(None, cv.string),
            vol.Optional("light_profile"): vol.Any(None, cv.string),
            vol.Optional("playlist"): vol.Any(None, cv.string),
            vol.Optional("manual_url"): vol.Any(None, cv.string),
            vol.Optional("ean"): vol.Any(None, vol.Coerce(str)),
            vol.Optional("links"): vol.Any(None, vol.All(cv.ensure_list, [vol.Schema(
                {vol.Optional("title", default=""): vol.Any(None, cv.string), vol.Required("url"): cv.string}
            )])),
        }
    ),
    "scan_code": vol.Schema({vol.Required("code"): vol.Coerce(str)}),
    "set_shelf": vol.Schema(
        {
            vol.Required("name"): cv.string,
            vol.Optional("new_name"): cv.string,
            vol.Optional("area_id"): vol.Any(None, cv.string),
            vol.Optional("compartments"): vol.All(vol.Coerce(int), vol.Range(min=0, max=50)),
            vol.Optional("compartment_1_bottom"): cv.boolean,
            vol.Optional("game_sort"): vol.In(GAME_SORTS),
        }
    ),
    "set_sort_order": vol.Schema(
        {
            vol.Required("kind"): vol.In(("rooms", "shelves", "games")),
            vol.Required("order"): vol.All(cv.ensure_list, [vol.Coerce(str)]),
        }
    ),
    "remove_shelf": vol.Schema({vol.Required("name"): cv.string}),
    "start_inventory": vol.Schema(
        {vol.Required("shelf"): cv.string, vol.Optional("compartment", default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=50))}
    ),
    "inventory_place": vol.Schema(GAME),
    "inventory_undo": vol.Schema({}),
    "inventory_next": vol.Schema(
        {
            vol.Optional("clear_missing", default=False): cv.boolean,
            vol.Optional("compartment"): vol.All(vol.Coerce(int), vol.Range(min=1, max=50)),
        }
    ),
    "stop_inventory": vol.Schema({vol.Optional("clear_missing", default=False): cv.boolean}),
    "assign_scanned_tag": vol.Schema(GAME),
    "lend_game": vol.Schema({**GAME, vol.Required("borrower"): cv.string}),
    "return_game": vol.Schema(GAME),
    "start_session": vol.Schema({**GAME, vol.Optional("order"): NAMES}),
    "end_session": vol.Schema({}),
    "cancel_session": vol.Schema({}),
    "next_player": vol.Schema({}),
    "next_round": vol.Schema({}),
    "set_order": vol.Schema({vol.Required("order"): NAMES}),
    "finish_session": vol.Schema(
        {
            vol.Required("players"): vol.All(
                cv.ensure_list,
                [
                    vol.Schema(
                        {
                            vol.Required("name"): cv.string,
                            vol.Optional("score"): vol.Any(None, vol.Coerce(str)),
                            vol.Optional("winner", default=False): cv.boolean,
                        }
                    )
                ],
            ),
            vol.Optional("note", default=""): cv.string,
            vol.Optional("auto_winner", default=True): cv.boolean,
        }
    ),
    "session_qr": vol.Schema({}),
    "suggest": vol.Schema(
        {
            vol.Optional("players"): vol.All(vol.Coerce(int), vol.Range(min=1, max=20)),
            vol.Optional("mode", default="any"): vol.In(("any", *MODES)),
            vol.Optional("game_type", default="any"): vol.In(("any", *GAME_TYPES)),
            vol.Optional("max_playtime"): vol.All(vol.Coerce(int), vol.Range(min=0)),
            vol.Optional("attendees"): NAMES,
        }
    ),
    "reject_suggestion": vol.Schema({}),
    "accept_suggestion": vol.Schema({}),
    "reset_suggestion": vol.Schema({}),
    "set_player": vol.Schema(
        {
            vol.Required("name"): cv.string,
            vol.Optional("bgg_username"): vol.Any(None, cv.string),
            vol.Optional("dislikes"): vol.All(cv.ensure_list, [vol.In(DISLIKE_OPTIONS)]),
            vol.Optional("hidden"): cv.boolean,
        }
    ),
    "remove_player": vol.Schema({vol.Required("name"): cv.string}),
    "plan_evening": vol.Schema(
        {
            vol.Optional("title", default="Spieleabend"): cv.string,
            vol.Required("start"): cv.datetime,
            vol.Optional("guests", default=[]): NAMES,
            vol.Optional("max_playtime"): vol.Any(None, vol.All(vol.Coerce(int), vol.Range(min=0))),
            vol.Optional("candidates"): IDS,
            vol.Optional("base_url"): BASE_URL,
        }
    ),
    "set_candidates": vol.Schema({vol.Required("evening_id"): vol.Coerce(int), vol.Required("candidates"): IDS}),
    "remove_evening": vol.Schema({vol.Required("evening_id"): vol.Coerce(int)}),
    "vote": vol.Schema(
        {vol.Required("evening_id"): vol.Coerce(int), vol.Required("voter"): cv.string, vol.Required("games"): IDS}
    ),
    "evening_qr": vol.Schema(
        {vol.Required("evening_id"): vol.Coerce(int), vol.Optional("base_url"): BASE_URL}
    ),
    "dismiss_expansions": vol.Schema({}),
}

RESPONSES = {
    "assign_scanned_tag": SupportsResponse.OPTIONAL,
    "scan_code": SupportsResponse.OPTIONAL,
    "start_inventory": SupportsResponse.OPTIONAL,
    "inventory_place": SupportsResponse.OPTIONAL,
    "inventory_undo": SupportsResponse.OPTIONAL,
    "inventory_next": SupportsResponse.OPTIONAL,
    "stop_inventory": SupportsResponse.OPTIONAL,
    "finish_session": SupportsResponse.OPTIONAL,
    "session_qr": SupportsResponse.ONLY,
    "suggest": SupportsResponse.OPTIONAL,
    "reject_suggestion": SupportsResponse.OPTIONAL,
    "accept_suggestion": SupportsResponse.OPTIONAL,
    "plan_evening": SupportsResponse.OPTIONAL,
    "evening_qr": SupportsResponse.ONLY,
}


def get_regal(hass: HomeAssistant) -> BgRegal:
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED:
            return entry.runtime_data.regal
    raise ServiceValidationError("BGRegal ist nicht eingerichtet oder nicht geladen")


def _game(regal: BgRegal, data: dict[str, Any]) -> dict[str, Any]:
    return regal.find_game(data.get("bgg_id"), data.get("name"))


def _local(value):
    return value if value.tzinfo else value.replace(tzinfo=dt_util.get_default_time_zone())


async def _handle(regal: BgRegal, service: str, d: dict[str, Any]) -> dict[str, Any] | None:
    match service:
        case "sync_now":
            await regal.entry.runtime_data.async_request_refresh()
        case "set_game":
            fields = {k: v for k, v in d.items() if k not in ("bgg_id", "name")}
            await regal.async_set_game(_game(regal, d), fields)
        case "scan_code":
            return await regal.async_scan_code(d["code"])
        case "set_shelf":
            await regal.async_set_shelf(
                d["name"], d.get("new_name"), d.get("area_id") if "area_id" in d else None,
                d.get("compartments"), d.get("compartment_1_bottom"), d.get("game_sort"),
            )
        case "set_sort_order":
            await regal.async_set_sort_order(d["kind"], d["order"])
        case "remove_shelf":
            await regal.async_remove_shelf(d["name"])
        case "start_inventory":
            return await regal.async_start_inventory(d["shelf"], d["compartment"])
        case "inventory_place":
            return await regal.async_inventory_place(_game(regal, d))
        case "inventory_undo":
            return {"undone": await regal.async_inventory_undo()}
        case "inventory_next":
            return await regal.async_inventory_next(d["clear_missing"], d.get("compartment"))
        case "stop_inventory":
            return await regal.async_stop_inventory(d["clear_missing"])
        case "assign_scanned_tag":
            return {"nfc_tag": await regal.async_assign_scanned_tag(_game(regal, d))}
        case "lend_game":
            await regal.async_lend(_game(regal, d), d["borrower"])
        case "return_game":
            await regal.async_return(_game(regal, d))
        case "start_session":
            game = _game(regal, d) if ("bgg_id" in d or "name" in d) else None
            await regal.async_start_session(game, d.get("order"))
        case "end_session":
            await regal.async_end_session()
        case "cancel_session":
            await regal.async_cancel_session()
        case "next_player" | "next_round":
            await regal.async_update_session(service)
        case "set_order":
            await regal.async_update_session("set_order", d["order"])
        case "finish_session":
            return await regal.async_finish_session(d["players"], d["note"], d["auto_winner"])
        case "session_qr":
            return await regal.async_session_qr()
        case "suggest":
            return await regal.async_suggest(
                d.get("players"), d["mode"], d["game_type"], d.get("max_playtime"), d.get("attendees")
            )
        case "reject_suggestion":
            return await regal.async_reject_suggestion()
        case "accept_suggestion":
            return await regal.async_accept_suggestion()
        case "reset_suggestion":
            await regal.async_reset_suggestion()
        case "set_player":
            await regal.async_set_player(d["name"], d.get("bgg_username"), d.get("dislikes"), d.get("hidden"))
        case "remove_player":
            await regal.async_remove_player(d["name"])
        case "plan_evening":
            return await regal.async_plan_evening(
                d["title"], _local(d["start"]), d["guests"], d.get("max_playtime"), d.get("candidates"),
                d.get("base_url"),
            )
        case "set_candidates":
            await regal.async_set_candidates(d["evening_id"], d["candidates"])
        case "remove_evening":
            await regal.async_remove_evening(d["evening_id"])
        case "vote":
            await regal.async_vote(d["evening_id"], d["voter"], d["games"])
        case "evening_qr":
            return await regal.async_evening_qr(d["evening_id"], d.get("base_url"))
        case "dismiss_expansions":
            await regal.async_dismiss_expansions()
    return None


def _make_handler(hass: HomeAssistant, service: str) -> Callable[[ServiceCall], Awaitable[ServiceResponse]]:
    async def handler(call: ServiceCall) -> ServiceResponse:
        result = await _handle(get_regal(hass), service, dict(call.data))
        return result if call.return_response else None

    return handler


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    for service, schema in SCHEMAS.items():
        hass.services.async_register(
            DOMAIN,
            service,
            _make_handler(hass, service),
            schema=schema,
            supports_response=RESPONSES.get(service, SupportsResponse.NONE),
        )
