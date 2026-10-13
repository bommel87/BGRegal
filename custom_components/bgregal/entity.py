"""Gemeinsame Basis der Entitäten."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SIGNAL_UPDATE, VERSION
from .coordinator import BgRegalCoordinator


class BgRegalEntity(CoordinatorEntity[BgRegalCoordinator]):
    """Aktualisiert sich nach jedem Sync und nach jeder lokalen Änderung."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: BgRegalCoordinator, key: str, platform: str, object_id: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        # Feste, sprachunabhängige Entity-IDs (z. B. sensor.bgregal_sammlung) für Automationen und ESP32
        self.entity_id = f"{platform}.{DOMAIN}_{object_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="BGRegal",
            manufacturer="BoardGameGeek",
            model=entry.title,
            sw_version=VERSION,
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def regal(self):
        return self.coordinator.regal

    @property
    def snapshot(self) -> dict:
        return self.coordinator.regal.snapshot

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_UPDATE, self.async_write_ha_state)
        )

    @property
    def available(self) -> bool:
        # Lokale Daten (Sitzung, Verleih …) gibt es auch, wenn BGG gerade nicht erreichbar ist
        return True
