"""Sensoren für Automationen und das ESP32-Display."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from .const import DOMAIN, SIGNAL_UPDATE
from .core import session as sess
from .core.suggest import summary_line
from .entity import BgRegalEntity

LIST_LIMIT = 50  # Listen in Attributen kürzen, damit die Datenbank von HA klein bleibt

SUMMARY_LABELS = {
    "de": {"players": "Spieler", "minutes": "Min", "cooperative": "Kooperativ",
           "competitive": "Wettkampf", "semi": "Semi-kooperativ"},
    "en": {"players": "players", "minutes": "min", "cooperative": "Cooperative",
           "competitive": "Competitive", "semi": "Semi-cooperative"},
}


def _games(snap: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {g["bgg_id"]: g for g in snap.get("games", [])}


def _location(game: dict[str, Any] | None) -> str:
    if not game:
        return ""
    shelf, fach = game.get("shelf") or "", game.get("compartment")
    if shelf and fach:
        return f"{shelf}, Fach {fach}"
    return shelf or (f"Fach {fach}" if fach else "")


@dataclass(frozen=True)
class Spec:
    key: str
    object_id: str
    value: Callable[[Any], Any]
    attrs: Callable[[Any], dict[str, Any]] = lambda _r: {}
    icon: str | None = None
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass | None = None


def _collection_attrs(regal) -> dict[str, Any]:
    snap = regal.snapshot
    games = _games(snap)
    s = snap.get("stats", {})
    return {
        "expansions": s.get("expansions", 0),
        "pile_of_shame": len(s.get("pile_of_shame", [])),
        "pile_of_shame_games": [games[i]["name"] for i in s.get("pile_of_shame", [])[:LIST_LIMIT]],
        "long_unplayed": len(s.get("long_unplayed", [])),
    }


def _plays_attrs(regal) -> dict[str, Any]:
    s = regal.snapshot.get("stats", {})
    games = [g for g in regal.snapshot.get("games", []) if g.get("last_play")]
    last = max(games, key=lambda g: g["last_play"], default=None)
    return {
        "this_month": s.get("plays_this_month", 0),
        "h_index": s.get("h_index", 0),
        "last_play_game": last["name"] if last else None,
        "last_play_date": last["last_play"] if last else None,
    }


def _session_state(regal) -> str:
    current = regal.snapshot.get("session")
    return current["state"] if current else "idle"


def _session_attrs(regal) -> dict[str, Any]:
    current = regal.snapshot.get("session")
    if not current:
        return {}
    game = _games(regal.snapshot).get(current["bgg_id"])
    return {
        "bgg_id": current["bgg_id"],
        "name": current["name"],
        "started": current["started"],
        "ended": current.get("ended"),
        "duration_min": sess.duration_min(current, dt_util.now()),
        "round": current.get("round", 1),
        "current_player": sess.current_player(current) or "",
        "order": current.get("order", []),
        "location": _location(game),
        "manual_url": (game or {}).get("manual_url", ""),
        "thumbnail": (game or {}).get("thumbnail"),
        "completed": bool(current.get("result")),
    }


def _suggestion_attrs(regal) -> dict[str, Any]:
    sug = regal.suggestion
    game = sug.get("game")
    if not game:
        return {}
    lang = "de" if regal.hass.config.language.startswith("de") else "en"
    return {
        "bgg_id": game["bgg_id"],
        "name": game["name"],
        "location": _location(game),
        "summary": summary_line(game, SUMMARY_LABELS[lang]),
        "thumbnail": game.get("thumbnail"),
        "remaining": sug.get("remaining", 0),
    }


def _loans_attrs(regal) -> dict[str, Any]:
    today = dt_util.now().date()
    return {
        "loans": [
            {"name": l.get("name"), "borrower": l["borrower"], "since": l["since"],
             "days": (today - datetime.fromisoformat(l["since"][:10]).date()).days}
            for l in regal.snapshot.get("loans", [])[:LIST_LIMIT]
        ]
    }


def _expansion_attrs(regal) -> dict[str, Any]:
    return {
        "expansions": [
            {"name": e["name"], "base": e["base_name"], "bgg_id": e["bgg_id"]}
            for e in regal.snapshot.get("new_expansions", [])[:LIST_LIMIT]
        ]
    }


def _last_sync(regal) -> datetime | None:
    value = regal.snapshot.get("last_sync")
    return dt_util.parse_datetime(value) if value else None


SPECS = (
    Spec("collection", "sammlung", lambda r: r.snapshot.get("stats", {}).get("games", 0),
         _collection_attrs, icon="mdi:bookshelf", state_class=SensorStateClass.MEASUREMENT),
    Spec("plays", "partien", lambda r: r.snapshot.get("stats", {}).get("plays_total", 0),
         _plays_attrs, icon="mdi:dice-multiple", state_class=SensorStateClass.TOTAL),
    Spec("session", "sitzung", _session_state, _session_attrs, icon="mdi:timer-play-outline"),
    Spec("suggestion", "vorschlag", lambda r: r.suggestion.get("phase", "idle"), _suggestion_attrs,
         icon="mdi:lightbulb-on-outline"),
    Spec("loans", "verliehen", lambda r: len(r.snapshot.get("loans", [])), _loans_attrs,
         icon="mdi:hand-extended-outline"),
    Spec("new_expansions", "neuheiten", lambda r: len(r.snapshot.get("new_expansions", [])),
         _expansion_attrs, icon="mdi:new-box"),
    Spec("last_sync", "letzter_sync", _last_sync,
         lambda r: {"error": r.entry.runtime_data.last_error}, icon="mdi:sync",
         device_class=SensorDeviceClass.TIMESTAMP),
)


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(BgRegalSensor(coordinator, spec) for spec in SPECS)

    known: set[str] = set()

    @callback
    def add_new_shelves() -> None:
        """Ein Sensor je Regal; neue Regale bekommen ihren Sensor automatisch."""
        current = {s["name"].lower(): s["name"] for s in coordinator.regal.snapshot.get("shelves", [])}
        new = [ShelfSensor(coordinator, name) for key, name in current.items() if key not in known]
        known.intersection_update(current)  # entfernte Regale: Gerät samt Sensor löscht die Laufzeit
        known.update(current)
        if new:
            async_add_entities(new)

    add_new_shelves()
    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_UPDATE, add_new_shelves))


class ShelfSensor(CoordinatorEntity, SensorEntity):
    """Ein Regal als Gerät im Raum; Zustand = Anzahl Spiele darin."""

    _attr_has_entity_name = True
    _attr_name = None  # heißt wie das Gerät, also wie das Regal
    _attr_translation_key = "shelf"
    _attr_icon = "mdi:bookshelf"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _unrecorded_attributes = frozenset({"games"})

    def __init__(self, coordinator, name: str) -> None:
        super().__init__(coordinator)
        self._key = name.lower()
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_shelf_{self._key}"
        self.entity_id = f"sensor.{DOMAIN}_regal_{slugify(name)}"
        self._attr_device_info = DeviceInfo(identifiers={coordinator.regal.shelf_device_id(name)})

    def _shelf(self) -> dict[str, Any] | None:
        return next(
            (s for s in self.coordinator.regal.snapshot.get("shelves", []) if s["name"].lower() == self._key),
            None,
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_UPDATE, self.async_write_ha_state))

    @property
    def available(self) -> bool:
        return self._shelf() is not None

    @property
    def native_value(self) -> int | None:
        shelf = self._shelf()
        return shelf["games"] if shelf else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        shelf = self._shelf()
        if not shelf:
            return {}
        games = [
            g["name"] for g in self.coordinator.regal.snapshot.get("games", [])
            if g["shelf"].lower() == self._key and not (g["expansion"] and g["in_base"])
        ]
        return {"compartments": shelf["compartments"], "layout": shelf["layout"], "games": games[:LIST_LIMIT]}


class BgRegalSensor(BgRegalEntity, SensorEntity):
    _unrecorded_attributes = frozenset(
        {"pile_of_shame_games", "loans", "expansions", "order", "thumbnail", "manual_url"}
    )

    def __init__(self, coordinator, spec: Spec) -> None:
        super().__init__(coordinator, spec.key, "sensor", spec.object_id)
        self._spec = spec
        self._attr_icon = spec.icon
        self._attr_device_class = spec.device_class
        self._attr_state_class = spec.state_class

    @property
    def native_value(self):
        return self._spec.value(self.regal)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._spec.attrs(self.regal)
