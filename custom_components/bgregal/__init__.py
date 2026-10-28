"""BGRegal: BGG-Sammlung, Spielsitzung und Spieleabend in Home Assistant."""
from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .const import CONF_TOKEN, CONF_USERNAME, DB_FILE, DOMAIN, PANEL_URL, STATIC_URL, VERSION
from .coordinator import BgRegalCoordinator
from .core.client import BggClient
from .core.store import Store
from .http_rules import RulesFileView, RulesUploadView
from .http_vote import VoteApiView, VotePageView
from .llm_api import async_setup_llm_api
from .runtime import BgRegal
from .services import async_setup_services
from .websocket_api import async_setup_websocket

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BUTTON, Platform.CALENDAR, Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type BgRegalConfigEntry = ConfigEntry[BgRegalCoordinator]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Einmalig: Dateien fürs Panel, Dashboard-Kachel, Dienste, WebSocket, Abstimmseite, Anleitungen, LLM-API."""
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(Path(__file__).parent / "frontend"), False)]
    )
    add_extra_js_url(hass, f"{STATIC_URL}/bgregal-card.js?v={VERSION}")
    async_setup_services(hass)
    async_setup_websocket(hass)
    hass.http.register_view(VotePageView())
    hass.http.register_view(VoteApiView())
    hass.http.register_view(RulesUploadView())
    hass.http.register_view(RulesFileView())
    async_setup_llm_api(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: BgRegalConfigEntry) -> bool:
    client = BggClient(
        async_get_clientsession(hass), entry.data[CONF_USERNAME], entry.data[CONF_TOKEN]
    )
    store = await hass.async_add_executor_job(Store, hass.config.path(DB_FILE))
    regal = BgRegal(hass, entry, client, store)
    await regal.async_start()

    coordinator = BgRegalCoordinator(hass, entry, regal)
    entry.runtime_data = coordinator
    # Kein Warten auf den ersten Sync: mit vorhandener Datenbank geht es sofort los,
    # der Sync läuft im Hintergrund (der erste kann einige Minuten dauern).
    regal.first_sync = entry.async_create_background_task(
        hass, coordinator.async_refresh(), "bgregal_first_sync"
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL,
        webcomponent_name="bgregal-panel",
        module_url=f"{STATIC_URL}/bgregal-panel.js?v={VERSION}",
        sidebar_title="BGRegal",
        sidebar_icon="mdi:bookshelf",
        require_admin=False,
    )
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: BgRegalConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: BgRegalConfigEntry) -> bool:
    frontend.async_remove_panel(hass, PANEL_URL)
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        coordinator = entry.runtime_data
        # Erst laufende Syncs beenden, dann die Datenbank schließen
        await coordinator.async_shutdown()
        first_sync = coordinator.regal.first_sync
        if first_sync is not None and not first_sync.done():
            first_sync.cancel()
            with suppress(asyncio.CancelledError):
                await first_sync
        await coordinator.regal.async_stop()
    return unloaded
