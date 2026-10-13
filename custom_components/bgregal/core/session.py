"""Spielsitzung: Zustände und Spielhilfe (Runde, wer ist dran) als reine Funktionen.

Eine Sitzung ist ein dict, das unverändert in der Datenbank landet:
  state: "running" | "finished"
  bgg_id, name, started (ISO), ended (ISO|None), round, order (Namen), turn (Index)
  result: {url, players, note} nach dem Abschluss
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

RUNNING = "running"
FINISHED = "finished"


def start(bgg_id: int, name: str, now: datetime, order: list[str] | None = None) -> dict[str, Any]:
    return {
        "state": RUNNING,
        "bgg_id": bgg_id,
        "name": name,
        "started": now.isoformat(timespec="seconds"),
        "ended": None,
        "round": 1,
        "order": list(order or []),
        "turn": 0,
        "result": None,
    }


def current_player(session: dict[str, Any]) -> str | None:
    order = session.get("order") or []
    return order[session.get("turn", 0) % len(order)] if order else None


def next_player(session: dict[str, Any]) -> dict[str, Any]:
    """Nächster Spieler; nach dem letzten beginnt eine neue Runde."""
    order = session.get("order") or []
    s = dict(session)
    if not order:
        s["round"] = s.get("round", 1) + 1
        return s
    s["turn"] = (s.get("turn", 0) + 1) % len(order)
    if s["turn"] == 0:
        s["round"] = s.get("round", 1) + 1
    return s


def next_round(session: dict[str, Any]) -> dict[str, Any]:
    s = dict(session)
    s["round"] = s.get("round", 1) + 1
    s["turn"] = 0
    return s


def set_order(session: dict[str, Any], order: list[str]) -> dict[str, Any]:
    s = dict(session)
    s["order"] = list(order)
    s["turn"] = 0
    return s


def end(session: dict[str, Any], now: datetime) -> dict[str, Any]:
    s = dict(session)
    s["state"] = FINISHED
    s["ended"] = now.isoformat(timespec="seconds")
    return s


def duration_min(session: dict[str, Any], now: datetime | None = None) -> int:
    started = datetime.fromisoformat(session["started"])
    ended = datetime.fromisoformat(session["ended"]) if session.get("ended") else now
    if ended is None:
        return 0
    return max(0, round((ended - started).total_seconds() / 60))
