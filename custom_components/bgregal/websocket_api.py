"""WebSocket-Befehle fürs Panel und die Kachel (nur lesend; Änderungen laufen über Dienste)."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import SIGNAL_UPDATE
from .services import get_regal


@callback
def async_setup_websocket(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_data)
    websocket_api.async_register_command(hass, ws_game)
    websocket_api.async_register_command(hass, ws_subscribe)


@websocket_api.websocket_command({vol.Required("type"): "bgregal/data"})
@callback
def ws_data(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    try:
        connection.send_result(msg["id"], get_regal(hass).public_state())
    except HomeAssistantError as err:
        connection.send_error(msg["id"], "not_loaded", str(err))


@websocket_api.websocket_command({vol.Required("type"): "bgregal/game", vol.Required("bgg_id"): int})
@websocket_api.async_response
async def ws_game(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    try:
        regal = get_regal(hass)
        plays = await hass.async_add_executor_job(regal.store.plays_for, msg["bgg_id"], 20)
    except HomeAssistantError as err:
        connection.send_error(msg["id"], "not_loaded", str(err))
        return
    connection.send_result(msg["id"], {"plays": plays})


@websocket_api.websocket_command({vol.Required("type"): "bgregal/subscribe"})
@callback
def ws_subscribe(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """Meldet jede Änderung; das Panel lädt dann bgregal/data neu."""

    @callback
    def forward() -> None:
        connection.send_message(websocket_api.event_message(msg["id"], {"changed": True}))

    connection.subscriptions[msg["id"]] = async_dispatcher_connect(hass, SIGNAL_UPDATE, forward)
    connection.send_result(msg["id"])
