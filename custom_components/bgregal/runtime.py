"""Laufzeit von BGRegal: verbindet den Kern mit Home Assistant.

Hält den aktuellen Datenstand (snapshot) für Entitäten und Panel und setzt alle Aktionen um:
Zuordnungen, NFC, Sitzung mit Licht und Sound, Vorschlag, Verleih, Mitspieler, Spieleabende.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import secrets
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.helpers.network import NoURLAvailableError, get_url
from homeassistant.util import dt as dt_util

from .const import (
    CONF_END_SCENE,
    CONF_LOAN_DAYS,
    CONF_LONG_MONTHS,
    CONF_MEDIA_PLAYER,
    CONF_NOTIFY,
    CONF_USERNAME,
    DEFAULTS,
    DOMAIN,
    EVENING_CANDIDATES,
    EVENT_UNKNOWN_CODE,
    INVENTORY_TIMEOUT_MIN,
    EVENT_LOAN_OVERDUE,
    EVENT_NEW_EXPANSION,
    EVENT_SESSION_ENDED,
    EVENT_SESSION_STARTED,
    LOAN_REPEAT_DAYS,
    RULES_DIR,
    SIGNAL_UPDATE,
    TAG_MAX_AGE_MIN,
)
from .core import session as sess
from .core import stats, suggest
from .core.bgstats import auto_winners, play_url, qr_svg
from .core.client import BggClient
from .core.errors import BggError
from .core.links import LinkCache
from .core.rules import RuleBooks
from .core.store import Store
from .core.suggest import DISLIKE_OPTIONS
from .core.sync import SyncResult
from .core.util import (
    normalize_ean,
    normalize_links,
    normalize_playlist,
    playlist_media_type,
    valid_light_profile,
)

_LOGGER = logging.getLogger(__name__)


class BgRegal:
    """Eine Instanz je Config-Entry (es gibt höchstens einen)."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: BggClient, store: Store) -> None:
        self.hass = hass
        self.entry = entry
        self.client = client
        self.store = store
        self.rules = RuleBooks(hass.config.path(RULES_DIR))
        self.links = LinkCache(hass.config.path(RULES_DIR))
        self.snapshot: dict[str, Any] = {}
        self.suggestion: dict[str, Any] = {"phase": "idle"}
        self._queue: list[dict[str, Any]] = []
        self._last_tag: tuple[str, datetime] | None = None
        self._started_playback = False
        self._unsubs: list = []
        self._rng = random.Random()
        self.first_sync: asyncio.Task | None = None
        self.inventory: dict[str, Any] | None = None  # laufende Inventur (nicht gespeichert)
        self._inventory_timer = None

    # ---- Lebenszyklus --------------------------------------------------------
    async def async_start(self) -> None:
        await self.async_refresh()
        self._unsubs.append(self.hass.bus.async_listen("tag_scanned", self._handle_tag))
        self._unsubs.append(
            async_track_time_interval(self.hass, self._check_loans, timedelta(hours=1))
        )
        self.hass.async_create_task(self._check_loans())

    async def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        if self._inventory_timer:
            self._inventory_timer()
            self._inventory_timer = None
        await self.hass.async_add_executor_job(self.store.close)

    @property
    def me(self) -> str:
        return self.entry.data[CONF_USERNAME]

    def opt(self, key: str) -> Any:
        value = self.entry.options.get(key, DEFAULTS[key])
        # Zahlenfelder im Optionsdialog liefern Kommazahlen (z. B. 24.0)
        return int(value) if isinstance(DEFAULTS[key], int) else value

    async def _run(self, fn, *args):
        return await self.hass.async_add_executor_job(fn, *args)

    # ---- Datenstand ----------------------------------------------------------
    def _build_snapshot(self) -> dict[str, Any]:
        today = dt_util.now().date()
        games = self.store.games()
        session = self.store.get_session()
        return {
            "me": self.me,
            "games": games,
            "stats": stats.overview(games, self.store.play_dates(), today, self.opt(CONF_LONG_MONTHS)),
            "loans": self.store.active_loans(),
            "players": self.store.players(self.me),
            "wishlist": self.store.wishlist(),
            "new_expansions": self.store.new_expansions(),
            "evenings": self.store.evenings(),
            "session": session,
            "shelves": self.store.shelves(),
            "rulebooks": self.rules.index(),
            "room_order": json.loads(self.store.get_meta("room_order") or "[]"),
            "last_sync": self.store.get_meta("last_sync"),
        }

    async def async_refresh(self) -> None:
        """Datenstand neu lesen, Regal-Geräte abgleichen und Entitäten benachrichtigen."""
        self.snapshot = await self._run(self._build_snapshot)
        self._sync_shelf_devices()
        async_dispatcher_send(self.hass, SIGNAL_UPDATE)

    # ---- Regale als Geräte -----------------------------------------------------
    def shelf_device_id(self, name: str) -> tuple[str, str]:
        return (DOMAIN, f"{self.entry.entry_id}_shelf_{name.lower()}")

    def shelf_device(self, name: str) -> dr.DeviceEntry | None:
        registry = dr.async_get(self.hass)
        ident = self.shelf_device_id(name)
        # Ab HA 2026.10 eindeutig je Config-Entry; ältere Versionen kennen nur async_get_device
        lookup = getattr(registry, "async_get_device_by_identifier", None)
        if lookup is not None:
            return lookup(ident, self.entry.entry_id)
        return registry.async_get_device(identifiers={ident})

    @callback
    def _sync_shelf_devices(self) -> None:
        """Ein Gerät je Regal, im zugeordneten Raum. Der Raum am Gerät ist maßgeblich:
        Ändert man ihn in Home Assistant, übernimmt das Panel ihn."""
        registry = dr.async_get(self.hass)
        # Hauptgerät zuerst, damit die Regale darauf verweisen können (gleiche Angaben wie in entity.py)
        main = registry.async_get_or_create(
            config_entry_id=self.entry.entry_id,
            identifiers={(DOMAIN, self.entry.entry_id)},
            name="BGRegal",
            manufacturer="BoardGameGeek",
            model=self.entry.title,
            entry_type=dr.DeviceEntryType.SERVICE,
        )
        wanted = {}
        for shelf in self.snapshot.get("shelves", []):
            ident = self.shelf_device_id(shelf["name"])
            wanted[ident] = shelf
            device = self.shelf_device(shelf["name"])
            if device is None:
                device = registry.async_get_or_create(
                    config_entry_id=self.entry.entry_id,
                    identifiers={ident},
                    name=shelf["name"],
                    manufacturer="BGRegal",
                    model="Regal",
                )
                # via_device_id gibt es in async_update_device in alten und neuen HA-Versionen
                registry.async_update_device(
                    device.id, via_device_id=main.id, area_id=shelf["area_id"] or None
                )
            elif (device.area_id or "") != shelf["area_id"]:
                # Raum wurde in Home Assistant am Gerät geändert -> übernehmen und speichern
                shelf["area_id"] = device.area_id or ""
                self.hass.async_add_executor_job(
                    self.store.set_shelf, shelf["name"], None, shelf["area_id"]
                )
        for device in dr.async_entries_for_config_entry(registry, self.entry.entry_id):
            idents = {i for i in device.identifiers if i[0] == DOMAIN and "_shelf_" in i[1]}
            if idents and not idents & wanted.keys():
                registry.async_remove_device(device.id)

    async def async_set_shelf(
        self,
        name: str,
        new_name: str | None = None,
        area_id: str | None = None,
        compartments: int | None = None,
        reversed_: bool | None = None,
        game_sort: str | None = None,
    ) -> None:
        shelf = next((s for s in self.snapshot.get("shelves", []) if s["name"].lower() == name.lower()), None)
        name = shelf["name"] if shelf else name.strip()
        if not name:
            raise ServiceValidationError("Name des Regals fehlt")
        if area_id and ar.async_get(self.hass).async_get_area(area_id) is None:
            raise ServiceValidationError(f"Den Bereich „{area_id}“ gibt es nicht")
        if new_name is not None and not new_name.strip():
            raise ServiceValidationError("Der neue Name darf nicht leer sein")
        await self._run(self.store.set_shelf, name, new_name, area_id, compartments, reversed_, game_sort)
        if area_id is not None:
            device = self.shelf_device(new_name or name)
            if device is not None:
                dr.async_get(self.hass).async_update_device(device.id, area_id=area_id or None)
        await self.async_refresh()

    async def async_set_sort_order(self, kind: str, order: list[str]) -> None:
        """Reihenfolge von Räumen (Bereichs-IDs, "" = ohne Raum), Regalen (Namen) oder Spielen (BGG-IDs)."""
        if kind == "rooms":
            registry = ar.async_get(self.hass)
            unknown = [a for a in order if a and registry.async_get_area(a) is None]
            if unknown:
                raise ServiceValidationError(f"Unbekannte Bereiche: {', '.join(unknown)}")
            await self._run(self.store.set_meta, "room_order", json.dumps(list(dict.fromkeys(order))))
        elif kind == "shelves":
            known = {s["name"].lower(): s["name"] for s in self.snapshot.get("shelves", [])}
            missing = [n for n in order if n.lower() not in known]
            if missing:
                raise ServiceValidationError(f"Unbekannte Regale: {', '.join(missing)}")
            await self._run(self.store.set_shelf_order, [known[n.lower()] for n in order])
        else:
            try:
                ids = [int(i) for i in order]
            except ValueError as err:
                raise ServiceValidationError("Spiele als BGG-IDs angeben") from err
            for bgg_id in ids:
                self.find_game(bgg_id)
            await self._run(self.store.set_game_order, ids)
        await self.async_refresh()

    async def async_remove_shelf(self, name: str) -> None:
        if not await self._run(self.store.remove_shelf, name):
            raise ServiceValidationError(f"„{name}“ ist nicht leer oder gibt es nicht")
        await self.async_refresh()

    def public_state(self) -> dict[str, Any]:
        """Alles, was das Panel braucht."""
        evenings = [
            {**e, "vote_url": self.vote_url(e["token"])} for e in self.snapshot.get("evenings", [])
        ]
        return {
            **self.snapshot,
            "evenings": evenings,
            "suggestion": self.suggestion_state(),
            "options": {
                "loan_days": self.opt(CONF_LOAN_DAYS),
                "long_months": self.opt(CONF_LONG_MONTHS),
                "media_player": self.opt(CONF_MEDIA_PLAYER),
            },
            "dislike_options": list(DISLIKE_OPTIONS),
            "inventory": self.inventory_state(),
        }

    async def async_after_sync(self, result: SyncResult) -> None:
        await self.async_refresh()
        if result.new_expansions:
            names = {g["bgg_id"]: g["name"] for g in self.snapshot["games"]}
            lines = []
            for exp in result.new_expansions:
                base = names.get(exp["base_id"], "?")
                self.hass.bus.async_fire(EVENT_NEW_EXPANSION, {**exp, "base_name": base})
                lines.append(f"- {exp['name']} (für {base})")
            await self.notify(
                "BGRegal: neue Erweiterungen", "\n".join(lines), "bgregal_new_expansions"
            )

    # ---- Spiele finden -------------------------------------------------------
    def find_game(self, bgg_id: int | None = None, name: str | None = None) -> dict[str, Any]:
        games = self.snapshot.get("games", [])
        if bgg_id is not None:
            for g in games:
                if g["bgg_id"] == bgg_id:
                    return g
            raise ServiceValidationError(f"BGG-ID {bgg_id} ist nicht in der Sammlung")
        if name:
            needle = name.strip().lower()
            exact = [g for g in games if g["name"].lower() == needle]
            if len(exact) == 1:
                return exact[0]
            part = [g for g in games if needle in g["name"].lower()]
            if len(part) == 1:
                return part[0]
            if not part:
                raise ServiceValidationError(f"Kein Spiel mit dem Namen „{name}“ gefunden")
            raise ServiceValidationError("Name nicht eindeutig: " + ", ".join(g["name"] for g in part[:5]))
        raise ServiceValidationError("bgg_id oder name angeben")

    # ---- Zuordnungen ---------------------------------------------------------
    async def async_set_game(self, game: dict[str, Any], fields: dict[str, Any]) -> None:
        clean: dict[str, Any] = {}
        for key in ("shelf", "nfc_tag", "manual_url", "light_profile"):
            if key in fields:
                clean[key] = (fields[key] or "").strip()
        if "compartment" in fields:
            value = fields["compartment"]
            clean["compartment"] = int(value) if value not in (None, "", 0) else None
        if "in_box" in fields or "in_base" in fields:
            clean["in_box"] = self._box_for(game, fields)
        if "playlist" in fields:
            try:
                clean["playlist"] = normalize_playlist(fields["playlist"])
            except ValueError as err:
                raise ServiceValidationError(f"Ungültiger Spotify-Link: {err}") from err
        if not valid_light_profile(clean.get("light_profile", "")):
            raise ServiceValidationError("Lichtprofil muss eine scene.* oder script.* Entität sein")
        if "ean" in fields:
            ean = normalize_ean(fields["ean"] or "")
            if ean is None:
                raise ServiceValidationError("Die EAN muss 8, 12, 13 oder 14 Ziffern haben")
            clean["ean"] = ean
        if "links" in fields:
            try:
                clean["links"] = json.dumps(normalize_links(fields["links"] or []), ensure_ascii=False)
            except ValueError as err:
                raise ServiceValidationError(f"Ungültiger Link: {err}") from err
        for key, lookup, label in (
            ("nfc_tag", self.store.game_by_tag, "Der Tag"),
            ("ean", self.store.game_by_ean, "Die EAN"),
        ):
            if clean.get(key):
                other = await self._run(lookup, clean[key])
                if other is not None and other != game["bgg_id"]:
                    raise ServiceValidationError(
                        f"{label} gehört schon zu „{self.find_game(other)['name']}“"
                    )
        await self._run(self.store.set_game_meta, game["bgg_id"], clean)
        await self.async_refresh()

    def _box_for(self, game: dict[str, Any], fields: dict[str, Any]) -> int | None:
        """Karton, in dem die Erweiterung liegen soll (BGG-ID) oder None für einen eigenen Platz.
        `in_box` hat Vorrang; `in_base: true` ist die Kurzform für das erste Basisspiel der Sammlung."""
        if "in_box" in fields:
            box = fields["in_box"] or None
        elif fields["in_base"]:
            owned = {g["bgg_id"] for g in self.snapshot.get("games", [])}
            box = next((b for b in game["base_ids"] if b in owned), None)
            if box is None:
                raise ServiceValidationError("Das Basisspiel ist nicht in der Sammlung")
        else:
            box = None if game.get("in_base") else game.get("in_box")
        if box is None:
            return None
        if not game["expansion"]:
            raise ServiceValidationError("Nur Erweiterungen können in einem anderen Karton liegen")
        host = self.find_game(int(box))
        if host["bgg_id"] == game["bgg_id"]:
            raise ServiceValidationError("Ein Spiel kann nicht in seinem eigenen Karton liegen")
        if host.get("in_box"):
            raise ServiceValidationError(f"„{host['name']}“ liegt selbst in einem Karton")
        if game.get("box_contents"):
            raise ServiceValidationError(f"In „{game['name']}“ liegen andere Erweiterungen")
        return host["bgg_id"]

    async def async_assign_scanned_tag(self, game: dict[str, Any]) -> str:
        if self._last_tag is None or dt_util.utcnow() - self._last_tag[1] > timedelta(
            minutes=TAG_MAX_AGE_MIN
        ):
            raise ServiceValidationError(
                f"In den letzten {TAG_MAX_AGE_MIN} Minuten wurde kein Tag gescannt"
            )
        await self.async_set_game(game, {"nfc_tag": self._last_tag[0]})
        return self._last_tag[0]

    # ---- NFC -----------------------------------------------------------------
    @callback
    def _handle_tag(self, event: Event) -> None:
        tag_id = event.data.get("tag_id")
        if not tag_id:
            return
        self._last_tag = (str(tag_id), dt_util.utcnow())
        self.hass.async_create_task(self._process_tag(str(tag_id)))

    async def _process_tag(self, tag_id: str) -> None:
        bgg_id = await self._run(self.store.game_by_tag, tag_id)
        if bgg_id is None:
            return
        try:
            if self.inventory:
                await self.async_inventory_place(self.find_game(bgg_id))
            else:
                await self._toggle_session(self.find_game(bgg_id))
        except HomeAssistantError as err:
            _LOGGER.warning("NFC-Aktion fehlgeschlagen: %s", err)

    async def _toggle_session(self, game: dict[str, Any]) -> str:
        """Wie ein Scan: erster startet die Sitzung, zweiter beendet sie. Liefert, was passiert ist."""
        current = self.snapshot.get("session")
        if current and current["state"] == sess.RUNNING:
            if current["bgg_id"] == game["bgg_id"]:
                await self.async_end_session()
                return "ended"
            _LOGGER.warning("„%s“ gescannt, aber „%s“ läuft noch", game["name"], current["name"])
            return "busy"
        await self.async_start_session(game)
        return "started"

    async def async_scan_code(self, code: str) -> dict[str, Any]:
        """EAN-Barcode (oder Tag-ID) gescannt: Sitzung starten/beenden oder unbekannten Code melden."""
        raw = code.strip()
        ean = normalize_ean(raw)
        bgg_id = await self._run(self.store.game_by_ean, ean) if ean else None
        if bgg_id is None:
            bgg_id = await self._run(self.store.game_by_tag, raw)
        if bgg_id is None:
            self.hass.bus.async_fire(EVENT_UNKNOWN_CODE, {"code": ean or raw})
            return {"result": "unknown", "code": ean or raw}
        game = self.find_game(bgg_id)
        if self.inventory:
            return {**await self.async_inventory_place(game), "code": ean or raw}
        result = await self._toggle_session(game)
        current = self.snapshot.get("session")
        return {"result": result, "code": ean or raw, "bgg_id": bgg_id, "name": game["name"],
                "running": current["name"] if result == "busy" and current else None}

    # ---- Inventur: Fach für Fach durchscannen ------------------------------------
    def inventory_state(self) -> dict[str, Any] | None:
        inv = self.inventory
        if not inv:
            return None
        placed_ids = {p["bgg_id"] for p in inv["placed"]}
        missing = [
            {"bgg_id": g["bgg_id"], "name": g["name"]}
            for g in self.snapshot.get("games", [])
            if g["shelf"].lower() == inv["shelf"].lower() and g["compartment"] == inv["compartment"]
            and g["bgg_id"] not in placed_ids and not g["in_box"]
        ]
        return {
            "shelf": inv["shelf"],
            "compartment": inv["compartment"],
            "placed": [{"bgg_id": p["bgg_id"], "name": p["name"]} for p in inv["placed"]],
            "missing": missing,
        }

    def _require_inventory(self) -> dict[str, Any]:
        if not self.inventory:
            raise ServiceValidationError("Es läuft keine Inventur")
        return self.inventory

    @callback
    def _inventory_touch(self) -> None:
        """Nach INVENTORY_TIMEOUT_MIN ohne Scan endet die Inventur von selbst."""
        if self._inventory_timer:
            self._inventory_timer()
        self._inventory_timer = async_call_later(
            self.hass, INVENTORY_TIMEOUT_MIN * 60, self._inventory_timeout
        )

    @callback
    def _inventory_timeout(self, _now: datetime | None = None) -> None:
        self._inventory_timer = None
        if self.inventory:
            _LOGGER.info("Inventur „%s“ nach %s Minuten ohne Scan beendet", self.inventory["shelf"], INVENTORY_TIMEOUT_MIN)
            self.inventory = None
            async_dispatcher_send(self.hass, SIGNAL_UPDATE)

    async def async_start_inventory(self, shelf: str, compartment: int = 1) -> dict[str, Any]:
        name = shelf.strip()
        if not name:
            raise ServiceValidationError("Name des Regals fehlt")
        existing = next((s for s in self.snapshot.get("shelves", []) if s["name"].lower() == name.lower()), None)
        if existing:
            name = existing["name"]
        else:
            await self._run(self.store.set_shelf, name)  # neues Regal anlegen
        self.inventory = {"shelf": name, "compartment": max(compartment, 1), "placed": []}
        self._inventory_touch()
        await self.async_refresh()
        return self.inventory_state()

    async def async_inventory_place(self, game: dict[str, Any]) -> dict[str, Any]:
        """Spiel ins aktuelle Fach stellen; merkt sich den alten Standort für Rückgängig."""
        inv = self._require_inventory()
        self._inventory_touch()
        result = {"result": "placed", "bgg_id": game["bgg_id"], "name": game["name"],
                  "shelf": inv["shelf"], "compartment": inv["compartment"]}
        if any(p["bgg_id"] == game["bgg_id"] for p in inv["placed"]):
            return {**result, "result": "already"}
        inv["placed"].append({
            "bgg_id": game["bgg_id"], "name": game["name"], "shelf": game["shelf"],
            "compartment": game["compartment"], "in_box": game["in_box"], "position": game.get("position"),
        })
        await self._run(
            self.store.set_game_meta, game["bgg_id"],
            # Scan-Reihenfolge = Reihenfolge im Fach
            {"shelf": inv["shelf"], "compartment": inv["compartment"], "in_box": None,
             "position": len(inv["placed"]) - 1},
        )
        await self.async_refresh()
        return result

    async def async_inventory_undo(self) -> dict[str, Any] | None:
        inv = self._require_inventory()
        self._inventory_touch()
        if not inv["placed"]:
            return None
        last = inv["placed"].pop()
        await self._run(
            self.store.set_game_meta, last["bgg_id"],
            {"shelf": last["shelf"], "compartment": last["compartment"], "in_box": last["in_box"],
             "position": last.get("position")},
        )
        await self.async_refresh()
        return {"bgg_id": last["bgg_id"], "name": last["name"]}

    async def _clear_missing(self) -> list[str]:
        """Spiele, die laut BGRegal im Fach standen, aber nicht gescannt wurden -> ohne Standort."""
        state = self.inventory_state() or {"missing": []}
        for g in state["missing"]:
            await self._run(self.store.set_game_meta, g["bgg_id"], {"shelf": "", "compartment": None})
        return [g["name"] for g in state["missing"]]

    async def async_inventory_next(self, clear_missing: bool, compartment: int | None = None) -> dict[str, Any]:
        inv = self._require_inventory()
        cleared = await self._clear_missing() if clear_missing else []
        inv["compartment"] = compartment if compartment else inv["compartment"] + 1
        inv["placed"] = []
        self._inventory_touch()
        await self.async_refresh()
        return {"cleared": cleared, "inventory": self.inventory_state()}

    async def async_stop_inventory(self, clear_missing: bool) -> dict[str, Any]:
        self._require_inventory()
        cleared = await self._clear_missing() if clear_missing else []
        self.inventory = None
        if self._inventory_timer:
            self._inventory_timer()
            self._inventory_timer = None
        await self.async_refresh()
        return {"cleared": cleared}

    # ---- Sitzung -------------------------------------------------------------
    async def _save_session(self, data: dict[str, Any] | None) -> None:
        await self._run(self.store.set_session, data)
        await self.async_refresh()

    def _session(self, *states: str) -> dict[str, Any]:
        current = self.snapshot.get("session")
        if not current or (states and current["state"] not in states):
            raise ServiceValidationError("Es läuft keine passende Spielsitzung")
        return current

    async def async_start_session(
        self, game: dict[str, Any] | None = None, order: list[str] | None = None
    ) -> dict[str, Any]:
        if game is None:
            if self.suggestion.get("phase") != "accepted":
                raise ServiceValidationError("Spiel angeben oder zuerst einen Vorschlag annehmen")
            game = self.find_game(self.suggestion["game"]["bgg_id"])
        current = self.snapshot.get("session")
        if current and current["state"] == sess.RUNNING:
            raise ServiceValidationError(f"Es läuft schon eine Sitzung: {current['name']}")
        data = sess.start(game["bgg_id"], game["name"], dt_util.now(), order)
        # Vorschlag vor dem Speichern zurücksetzen, damit beide Sensoren gemeinsam aktualisiert werden
        self.suggestion = {"phase": "idle"}
        self._queue = []
        await self._save_session(data)
        await self._activate_profiles(game)
        self.hass.bus.async_fire(
            EVENT_SESSION_STARTED, {"bgg_id": game["bgg_id"], "name": game["name"]}
        )
        return data

    async def async_end_session(self) -> dict[str, Any]:
        current = self._session(sess.RUNNING)
        data = sess.end(current, dt_util.now())
        await self._save_session(data)
        await self._deactivate_profiles()
        self.hass.bus.async_fire(
            EVENT_SESSION_ENDED,
            {"bgg_id": data["bgg_id"], "name": data["name"], "duration_min": sess.duration_min(data)},
        )
        return data

    async def async_cancel_session(self) -> None:
        """Verwirft eine laufende oder schließt eine beendete Sitzung."""
        current = self._session()
        if current["state"] == sess.RUNNING:
            await self._deactivate_profiles()
        await self._save_session(None)

    async def async_update_session(self, action: str, order: list[str] | None = None) -> None:
        current = self._session(sess.RUNNING)
        if action == "next_player":
            data = sess.next_player(current)
        elif action == "next_round":
            data = sess.next_round(current)
        else:
            data = sess.set_order(current, order or [])
        await self._save_session(data)

    async def async_finish_session(
        self, players: list[dict[str, Any]], note: str = "", auto_winner: bool = True
    ) -> dict[str, Any]:
        """Abschluss: Mitspieler, Punkte, Gewinner -> Link und QR-Code für BG Stats."""
        current = self.snapshot.get("session")
        if current and current["state"] == sess.RUNNING:
            current = await self.async_end_session()
        current = self._session(sess.FINISHED)
        known = {p["name"].lower(): p for p in self.snapshot.get("players", [])}
        lineup = []
        for p in players:
            name = str(p.get("name") or "").strip()
            if not name:
                continue
            is_me = name.lower() == self.me.lower()
            username = self.me if is_me else (p.get("username") or known.get(name.lower(), {}).get("bgg_username") or "")
            lineup.append({"name": name, "username": username, "score": p.get("score"),
                           "winner": bool(p.get("winner"))})
        if not any(p["winner"] for p in lineup) and auto_winner:
            winners = auto_winners(lineup)
            for p in lineup:
                p["winner"] = p["name"].lower() in winners
        ended = dt_util.parse_datetime(current["ended"]) or dt_util.now()
        url = play_url(
            self.me, current["name"], current["bgg_id"], ended, sess.duration_min(current),
            lineup, note, source_id=f"bgregal-{self.me.lower()}-{int(ended.timestamp())}",
        )
        svg = await self._run(qr_svg, url)
        data = {**current, "result": {"url": url, "players": lineup, "note": note}}
        await self._save_session(data)
        return {"url": url, "qr_svg": svg}

    async def async_session_qr(self) -> dict[str, Any]:
        current = self._session(sess.FINISHED)
        if not current.get("result"):
            raise ServiceValidationError("Die Sitzung ist noch nicht abgeschlossen")
        url = current["result"]["url"]
        return {"url": url, "qr_svg": await self._run(qr_svg, url)}

    async def _call(self, domain: str, service: str, data: dict[str, Any]) -> None:
        try:
            await self.hass.services.async_call(domain, service, data, blocking=False)
        except HomeAssistantError as err:
            _LOGGER.warning("Aufruf %s.%s fehlgeschlagen: %s", domain, service, err)

    async def _activate_profiles(self, game: dict[str, Any]) -> None:
        profile = game.get("light_profile")
        if profile:
            await self._call(profile.split(".")[0], "turn_on", {"entity_id": profile})
        player = self.opt(CONF_MEDIA_PLAYER)
        playlist = game.get("playlist")
        self._started_playback = False
        if player and playlist:
            await self._call(
                "media_player", "play_media",
                {"entity_id": player, "media_content_id": playlist,
                 "media_content_type": playlist_media_type(playlist)},
            )
            self._started_playback = True

    async def _deactivate_profiles(self) -> None:
        player = self.opt(CONF_MEDIA_PLAYER)
        if player and self._started_playback:
            await self._call("media_player", "media_pause", {"entity_id": player})
        self._started_playback = False
        end_scene = self.opt(CONF_END_SCENE)
        if end_scene:
            await self._call(end_scene.split(".")[0], "turn_on", {"entity_id": end_scene})

    # ---- Vorschlag -----------------------------------------------------------
    def suggestion_state(self) -> dict[str, Any]:
        return {k: v for k, v in self.suggestion.items() if k != "queue"}

    async def async_suggest(
        self,
        players: int | None,
        mode: str,
        game_type: str,
        max_playtime: int | None,
        attendees: list[str] | None = None,
    ) -> dict[str, Any]:
        dislikes = self._dislikes(attendees or [])
        self._queue = suggest.rank(
            self.snapshot.get("games", []), dt_util.now().date(), self._rng,
            players=players, mode=mode, game_type=game_type, max_playtime=max_playtime,
            dislikes=dislikes,
        )
        self._next_suggestion()
        return self.suggestion_state()

    def _dislikes(self, names: list[str]) -> set[str]:
        wanted = {n.lower() for n in names}
        return {
            d for p in self.snapshot.get("players", []) if p["name"].lower() in wanted
            for d in p.get("dislikes", [])
        }

    def _next_suggestion(self) -> None:
        if not self._queue:
            self.suggestion = {"phase": "none"}
        else:
            game = self._queue.pop(0)
            self.suggestion = {"phase": "suggested", "game": self._game_brief(game),
                               "remaining": len(self._queue)}
        async_dispatcher_send(self.hass, SIGNAL_UPDATE)

    @staticmethod
    def _game_brief(game: dict[str, Any]) -> dict[str, Any]:
        keys = ("bgg_id", "name", "thumbnail", "shelf", "compartment", "min_players", "max_players",
                "playing_time", "mode", "plays", "last_play")
        return {k: game.get(k) for k in keys}

    async def async_reject_suggestion(self) -> dict[str, Any]:
        if self.suggestion.get("phase") != "suggested":
            raise ServiceValidationError("Es gibt gerade keinen Vorschlag")
        self._next_suggestion()
        return self.suggestion_state()

    async def async_accept_suggestion(self) -> dict[str, Any]:
        if self.suggestion.get("phase") != "suggested":
            raise ServiceValidationError("Es gibt gerade keinen Vorschlag")
        self.suggestion = {**self.suggestion, "phase": "accepted"}
        async_dispatcher_send(self.hass, SIGNAL_UPDATE)
        return self.suggestion_state()

    async def async_reset_suggestion(self) -> None:
        self._queue = []
        self.suggestion = {"phase": "idle"}
        async_dispatcher_send(self.hass, SIGNAL_UPDATE)

    # ---- Verleih -------------------------------------------------------------
    async def async_lend(self, game: dict[str, Any], borrower: str) -> None:
        borrower = borrower.strip()
        if not borrower:
            raise ServiceValidationError("An wen? Bitte einen Namen angeben")
        await self._run(self.store.lend, game["bgg_id"], borrower, dt_util.now().date().isoformat())
        await self.async_refresh()

    async def async_return(self, game: dict[str, Any]) -> None:
        if not await self._run(self.store.return_game, game["bgg_id"], dt_util.now().date().isoformat()):
            raise ServiceValidationError(f"„{game['name']}“ ist nicht verliehen")
        await self.async_refresh()

    async def _check_loans(self, _now: datetime | None = None) -> None:
        today = dt_util.now().date()
        limit = self.opt(CONF_LOAN_DAYS)
        for loan in await self._run(self.store.active_loans):
            days = (today - date.fromisoformat(loan["since"][:10])).days
            if days < limit:
                continue
            reminded = loan.get("reminded")
            if reminded and (today - date.fromisoformat(reminded[:10])).days < LOAN_REPEAT_DAYS:
                continue
            name = loan.get("name") or f"BGG {loan['bgg_id']}"
            self.hass.bus.async_fire(
                EVENT_LOAN_OVERDUE,
                {"bgg_id": loan["bgg_id"], "name": name, "borrower": loan["borrower"], "days": days},
            )
            await self.notify(
                "BGRegal: Spiel verliehen",
                f"„{name}“ ist seit {days} Tagen an {loan['borrower']} verliehen.",
                f"bgregal_loan_{loan['id']}",
            )
            await self._run(self.store.mark_reminded, loan["id"], today.isoformat())

    # ---- Mitspieler ----------------------------------------------------------
    async def async_set_player(
        self,
        name: str,
        bgg_username: str | None,
        dislikes: list[str] | None,
        hidden: bool | None = None,
    ) -> None:
        name = name.strip()
        if not name:
            raise ServiceValidationError("Name fehlt")
        if name.lower() == self.me.lower():
            raise ServiceValidationError("Du selbst bist kein Mitspieler")
        if bgg_username:
            bgg_username = bgg_username.strip()
            try:
                exists = await self.client.user_exists(bgg_username)
            except BggError as err:
                raise HomeAssistantError(f"BGG nicht erreichbar: {err}") from err
            if not exists:
                raise ServiceValidationError(f"BGG-Benutzer „{bgg_username}“ gibt es nicht")
        if dislikes is not None:
            unknown = set(dislikes) - set(DISLIKE_OPTIONS)
            if unknown:
                raise ServiceValidationError(f"Unbekannte Vorliebe: {', '.join(sorted(unknown))}")
        await self._run(self.store.set_player, name, bgg_username, dislikes, hidden)
        await self.async_refresh()

    async def async_remove_player(self, name: str) -> None:
        if not await self._run(self.store.remove_player, name.strip()):
            raise ServiceValidationError(f"„{name}“ ist kein selbst angelegter Mitspieler")
        await self.async_refresh()

    # ---- Spieleabende --------------------------------------------------------
    def vote_url(self, token: str, base_url: str | None = None) -> str:
        """Link zur Abstimmseite. `base_url` (z. B. die Adresse, unter der das Panel offen ist)
        hat Vorrang, weil die in HA hinterlegte externe URL oft ohne Port eingetragen ist."""
        path = f"/api/bgregal/vote/{token}"
        if base_url:
            return base_url.rstrip("/") + path
        try:
            return get_url(self.hass, prefer_external=True) + path
        except NoURLAvailableError:
            return path

    def _evening(self, evening_id: int) -> dict[str, Any]:
        for e in self.snapshot.get("evenings", []):
            if e["id"] == evening_id:
                return e
        raise ServiceValidationError(f"Spieleabend {evening_id} gibt es nicht")

    async def async_plan_evening(
        self,
        title: str,
        start: datetime,
        guests: list[str],
        max_playtime: int | None,
        candidates: list[int] | None,
        base_url: str | None = None,
    ) -> dict[str, Any]:
        guests = [g.strip() for g in guests if g.strip()]
        if candidates is None:
            ranked = suggest.rank(
                self.snapshot.get("games", []), start.date(), self._rng,
                players=len(guests) + 1, max_playtime=max_playtime, dislikes=self._dislikes(guests),
            )
            candidates = [g["bgg_id"] for g in ranked[:EVENING_CANDIDATES]]
        else:
            for bgg_id in candidates:
                self.find_game(bgg_id)
        token = secrets.token_urlsafe(16)
        evening_id = await self._run(
            self.store.add_evening, title.strip() or "Spieleabend", start.isoformat(timespec="minutes"),
            max_playtime, token, guests, candidates,
        )
        await self.async_refresh()
        url = self.vote_url(token, base_url)
        return {"evening_id": evening_id, "vote_url": url, "qr_svg": await self._run(qr_svg, url)}

    async def async_set_candidates(self, evening_id: int, candidates: list[int]) -> None:
        self._evening(evening_id)
        for bgg_id in candidates:
            self.find_game(bgg_id)
        await self._run(self.store.set_candidates, evening_id, candidates)
        await self.async_refresh()

    async def async_remove_evening(self, evening_id: int) -> None:
        if not await self._run(self.store.remove_evening, evening_id):
            raise ServiceValidationError(f"Spieleabend {evening_id} gibt es nicht")
        await self.async_refresh()

    async def async_vote(self, evening_id: int, voter: str, bgg_ids: list[int]) -> None:
        evening = self._evening(evening_id)
        self._check_vote(evening, voter, bgg_ids)
        await self._run(self.store.set_votes, evening_id, voter.strip(), bgg_ids)
        await self.async_refresh()

    def _check_vote(self, evening: dict[str, Any], voter: str, bgg_ids: list[int]) -> None:
        allowed = {g.lower() for g in evening["guests"]} | {self.me.lower()}
        if voter.strip().lower() not in allowed:
            raise ServiceValidationError(f"„{voter}“ ist kein Gast dieses Abends")
        if set(bgg_ids) - set(evening["candidates"]):
            raise ServiceValidationError("Nur Spiele aus der Auswahl des Abends sind möglich")

    async def async_evening_qr(self, evening_id: int, base_url: str | None = None) -> dict[str, Any]:
        url = self.vote_url(self._evening(evening_id)["token"], base_url)
        return {"vote_url": url, "qr_svg": await self._run(qr_svg, url)}

    def evening_open(self, evening: dict[str, Any]) -> bool:
        """Abstimmen geht bis zum Morgen nach dem Abend (6 Uhr)."""
        start = dt_util.parse_datetime(evening["start"])
        if start is None:
            return False
        if start.tzinfo is None:
            start = start.replace(tzinfo=dt_util.get_default_time_zone())
        closes = datetime.combine(start.date() + timedelta(days=1), datetime.min.time()).replace(
            hour=6, tzinfo=start.tzinfo
        )
        return dt_util.now() < closes

    async def async_public_vote(self, token: str, voter: str, bgg_ids: list[int]) -> None:
        """Stimme von der Abstimmseite (ohne HA-Login)."""
        evening = await self._run(self.store.evening_by_token, token)
        if evening is None or not self.evening_open(evening):
            raise ServiceValidationError("Abstimmung nicht gefunden oder beendet")
        self._check_vote(evening, voter, bgg_ids)
        await self._run(self.store.set_votes, evening["id"], voter.strip(), bgg_ids)
        await self.async_refresh()

    # ---- Benachrichtigung ----------------------------------------------------
    async def notify(self, title: str, message: str, notification_id: str) -> None:
        await self._call(
            "persistent_notification", "create",
            {"title": title, "message": message, "notification_id": notification_id},
        )
        target = self.opt(CONF_NOTIFY)
        if target and "." in target:
            domain, service = target.split(".", 1)
            await self._call(domain, service, {"title": title, "message": message})

    async def async_dismiss_expansions(self) -> None:
        await self._run(self.store.dismiss_new_expansions)
        await self.async_refresh()
