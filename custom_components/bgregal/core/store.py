"""SQLite-Datenbank von BGRegal.

BGG-Tabellen (games, plays, play_players, wishlist, expansions_known) werden beim Sync
überschrieben. Lokale Tabellen (game_meta, loans, players, session, evenings …) nie.
Alle Methoden sind synchron und laufen in Home Assistant im Executor.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable
from typing import Any

from .parser import EXPANSION, CollectionItem, Play, ThingInfo

SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    bgg_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    subtype TEXT NOT NULL,
    year INTEGER,
    image TEXT,
    thumbnail TEXT,
    user_rating REAL,
    version_name TEXT,
    languages TEXT NOT NULL DEFAULT '[]',
    min_players INTEGER,
    max_players INTEGER,
    min_playtime INTEGER,
    max_playtime INTEGER,
    playing_time INTEGER,
    weight REAL,
    game_types TEXT NOT NULL DEFAULT '[]',
    mode TEXT,
    base_ids TEXT NOT NULL DEFAULT '[]',
    info_updated TEXT
);
CREATE TABLE IF NOT EXISTS plays (
    play_id INTEGER PRIMARY KEY,
    bgg_id INTEGER,
    date TEXT,
    quantity INTEGER NOT NULL DEFAULT 1,
    length INTEGER,
    comments TEXT
);
CREATE INDEX IF NOT EXISTS plays_game ON plays (bgg_id, date);
CREATE TABLE IF NOT EXISTS play_players (
    play_id INTEGER NOT NULL,
    idx INTEGER NOT NULL,
    name TEXT NOT NULL,
    username TEXT,
    score TEXT,
    win INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (play_id, idx)
);
CREATE TABLE IF NOT EXISTS wishlist (
    bgg_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    year INTEGER,
    thumbnail TEXT,
    priority INTEGER
);
CREATE TABLE IF NOT EXISTS expansions_known (
    base_id INTEGER NOT NULL,
    expansion_id INTEGER NOT NULL,
    name TEXT,
    first_seen TEXT NOT NULL,
    is_new INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (base_id, expansion_id)
);
CREATE TABLE IF NOT EXISTS game_meta (
    bgg_id INTEGER PRIMARY KEY,
    shelf TEXT NOT NULL DEFAULT '',
    compartment INTEGER,
    in_base INTEGER NOT NULL DEFAULT 0,
    nfc_tag TEXT NOT NULL DEFAULT '',
    light_profile TEXT NOT NULL DEFAULT '',
    playlist TEXT NOT NULL DEFAULT '',
    manual_url TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS loans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bgg_id INTEGER NOT NULL,
    borrower TEXT NOT NULL,
    since TEXT NOT NULL,
    returned TEXT,
    reminded TEXT
);
CREATE TABLE IF NOT EXISTS players (
    name TEXT PRIMARY KEY COLLATE NOCASE,
    bgg_username TEXT NOT NULL DEFAULT '',
    dislikes TEXT NOT NULL DEFAULT '[]',
    hidden INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS session (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evenings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    start TEXT NOT NULL,
    max_playtime INTEGER,
    token TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS evening_guests (
    evening_id INTEGER NOT NULL,
    name TEXT NOT NULL COLLATE NOCASE,
    PRIMARY KEY (evening_id, name)
);
CREATE TABLE IF NOT EXISTS evening_candidates (
    evening_id INTEGER NOT NULL,
    bgg_id INTEGER NOT NULL,
    PRIMARY KEY (evening_id, bgg_id)
);
CREATE TABLE IF NOT EXISTS evening_votes (
    evening_id INTEGER NOT NULL,
    voter TEXT NOT NULL COLLATE NOCASE,
    bgg_id INTEGER NOT NULL,
    PRIMARY KEY (evening_id, voter, bgg_id)
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

# Änderungen an bestehenden Datenbanken; neue Datenbanken entstehen direkt aus SCHEMA
MIGRATIONS: dict[int, tuple[str, ...]] = {
    2: ("ALTER TABLE players ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0",),
}

META_FIELDS = ("shelf", "compartment", "in_base", "nfc_tag", "light_profile", "playlist", "manual_url")


class Store:
    """Zugriff auf die SQLite-Datei; threadsicher über eine Sperre."""

    def __init__(self, path: str) -> None:
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock, self._db:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.executescript(SCHEMA)
            self._db.execute(
                "INSERT OR IGNORE INTO meta (key, value) VALUES ('schema', ?)", (str(SCHEMA_VERSION),)
            )
            current = int(self._db.execute("SELECT value FROM meta WHERE key = 'schema'").fetchone()[0])
            for version in range(current + 1, SCHEMA_VERSION + 1):
                for sql in MIGRATIONS.get(version, ()):
                    self._db.execute(sql)
            self._db.execute("UPDATE meta SET value = ? WHERE key = 'schema'", (str(SCHEMA_VERSION),))

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def _rows(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._db.execute(sql, tuple(params)).fetchall()]

    def _write(self, sql: str, params: Iterable[Any] = ()) -> int:
        with self._lock, self._db:
            return self._db.execute(sql, tuple(params)).lastrowid or 0

    # ---- meta --------------------------------------------------------------
    def get_meta(self, key: str) -> str | None:
        rows = self._rows("SELECT value FROM meta WHERE key = ?", (key,))
        return rows[0]["value"] if rows else None

    def set_meta(self, key: str, value: str | None) -> None:
        self._write("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))

    # ---- Sammlung ----------------------------------------------------------
    def replace_collection(self, items: list[CollectionItem]) -> None:
        """Übernimmt die eigenen Spiele; nicht mehr vorhandene fallen weg (Zuordnungen bleiben)."""
        ids = [i.bgg_id for i in items]
        with self._lock, self._db:
            for i in items:
                self._db.execute(
                    """INSERT INTO games (bgg_id, name, subtype, year, image, thumbnail, user_rating,
                           version_name, languages)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT (bgg_id) DO UPDATE SET name = excluded.name,
                           subtype = excluded.subtype, year = excluded.year, image = excluded.image,
                           thumbnail = excluded.thumbnail, user_rating = excluded.user_rating,
                           version_name = excluded.version_name, languages = excluded.languages""",
                    (i.bgg_id, i.name, i.subtype, i.year, i.image, i.thumbnail, i.user_rating,
                     i.version_name, json.dumps(i.languages)),
                )
            if ids:
                marks = ",".join("?" * len(ids))
                self._db.execute(f"DELETE FROM games WHERE bgg_id NOT IN ({marks})", ids)
            else:
                self._db.execute("DELETE FROM games")

    def game_count(self) -> int:
        return self._rows("SELECT COUNT(*) AS n FROM games")[0]["n"]

    def ids_needing_info(self, older_than: str) -> list[int]:
        rows = self._rows(
            "SELECT bgg_id FROM games WHERE info_updated IS NULL OR info_updated < ? ORDER BY bgg_id",
            (older_than,),
        )
        return [r["bgg_id"] for r in rows]

    def update_info(self, infos: dict[int, ThingInfo], now: str) -> None:
        with self._lock, self._db:
            for info in infos.values():
                self._db.execute(
                    """UPDATE games SET min_players = ?, max_players = ?, min_playtime = ?,
                           max_playtime = ?, playing_time = ?, weight = ?, game_types = ?, mode = ?,
                           base_ids = ?, info_updated = ? WHERE bgg_id = ?""",
                    (info.min_players, info.max_players, info.min_playtime, info.max_playtime,
                     info.playing_time, info.weight, json.dumps(info.game_types), info.mode,
                     json.dumps(info.base_ids), now, info.bgg_id),
                )

    def record_expansions(
        self, base_id: int, expansions: list[tuple[int, str]], now: str, announce: bool
    ) -> list[dict[str, Any]]:
        """Merkt sich die Erweiterungen eines Basisspiels; liefert die bisher unbekannten.

        Beim ersten Abgleich eines Spiels (announce=False) wird nichts als neu markiert.
        """
        known = {
            r["expansion_id"]
            for r in self._rows("SELECT expansion_id FROM expansions_known WHERE base_id = ?", (base_id,))
        }
        fresh = [(eid, name) for eid, name in expansions if eid not in known]
        with self._lock, self._db:
            for eid, name in fresh:
                self._db.execute(
                    "INSERT INTO expansions_known VALUES (?, ?, ?, ?, ?)",
                    (base_id, eid, name, now, int(announce)),
                )
        return [{"base_id": base_id, "bgg_id": eid, "name": name} for eid, name in fresh] if announce else []

    def has_expansion_record(self, base_id: int) -> bool:
        return bool(self._rows("SELECT 1 FROM expansions_known WHERE base_id = ? LIMIT 1", (base_id,)))

    def new_expansions(self) -> list[dict[str, Any]]:
        """Neue Erweiterungen zu eigenen Spielen, die man noch nicht besitzt."""
        return self._rows(
            """SELECT k.base_id, g.name AS base_name, k.expansion_id AS bgg_id, k.name, k.first_seen
               FROM expansions_known k JOIN games g ON g.bgg_id = k.base_id
               WHERE k.is_new = 1 AND k.expansion_id NOT IN (SELECT bgg_id FROM games)
               ORDER BY k.first_seen DESC, k.name"""
        )

    def dismiss_new_expansions(self) -> None:
        self._write("UPDATE expansions_known SET is_new = 0 WHERE is_new = 1")

    # ---- Wunschliste ---------------------------------------------------------
    def replace_wishlist(self, items: list[CollectionItem]) -> None:
        with self._lock, self._db:
            self._db.execute("DELETE FROM wishlist")
            self._db.executemany(
                "INSERT OR REPLACE INTO wishlist VALUES (?, ?, ?, ?, ?)",
                [(i.bgg_id, i.name, i.year, i.thumbnail, i.wishlist_priority) for i in items],
            )

    def wishlist(self) -> list[dict[str, Any]]:
        return self._rows("SELECT * FROM wishlist ORDER BY COALESCE(priority, 9), name")

    # ---- Partien -----------------------------------------------------------
    def known_play_ids(self) -> set[int]:
        return {r["play_id"] for r in self._rows("SELECT play_id FROM plays")}

    def upsert_plays(self, plays: list[Play]) -> None:
        with self._lock, self._db:
            for p in plays:
                self._db.execute(
                    "INSERT OR REPLACE INTO plays VALUES (?, ?, ?, ?, ?, ?)",
                    (p.play_id, p.bgg_id, p.date, p.quantity, p.length, p.comments),
                )
                self._db.execute("DELETE FROM play_players WHERE play_id = ?", (p.play_id,))
                self._db.executemany(
                    "INSERT INTO play_players VALUES (?, ?, ?, ?, ?, ?)",
                    [(p.play_id, n, pl.name, pl.username, pl.score, int(pl.win))
                     for n, pl in enumerate(p.players)],
                )

    def delete_plays_except(self, keep: set[int]) -> None:
        gone = self.known_play_ids() - keep
        with self._lock, self._db:
            for play_id in gone:
                self._db.execute("DELETE FROM plays WHERE play_id = ?", (play_id,))
                self._db.execute("DELETE FROM play_players WHERE play_id = ?", (play_id,))

    def play_dates(self) -> list[dict[str, Any]]:
        return self._rows("SELECT date, quantity FROM plays WHERE date IS NOT NULL")

    def plays_for(self, bgg_id: int, limit: int = 10) -> list[dict[str, Any]]:
        plays = self._rows(
            """SELECT play_id, date, quantity, length, comments FROM plays WHERE bgg_id = ?
               ORDER BY date DESC, play_id DESC LIMIT ?""",
            (bgg_id, limit),
        )
        self._attach_players(plays)
        return plays

    def _attach_players(self, plays: list[dict[str, Any]]) -> None:
        if not plays:
            return
        ids = [p["play_id"] for p in plays]
        rows = self._rows(
            f"SELECT * FROM play_players WHERE play_id IN ({','.join('?' * len(ids))}) ORDER BY idx",
            ids,
        )
        by_play: dict[int, list[dict[str, Any]]] = {}
        for r in rows:
            by_play.setdefault(r["play_id"], []).append(
                {"name": r["name"], "username": r["username"], "score": r["score"], "win": bool(r["win"])}
            )
        for p in plays:
            p["players"] = by_play.get(p["play_id"], [])

    # ---- Spiele mit allem, was das Panel braucht ----------------------------
    def games(self) -> list[dict[str, Any]]:
        rows = self._rows(
            """SELECT g.*, m.shelf, m.compartment, m.in_base, m.nfc_tag, m.light_profile,
                      m.playlist, m.manual_url,
                      COALESCE(s.plays, 0) AS plays, s.last_play
               FROM games g
               LEFT JOIN game_meta m ON m.bgg_id = g.bgg_id
               LEFT JOIN (SELECT bgg_id, SUM(quantity) AS plays, MAX(date) AS last_play
                          FROM plays GROUP BY bgg_id) s ON s.bgg_id = g.bgg_id
               ORDER BY g.name COLLATE NOCASE"""
        )
        last_ids = {
            r["bgg_id"]: r["play_id"]
            for r in self._rows(
                """SELECT bgg_id, MAX(play_id) AS play_id FROM plays p
                   WHERE date = (SELECT MAX(date) FROM plays q WHERE q.bgg_id = p.bgg_id)
                   GROUP BY bgg_id"""
            )
        }
        last_plays = [{"play_id": pid} for pid in last_ids.values()]
        self._attach_players(last_plays)
        players_by_play = {p["play_id"]: p["players"] for p in last_plays}
        loans = {l["bgg_id"]: l for l in self.active_loans()}
        for g in rows:
            for key in ("languages", "game_types", "base_ids"):
                g[key] = json.loads(g[key] or "[]")
            for key in ("shelf", "nfc_tag", "light_profile", "playlist", "manual_url"):
                g[key] = g[key] or ""
            g["in_base"] = bool(g["in_base"])
            g["expansion"] = g["subtype"] == EXPANSION
            g["last_players"] = players_by_play.get(last_ids.get(g["bgg_id"]), [])
            loan = loans.get(g["bgg_id"])
            g["loan"] = {"borrower": loan["borrower"], "since": loan["since"]} if loan else None
        return rows

    def game(self, bgg_id: int) -> dict[str, Any] | None:
        return next((g for g in self.games() if g["bgg_id"] == bgg_id), None)

    def set_game_meta(self, bgg_id: int, fields: dict[str, Any]) -> None:
        fields = {k: v for k, v in fields.items() if k in META_FIELDS}
        if not fields:
            return
        with self._lock, self._db:
            self._db.execute("INSERT OR IGNORE INTO game_meta (bgg_id) VALUES (?)", (bgg_id,))
            for key, value in fields.items():
                self._db.execute(f"UPDATE game_meta SET {key} = ? WHERE bgg_id = ?", (value, bgg_id))

    def game_by_tag(self, tag: str) -> int | None:
        rows = self._rows(
            "SELECT bgg_id FROM game_meta WHERE nfc_tag != '' AND lower(nfc_tag) = lower(?)", (tag,)
        )
        return rows[0]["bgg_id"] if rows else None

    # ---- Verleih -----------------------------------------------------------
    def active_loans(self) -> list[dict[str, Any]]:
        return self._rows(
            """SELECT l.*, g.name FROM loans l LEFT JOIN games g ON g.bgg_id = l.bgg_id
               WHERE l.returned IS NULL ORDER BY l.since"""
        )

    def lend(self, bgg_id: int, borrower: str, since: str) -> None:
        with self._lock, self._db:
            self._db.execute(
                "UPDATE loans SET returned = ? WHERE bgg_id = ? AND returned IS NULL", (since, bgg_id)
            )
            self._db.execute(
                "INSERT INTO loans (bgg_id, borrower, since) VALUES (?, ?, ?)", (bgg_id, borrower, since)
            )

    def return_game(self, bgg_id: int, when: str) -> bool:
        with self._lock, self._db:
            cur = self._db.execute(
                "UPDATE loans SET returned = ? WHERE bgg_id = ? AND returned IS NULL", (when, bgg_id)
            )
            return cur.rowcount > 0

    def mark_reminded(self, loan_id: int, when: str) -> None:
        self._write("UPDATE loans SET reminded = ? WHERE id = ?", (when, loan_id))

    # ---- Mitspieler ----------------------------------------------------------
    def players(self, me: str) -> list[dict[str, Any]]:
        """Mitspieler aus den BGG-Partien plus selbst angelegte; ohne einen selbst."""
        me = me.lower()
        result: dict[str, dict[str, Any]] = {}
        for r in self._rows(
            """SELECT name, MAX(username) AS username, COUNT(DISTINCT play_id) AS plays
               FROM play_players GROUP BY lower(name)"""
        ):
            if (r["username"] or "").lower() == me or r["name"].lower() == me:
                continue
            result[r["name"].lower()] = {
                "name": r["name"], "bgg_username": r["username"] or "", "dislikes": [],
                "plays": r["plays"], "from_bgg": True, "hidden": False,
            }
        for r in self._rows("SELECT * FROM players"):
            entry = result.setdefault(
                r["name"].lower(), {"name": r["name"], "plays": 0, "from_bgg": False}
            )
            entry["bgg_username"] = r["bgg_username"] or entry.get("bgg_username", "")
            entry["dislikes"] = json.loads(r["dislikes"] or "[]")
            entry["hidden"] = bool(r["hidden"])
        return sorted(result.values(), key=lambda p: (-p["plays"], p["name"].lower()))

    def set_player(
        self, name: str, bgg_username: str | None, dislikes: list[str] | None, hidden: bool | None = None
    ) -> None:
        with self._lock, self._db:
            self._db.execute("INSERT OR IGNORE INTO players (name) VALUES (?)", (name,))
            if hidden is not None:
                self._db.execute("UPDATE players SET hidden = ? WHERE name = ?", (int(hidden), name))
            if bgg_username is not None:
                self._db.execute(
                    "UPDATE players SET bgg_username = ? WHERE name = ?", (bgg_username, name)
                )
            if dislikes is not None:
                self._db.execute(
                    "UPDATE players SET dislikes = ? WHERE name = ?", (json.dumps(dislikes), name)
                )

    def remove_player(self, name: str) -> bool:
        with self._lock, self._db:
            return self._db.execute("DELETE FROM players WHERE name = ?", (name,)).rowcount > 0

    # ---- Sitzung -----------------------------------------------------------
    def get_session(self) -> dict[str, Any] | None:
        rows = self._rows("SELECT data FROM session WHERE id = 1")
        return json.loads(rows[0]["data"]) if rows else None

    def set_session(self, data: dict[str, Any] | None) -> None:
        if data is None:
            self._write("DELETE FROM session")
        else:
            self._write(
                "INSERT OR REPLACE INTO session (id, data) VALUES (1, ?)",
                (json.dumps(data, ensure_ascii=False),),
            )

    # ---- Spieleabende ------------------------------------------------------
    def add_evening(
        self, title: str, start: str, max_playtime: int | None, token: str,
        guests: list[str], candidates: list[int],
    ) -> int:
        with self._lock, self._db:
            evening_id = self._db.execute(
                "INSERT INTO evenings (title, start, max_playtime, token) VALUES (?, ?, ?, ?)",
                (title, start, max_playtime, token),
            ).lastrowid
            self._db.executemany(
                "INSERT OR IGNORE INTO evening_guests VALUES (?, ?)", [(evening_id, g) for g in guests]
            )
            self._db.executemany(
                "INSERT OR IGNORE INTO evening_candidates VALUES (?, ?)",
                [(evening_id, c) for c in candidates],
            )
            return evening_id

    def set_candidates(self, evening_id: int, candidates: list[int]) -> None:
        with self._lock, self._db:
            self._db.execute("DELETE FROM evening_candidates WHERE evening_id = ?", (evening_id,))
            self._db.executemany(
                "INSERT OR IGNORE INTO evening_candidates VALUES (?, ?)",
                [(evening_id, c) for c in candidates],
            )
            marks = ",".join("?" * len(candidates))
            self._db.execute(
                f"DELETE FROM evening_votes WHERE evening_id = ? AND bgg_id NOT IN ({marks})"
                if candidates else "DELETE FROM evening_votes WHERE evening_id = ?",
                (evening_id, *candidates),
            )

    def remove_evening(self, evening_id: int) -> bool:
        with self._lock, self._db:
            n = self._db.execute("DELETE FROM evenings WHERE id = ?", (evening_id,)).rowcount
            for table in ("evening_guests", "evening_candidates", "evening_votes"):
                self._db.execute(f"DELETE FROM {table} WHERE evening_id = ?", (evening_id,))
            return n > 0

    def evenings(self) -> list[dict[str, Any]]:
        evenings = self._rows("SELECT * FROM evenings ORDER BY start")
        for e in evenings:
            self._fill_evening(e)
        return evenings

    def evening_by_token(self, token: str) -> dict[str, Any] | None:
        rows = self._rows("SELECT * FROM evenings WHERE token = ?", (token,))
        if not rows:
            return None
        self._fill_evening(rows[0])
        return rows[0]

    def evening(self, evening_id: int) -> dict[str, Any] | None:
        rows = self._rows("SELECT * FROM evenings WHERE id = ?", (evening_id,))
        if not rows:
            return None
        self._fill_evening(rows[0])
        return rows[0]

    def _fill_evening(self, e: dict[str, Any]) -> None:
        eid = e["id"]
        e["guests"] = [r["name"] for r in self._rows(
            "SELECT name FROM evening_guests WHERE evening_id = ? ORDER BY name", (eid,))]
        e["candidates"] = [r["bgg_id"] for r in self._rows(
            "SELECT bgg_id FROM evening_candidates WHERE evening_id = ?", (eid,))]
        votes: dict[str, list[int]] = {}
        for r in self._rows(
            "SELECT voter, bgg_id FROM evening_votes WHERE evening_id = ? ORDER BY voter", (eid,)
        ):
            votes.setdefault(r["voter"], []).append(r["bgg_id"])
        e["votes"] = votes

    def set_votes(self, evening_id: int, voter: str, bgg_ids: list[int]) -> None:
        with self._lock, self._db:
            self._db.execute(
                "DELETE FROM evening_votes WHERE evening_id = ? AND voter = ?", (evening_id, voter)
            )
            self._db.executemany(
                "INSERT OR IGNORE INTO evening_votes VALUES (?, ?, ?)",
                [(evening_id, voter, b) for b in bgg_ids],
            )
