"""Spielvorschlag: Filter und Gewichtung (lange nicht gespielt, Bewertung, Vorlieben)."""
from __future__ import annotations

import random
from datetime import date
from typing import Any

GAME_TYPES = ("family", "strategy", "party", "abstract", "thematic", "wargame", "children")
MODES = ("cooperative", "competitive")
DISLIKE_OPTIONS = MODES + GAME_TYPES


def matches(
    game: dict[str, Any],
    players: int | None = None,
    mode: str = "any",
    game_type: str = "any",
    max_playtime: int | None = None,
) -> bool:
    """Passt ein Spiel zu den Filtern? Unbekannte Werte passen nur zu „egal“."""
    if game.get("expansion") or game.get("loan"):
        return False
    if players is not None:
        lo, hi = game.get("min_players"), game.get("max_players")
        if lo is None or hi is None or not lo <= players <= hi:
            return False
    game_mode = game.get("mode")
    if mode == "cooperative" and game_mode != "cooperative":
        return False
    if mode == "competitive" and game_mode not in ("competitive", "semi"):
        return False
    if game_type != "any" and game_type not in (game.get("game_types") or []):
        return False
    if max_playtime and (game.get("playing_time") or 0) > max_playtime:
        return False
    return True


def disliked(game: dict[str, Any], dislikes: set[str]) -> bool:
    """Mag jemand der Anwesenden diese Art von Spiel nicht?"""
    mode = game.get("mode")
    if mode == "cooperative" and "cooperative" in dislikes:
        return True
    if mode in ("competitive", "semi") and "competitive" in dislikes:
        return True
    return any(t in dislikes for t in game.get("game_types") or [])


def weight(game: dict[str, Any], today: date) -> float:
    """Je länger nicht gespielt und je besser bewertet, desto wahrscheinlicher."""
    last = game.get("last_play")
    if last:
        try:
            days = (today - date.fromisoformat(last[:10])).days
        except ValueError:
            days = 365
        w = 1.0 + min(max(days, 0), 3 * 365) / 182.5  # bis zu 7x nach drei Jahren
    else:
        w = 5.0  # nie gespielt: deutlich bevorzugen
    rating = game.get("user_rating")
    if rating:
        w *= 0.5 + rating / 10  # Bewertung 10 -> x1,5, Bewertung 5 -> x1,0
    return w


def rank(
    games: list[dict[str, Any]],
    today: date,
    rng: random.Random,
    players: int | None = None,
    mode: str = "any",
    game_type: str = "any",
    max_playtime: int | None = None,
    dislikes: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Passende Spiele in gewichtet zufälliger Reihenfolge."""
    dislikes = dislikes or set()
    pool = [
        g for g in games
        if matches(g, players, mode, game_type, max_playtime) and not disliked(g, dislikes)
    ]
    # Gewichtetes Ziehen ohne Zurücklegen (Efraimidis-Spirakis)
    keyed = [(rng.random() ** (1.0 / weight(g, today)), g) for g in pool]
    keyed.sort(key=lambda kv: kv[0], reverse=True)
    return [g for _, g in keyed]


def summary_line(game: dict[str, Any], labels: dict[str, str]) -> str:
    """Kurzbeschreibung, z. B. „2–4 Spieler | 45 Min | Kooperativ“."""
    parts = []
    lo, hi = game.get("min_players"), game.get("max_players")
    if lo and hi:
        parts.append(f"{lo} {labels['players']}" if lo == hi else f"{lo}–{hi} {labels['players']}")
    if game.get("playing_time"):
        parts.append(f"{game['playing_time']} {labels['minutes']}")
    if game.get("mode") in labels:
        parts.append(labels[game["mode"]])
    return " | ".join(parts)
