"""Abgleich mit BGG: Sammlung, Spielinfos, Partien, Wunschliste, neue Erweiterungen."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Protocol

from .errors import BggError
from .parser import EXPANSION, CollectionItem, Play, ThingInfo
from .store import Store

INFO_MAX_AGE = timedelta(days=7)  # Spielinfos und Erweiterungslisten wöchentlich auffrischen
FULL_PLAYS_EVERY = timedelta(days=7)  # alle Partien vollständig laden (erkennt Änderungen/Löschungen)

Runner = Callable[..., Awaitable[Any]]


class Client(Protocol):
    async def fetch_owned(self) -> list[CollectionItem]: ...
    async def fetch_wishlist(self) -> list[CollectionItem]: ...
    async def fetch_things(self, ids: list[int]) -> dict[int, ThingInfo]: ...
    async def fetch_plays(self, page: int) -> tuple[int, list[Play]]: ...


@dataclass
class SyncResult:
    games: int = 0
    new_plays: int = 0
    new_expansions: list[dict[str, Any]] = field(default_factory=list)


async def run_sync(client: Client, store: Store, run: Runner, now: datetime) -> SyncResult:
    """Ein vollständiger Sync. `run` führt Datenbankaufrufe aus (in HA: im Executor)."""
    stamp = now.isoformat(timespec="seconds")
    result = SyncResult()

    owned = await client.fetch_owned()
    if not owned and await run(store.game_count):
        # Eine plötzlich leere Sammlung ist fast immer ein BGG-Aussetzer -> nichts löschen
        raise BggError("BGG hat eine leere Sammlung geliefert; Sync abgebrochen")
    await run(store.replace_collection, owned)
    result.games = len(owned)

    stale = await run(store.ids_needing_info, (now - INFO_MAX_AGE).isoformat(timespec="seconds"))
    if stale:
        infos = await client.fetch_things(stale)
        await run(store.update_info, infos, stamp)
        subtypes = {i.bgg_id: i.subtype for i in owned}
        for bgg_id, info in infos.items():
            if subtypes.get(bgg_id) == EXPANSION:
                continue
            announce = await run(store.has_expansion_record, bgg_id)
            result.new_expansions += await run(
                store.record_expansions, bgg_id, info.expansions, stamp, announce
            )

    result.new_plays = await _sync_plays(client, store, run, now)
    await run(store.replace_wishlist, await client.fetch_wishlist())
    await run(store.set_meta, "last_sync", stamp)
    return result



async def _sync_plays(client: Client, store: Store, run: Runner, now: datetime) -> int:
    known: set[int] = await run(store.known_play_ids)
    last_full = await run(store.get_meta, "last_full_plays")
    full = not last_full or datetime.fromisoformat(last_full) < now - FULL_PLAYS_EVERY

    seen: set[int] = set()
    page = 1
    while True:
        total, plays = await client.fetch_plays(page)
        if not plays:
            break
        await run(store.upsert_plays, plays)
        ids = {p.play_id for p in plays}
        seen |= ids
        if not full and ids <= known:
            break  # nur bekannte Partien auf dieser Seite -> der Rest ist auch bekannt
        if len(seen) >= total:
            break
        page += 1

    if full:
        await run(store.delete_plays_except, seen)
        await run(store.set_meta, "last_full_plays", now.isoformat(timespec="seconds"))
    return len(seen - known)
