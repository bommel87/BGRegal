"""Knopf: sofort mit BGG synchronisieren."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import BgRegalEntity


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([BgRegalSyncButton(entry.runtime_data)])


class BgRegalSyncButton(BgRegalEntity, ButtonEntity):
    _attr_icon = "mdi:cloud-sync"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "sync", "button", "sync")

    async def async_press(self) -> None:
        await self.coordinator.async_request_refresh()
