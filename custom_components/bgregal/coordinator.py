"""Regelmäßiger Sync mit BGG."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import CONF_SCAN_HOURS, DEFAULTS, DOMAIN
from .core.errors import BggError
from .core.sync import SyncResult, run_sync
from .runtime import BgRegal

_LOGGER = logging.getLogger(__name__)


class BgRegalCoordinator(DataUpdateCoordinator[SyncResult]):
    """Startet den Sync im Intervall; die Daten selbst liegen in BgRegal.snapshot."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, regal: BgRegal) -> None:
        hours = int(entry.options.get(CONF_SCAN_HOURS, DEFAULTS[CONF_SCAN_HOURS]))
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=timedelta(hours=hours)
        )
        self.regal = regal
        self.last_error: str | None = None

    async def _async_update_data(self) -> SyncResult:
        try:
            result = await run_sync(
                self.regal.client, self.regal.store, self.hass.async_add_executor_job, dt_util.now()
            )
        except BggError as err:
            self.last_error = str(err)
            raise UpdateFailed(str(err)) from err
        self.last_error = None
        await self.regal.async_after_sync(result)
        return result
