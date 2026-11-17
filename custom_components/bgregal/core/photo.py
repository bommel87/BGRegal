"""Regal-Scanner per Foto: Auftrag an die KI, Antwort lesen, Titel mit der Sammlung abgleichen.

Reine Logik ohne Home Assistant, damit sie sich direkt testen lässt.
"""
from __future__ import annotations

import json
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

OK = "ok"  # steht schon in diesem Fach
MOVED = "moved"  # laut BGRegal woanders
UNSURE = "unsure"  # Treffer unsicher, zur Auswahl
UNKNOWN = "unknown"  # nicht in der Sammlung

MATCH_SURE = 0.88  # Namensähnlichkeit für einen sicheren Treffer
MATCH_MIN = 0.6  # darunter gilt der Titel als „nicht in der Sammlung“
CONFIDENCE_SURE = 0.6  # unsicherere Erkennungen der KI kommen immer zur Auswahl
CANDIDATES = 3


def instructions(shelf: dict[str, Any], names: list[str], photos: int) -> str:
    """Auftrag an die KI. Die Namen der Sammlung helfen beim Lesen kleiner oder schräger Schrift."""
    count = shelf["compartments"]
    first = "unterste" if shelf.get("reversed") else "oberste"
    parts = (
        f"Die {photos} Fotos zeigen zusammen dieses eine Regal, in der Reihenfolge von oben nach unten "
        "bzw. links nach rechts. Spiele, die auf zwei Fotos zu sehen sind, nur einmal nennen."
        if photos > 1 else "Das Foto zeigt ein ganzes Regal."
    )
    return (
        "Du bekommst Fotos eines Regals mit Brettspielen. Erkenne die Spiele an den Kartonrücken "
        "und ordne sie den Fächern zu.\n"
        f"{parts}\n"
        f"Das Regal „{shelf['name']}“ hat {count} Fächer, übereinander angeordnet. "
        f"Fach 1 ist das {first} Fach, die Nummern zählen von dort aus weiter. "
        "Die Fachböden erkennst du an den waagerechten Brettern.\n"
        "Nenne die Spiele je Fach von links nach rechts, so wie sie stehen oder liegen. "
        "Nutze den Namen aus der Sammlung unten, wenn das Spiel darin vorkommt, sonst den Titel "
        "auf dem Karton. Gib je Spiel an, wie sicher du dir bist (0 bis 1). "
        "Lass Kartons weg, deren Titel du nicht lesen kannst.\n"
        'Antworte nur mit JSON in dieser Form: {"compartments": [{"compartment": 1, '
        '"games": [{"title": "Catan", "confidence": 0.95}]}]}\n\n'
        "Sammlung:\n" + "\n".join(names)
    )


def parse_answer(data: Any, compartments: int) -> list[dict[str, Any]]:
    """Antwort der KI (dict oder Text mit JSON) -> Liste aus Fach, Titel, Sicherheit.

    Fächer außerhalb des Regals und leere Titel fallen weg, die Reihenfolge bleibt erhalten."""
    if isinstance(data, str):
        text = data.strip()
        fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
        if fence:
            text = fence.group(1)
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end < start:
            raise ValueError("Die KI hat kein JSON geliefert")
        try:
            data = json.loads(text[start:end + 1])
        except json.JSONDecodeError as err:
            raise ValueError(f"Die Antwort der KI ist kein gültiges JSON: {err}") from err
    if not isinstance(data, dict) or not isinstance(data.get("compartments"), list):
        raise ValueError("Die Antwort der KI enthält keine Fächer")
    found = []
    for comp in data["compartments"]:
        if not isinstance(comp, dict):
            continue
        try:
            number = int(comp.get("compartment"))
        except (TypeError, ValueError):
            continue
        if not 1 <= number <= compartments:
            continue
        for game in comp.get("games") or []:
            if isinstance(game, str):
                game = {"title": game}
            title = str((game or {}).get("title") or "").strip() if isinstance(game, dict) else ""
            if not title:
                continue
            try:
                confidence = min(max(float(game.get("confidence", 1)), 0.0), 1.0)
            except (TypeError, ValueError):
                confidence = 1.0
            found.append({"compartment": number, "title": title, "confidence": confidence})
    found.sort(key=lambda f: f["compartment"])  # stabil: links -> rechts bleibt
    return found


def normalize(name: str) -> str:
    """Kleinbuchstaben, ohne Akzente, Satzzeichen und Artikel am Anfang."""
    text = unicodedata.normalize("NFKD", name.casefold())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^\w]+", " ", text).strip()
    return re.sub(r"^(the|der|die|das) ", "", text)


def similarity(title: str, name: str) -> float:
    """Ähnlichkeit 0..1; ein fehlender oder zusätzlicher Untertitel („Catan: Das Spiel“) zählt kaum."""
    a, b = normalize(title), normalize(name)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    best = SequenceMatcher(None, a, b).ratio()
    for x, y in ((title, name), (name, title)):
        head = normalize(re.split(r"[:–—(]| - ", x, maxsplit=1)[0])
        if head and head == normalize(y):
            best = max(best, 0.95)
    return best


def _location(game: dict[str, Any]) -> str:
    if not game.get("shelf"):
        return ""
    return f"{game['shelf']}, {game['compartment']}" if game.get("compartment") else game["shelf"]


def match(
    found: list[dict[str, Any]], games: list[dict[str, Any]], shelf: str
) -> dict[str, Any]:
    """Erkannte Titel mit der Sammlung abgleichen.

    Liefert die Einträge in Regal-Reihenfolge (Fach, dann links -> rechts) mit Status und
    die Spiele, die laut BGRegal im Regal stehen, aber nicht sicher erkannt wurden."""
    # Erweiterungen in einem anderen Karton haben keinen eigenen Rücken
    pool = [g for g in games if not g.get("in_box")]
    items: list[dict[str, Any]] = []
    taken: set[int] = set()
    for f in found:
        ranked = sorted(
            ((similarity(f["title"], g["name"]), g) for g in pool), key=lambda r: -r[0]
        )
        ranked = [(score, g) for score, g in ranked if score >= MATCH_MIN and g["bgg_id"] not in taken]
        item = {**f, "status": UNKNOWN, "bgg_id": None, "name": None, "from": "", "candidates": []}
        if ranked:
            score, game = ranked[0]
            sure = score >= MATCH_SURE and f["confidence"] >= CONFIDENCE_SURE
            # Zwei fast gleich gute Treffer (z. B. Neuauflagen) -> lieber nachfragen
            if len(ranked) > 1 and ranked[1][0] >= score - 0.02 and score < 1.0:
                sure = False
            item["candidates"] = [{"bgg_id": g["bgg_id"], "name": g["name"]} for _, g in ranked[:CANDIDATES]]
            item["bgg_id"], item["name"] = game["bgg_id"], game["name"]
            if not sure:
                item["status"] = UNSURE
            else:
                taken.add(game["bgg_id"])
                here = game["shelf"].lower() == shelf.lower() and game.get("compartment") == f["compartment"]
                item["status"] = OK if here else MOVED
                item["from"] = "" if here else _location(game)
        items.append(item)
    missing = [
        {"bgg_id": g["bgg_id"], "name": g["name"], "compartment": g.get("compartment")}
        for g in pool
        if g["shelf"].lower() == shelf.lower() and g["bgg_id"] not in taken
    ]
    return {"items": items, "missing": missing}
