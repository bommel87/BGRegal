"""Asynchroner Client für die BGG XML API2 (nur lesend)."""
from __future__ import annotations

import asyncio
import logging

import aiohttp

from .errors import BggAuthError, BggError, BggNotFoundError
from .parser import (
    BASEGAME,
    EXPANSION,
    CollectionItem,
    Play,
    ThingInfo,
    parse_collection,
    parse_plays,
    parse_things,
    parse_user_id,
)

_LOGGER = logging.getLogger(__name__)

API_BASE = "https://boardgamegeek.com/xmlapi2"
USER_AGENT = "HomeAssistant-BGRegal/0.3.0"
MAX_ATTEMPTS = 8
RETRY_DELAY = 5  # Sekunden; BGG antwortet bei Sammlungen zuerst oft mit 202
THING_BATCH_SIZE = 20  # BGG erlaubt höchstens 20 IDs pro /thing
REQUEST_GAP = 2  # Sekunden Pause zwischen Folgeabfragen, schont das Rate-Limit


class BggClient:
    """Dünner Client um die BGG XML API2."""

    def __init__(self, session: aiohttp.ClientSession, username: str, token: str) -> None:
        self._session = session
        self.username = username
        self._token = token

    async def _get(self, endpoint: str, params: dict) -> str:
        headers = {"User-Agent": USER_AGENT, "Authorization": f"Bearer {self._token}"}
        for attempt in range(MAX_ATTEMPTS):
            try:
                async with self._session.get(
                    f"{API_BASE}/{endpoint}",
                    params=params,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    if resp.status == 202:  # Anfrage steht in der Warteschlange
                        await asyncio.sleep(RETRY_DELAY)
                        continue
                    if resp.status == 429:  # Rate-Limit
                        await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                        continue
                    if resp.status in (401, 403):
                        raise BggAuthError("BGG lehnt den Zugriff ab (Token prüfen)")
                    if resp.status != 200:
                        raise BggError(f"BGG antwortete mit HTTP {resp.status}")
                    return await resp.text()
            except (aiohttp.ClientError, TimeoutError) as err:
                raise BggError(f"Verbindung zu BGG fehlgeschlagen: {err}") from err
        raise BggError("BGG hat die Daten nicht rechtzeitig geliefert")

    async def validate_user(self) -> None:
        """Prüft Token und Benutzernamen."""
        if parse_user_id(await self._get("user", {"name": self.username})) is None:
            raise BggNotFoundError(self.username)

    async def user_exists(self, username: str) -> bool:
        return parse_user_id(await self._get("user", {"name": username})) is not None

    async def fetch_owned(self) -> list[CollectionItem]:
        """Eigene Spiele und Erweiterungen (je eine Abfrage)."""
        common = {"username": self.username, "own": 1, "version": 1, "stats": 1}
        games = parse_collection(
            await self._get(
                "collection", {**common, "subtype": BASEGAME, "excludesubtype": EXPANSION}
            )
        )
        await asyncio.sleep(REQUEST_GAP)
        expansions = parse_collection(
            await self._get("collection", {**common, "subtype": EXPANSION})
        )
        for item in expansions:
            item.subtype = EXPANSION
        return games + expansions

    async def fetch_wishlist(self) -> list[CollectionItem]:
        return parse_collection(
            await self._get("collection", {"username": self.username, "wishlist": 1})
        )

    async def fetch_things(self, ids: list[int]) -> dict[int, ThingInfo]:
        """Spielinfos für beliebig viele IDs (in Paketen zu 20)."""
        result: dict[int, ThingInfo] = {}
        for start in range(0, len(ids), THING_BATCH_SIZE):
            if start:
                await asyncio.sleep(REQUEST_GAP)
            batch = ids[start : start + THING_BATCH_SIZE]
            result.update(
                parse_things(
                    await self._get("thing", {"id": ",".join(map(str, batch)), "stats": 1})
                )
            )
        return result

    async def fetch_plays(self, page: int) -> tuple[int, list[Play]]:
        """Eine Seite eigener Partien (100 je Seite, neueste zuerst)."""
        if page > 1:
            await asyncio.sleep(REQUEST_GAP)
        return parse_plays(await self._get("plays", {"username": self.username, "page": page}))
