"""Übergabe einer Partie an BG Stats (offizielles createPlay-Link-Format) und QR-Code."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

BGSTATS_URL = "https://app.bgstatsapp.com/createPlay.html"


def parse_score(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return None


def auto_winners(players: list[dict[str, Any]]) -> set[str]:
    """Höchste Punktzahl gewinnt, bei Gleichstand alle mit dieser Punktzahl."""
    scores = [(p["name"], parse_score(p.get("score"))) for p in players]
    valid = [s for _, s in scores if s is not None]
    if not valid:
        return set()
    best = max(valid)
    return {name.lower() for name, s in scores if s == best}


def play_url(
    me: str,
    game_name: str,
    bgg_id: int,
    ended: datetime,
    duration_min: int,
    players: list[dict[str, Any]],
    note: str = "",
    source_id: str = "",
) -> str:
    """Link, der in BG Stats den Import-Dialog mit allen Angaben öffnet.

    `players`: [{"name", "username"?, "score"?, "winner"?}]; der Eintrag für einen selbst
    hat `username` = eigener BGG-Name.
    """
    entries = []
    for p in players:
        username = (p.get("username") or "").strip()
        ident = f"bgg:{username.lower()}" if username else f"name:{p['name'].lower()}"
        entry: dict[str, Any] = {"name": p["name"], "sourcePlayerId": ident, "winner": bool(p.get("winner"))}
        score = parse_score(p.get("score"))
        if score is not None:
            entry["score"] = score
        entries.append(entry)
    data: dict[str, Any] = {
        "sourceName": "Home Assistant",
        "sourcePlayId": source_id or f"bgregal-{me.lower()}-{int(ended.timestamp())}",
        "playDate": ended.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "durationMin": max(duration_min, 0),
        "game": {
            "name": game_name,
            "sourceGameId": str(bgg_id),
            "bggId": bgg_id,
            "highestWins": True,
            "noPoints": not any("score" in e for e in entries),
        },
        "players": entries,
    }
    if note:
        data["comments"] = note
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"{BGSTATS_URL}?data={quote(payload, safe='')}"


def qr_svg(text: str) -> str:
    """QR-Code als eingebettetes SVG; skaliert mit (viewBox statt fester Größe)."""
    import segno  # noqa: PLC0415 - erst bei Bedarf laden

    return segno.make(text, error="m").svg_inline(
        scale=4, border=2, dark="#000", light="#fff", omitsize=True
    )
