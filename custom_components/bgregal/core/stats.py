"""Statistik: Partien pro Monat, Pile of Shame, lange nicht gespielt, H-Index."""
from __future__ import annotations

from datetime import date
from typing import Any


def _months_back(today: date, months: int) -> date:
    """Erster Tag des Monats, der `months` Monate vor dem aktuellen liegt."""
    index = today.year * 12 + today.month - 1 - months
    return date(index // 12, index % 12 + 1, 1)


def plays_per_month(play_dates: list[dict[str, Any]], today: date, months: int = 12) -> list[dict[str, Any]]:
    """Partien je Monat für die letzten `months` Monate (ältester zuerst, mit Nullen)."""
    keys = [_months_back(today, n).strftime("%Y-%m") for n in range(months - 1, -1, -1)]
    counts = dict.fromkeys(keys, 0)
    for row in play_dates:
        key = (row.get("date") or "")[:7]
        if key in counts:
            counts[key] += row.get("quantity") or 1
    return [{"month": k, "plays": v} for k, v in counts.items()]


def h_index(play_counts: list[int]) -> int:
    """Größtes h, sodass h Spiele mindestens h-mal gespielt wurden."""
    h = 0
    for n, count in enumerate(sorted(play_counts, reverse=True), start=1):
        if count >= n:
            h = n
        else:
            break
    return h


def pile_of_shame(games: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Eigene Basisspiele ohne eine einzige Partie."""
    return [g for g in games if not g.get("expansion") and not g.get("plays")]


def long_unplayed(games: list[dict[str, Any]], today: date, months: int) -> list[dict[str, Any]]:
    """Gespielte Basisspiele, deren letzte Partie mindestens `months` Monate her ist."""
    limit = _months_back(today, months).replace(day=min(today.day, 28)).isoformat()
    result = [
        g for g in games
        if not g.get("expansion") and g.get("last_play") and g["last_play"][:10] <= limit
    ]
    return sorted(result, key=lambda g: g["last_play"])


def overview(
    games: list[dict[str, Any]], play_dates: list[dict[str, Any]], today: date, long_months: int
) -> dict[str, Any]:
    base = [g for g in games if not g.get("expansion")]
    shame = pile_of_shame(games)
    unplayed = long_unplayed(games, today, long_months)
    return {
        "games": len(base),
        "expansions": len(games) - len(base),
        "plays_total": sum(r.get("quantity") or 1 for r in play_dates),
        "plays_this_month": sum(
            r.get("quantity") or 1 for r in play_dates if (r.get("date") or "")[:7] == today.strftime("%Y-%m")
        ),
        "h_index": h_index([g.get("plays") or 0 for g in base]),
        "per_month": plays_per_month(play_dates, today),
        "pile_of_shame": [g["bgg_id"] for g in shame],
        "long_unplayed": [g["bgg_id"] for g in unplayed],
        "top": [g["bgg_id"] for g in sorted(base, key=lambda g: -(g.get("plays") or 0))[:10]
                if g.get("plays")],
    }
