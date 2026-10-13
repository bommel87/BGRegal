"""XML der BGG-API2 in einfache Datenobjekte übersetzen."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from .errors import BggError

BASEGAME = "boardgame"
EXPANSION = "boardgameexpansion"

# BGG-Subdomains (Rank-Namen) -> Spieltyp
SUBDOMAIN_TYPES = {
    "strategygames": "strategy",
    "familygames": "family",
    "partygames": "party",
    "abstracts": "abstract",
    "thematic": "thematic",
    "wargames": "wargame",
    "childrensgames": "children",
}
# Fallback für Spiele ohne Rang
CATEGORY_TYPES = {
    "Party Game": "party",
    "Children's Game": "children",
    "Abstract Strategy": "abstract",
    "Wargame": "wargame",
}
MECHANIC_COOP = "Cooperative Game"
MECHANIC_SEMI = "Semi-Cooperative Game"


@dataclass
class CollectionItem:
    """Ein Eintrag der BGG-Sammlung (eigene Spiele oder Wunschliste)."""

    bgg_id: int
    name: str
    subtype: str
    year: int | None = None
    image: str | None = None
    thumbnail: str | None = None
    owned: bool = False
    wishlist: bool = False
    wishlist_priority: int | None = None
    user_rating: float | None = None
    version_name: str | None = None
    languages: list[str] = field(default_factory=list)


@dataclass
class ThingInfo:
    """Spielinfos aus /thing."""

    bgg_id: int
    min_players: int | None = None
    max_players: int | None = None
    min_playtime: int | None = None
    max_playtime: int | None = None
    playing_time: int | None = None
    weight: float | None = None
    categories: list[str] = field(default_factory=list)
    mechanics: list[str] = field(default_factory=list)
    game_types: list[str] = field(default_factory=list)
    mode: str = "competitive"
    # Bei Erweiterungen: die Basisspiele, die sie erweitert
    base_ids: list[int] = field(default_factory=list)
    # Bei Basisspielen: alle auf BGG bekannten Erweiterungen (id, name)
    expansions: list[tuple[int, str]] = field(default_factory=list)


@dataclass
class PlayPlayer:
    """Ein Spieler einer BGG-Partie."""

    name: str
    username: str | None = None
    score: str | None = None
    win: bool = False


@dataclass
class Play:
    """Eine auf BGG geloggte Partie."""

    play_id: int
    bgg_id: int | None
    date: str | None
    quantity: int = 1
    length: int | None = None
    comments: str | None = None
    players: list[PlayPlayer] = field(default_factory=list)


def _root(text: str) -> ET.Element:
    try:
        return ET.fromstring(text)
    except ET.ParseError as err:
        raise BggError("Ungültige XML-Antwort von BGG") from err


def _int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _value_int(el: ET.Element, tag: str) -> int | None:
    child = el.find(tag)
    return _int(child.get("value")) if child is not None else None


def _check_errors(root: ET.Element) -> None:
    """BGG meldet manche Fehler als <errors><error><message>…"""
    message = root.findtext("error/message")
    if root.tag == "errors" and message:
        raise BggError(message)


def parse_user_id(text: str) -> int | None:
    """ID aus /user; leer, wenn es den Benutzer nicht gibt."""
    root = _root(text)
    return _int(root.get("id")) or None


def parse_collection(text: str) -> list[CollectionItem]:
    root = _root(text)
    _check_errors(root)
    items = []
    for el in root.findall("item"):
        bgg_id = _int(el.get("objectid"))
        if bgg_id is None:
            continue
        status = el.find("status")

        def flag(name: str, status=status) -> bool:
            return status is not None and status.get(name) == "1"

        rating = el.find("stats/rating")
        version = el.find("version/item")
        version_name = None
        languages: list[str] = []
        if version is not None:
            name_el = version.find("name")
            version_name = name_el.get("value") if name_el is not None else None
            languages = [
                link.get("value")
                for link in version.findall("link[@type='language']")
                if link.get("value")
            ]
        items.append(
            CollectionItem(
                bgg_id=bgg_id,
                name=(el.findtext("name") or "").strip(),
                subtype=el.get("subtype") or BASEGAME,
                year=_int(el.findtext("yearpublished")),
                image=(el.findtext("image") or "").strip() or None,
                thumbnail=(el.findtext("thumbnail") or "").strip() or None,
                owned=flag("own"),
                wishlist=flag("wishlist"),
                wishlist_priority=_int(status.get("wishlistpriority")) if status is not None else None,
                user_rating=_float(rating.get("value")) if rating is not None else None,
                version_name=version_name,
                languages=languages,
            )
        )
    return items


def parse_things(text: str) -> dict[int, ThingInfo]:
    root = _root(text)
    _check_errors(root)
    result: dict[int, ThingInfo] = {}
    for game in root.findall("item"):
        bgg_id = _int(game.get("id"))
        if bgg_id is None:
            continue
        info = ThingInfo(bgg_id=bgg_id)
        for link in game.findall(f"link[@type='{EXPANSION}']"):
            link_id = _int(link.get("id"))
            if link_id is None:
                continue
            if link.get("inbound") == "true":
                info.base_ids.append(link_id)
            else:
                info.expansions.append((link_id, link.get("value") or ""))
        info.categories = [l.get("value") for l in game.findall("link[@type='boardgamecategory']")]
        info.mechanics = [l.get("value") for l in game.findall("link[@type='boardgamemechanic']")]
        types = {CATEGORY_TYPES[c] for c in info.categories if c in CATEGORY_TYPES}
        for rank in game.findall("statistics/ratings/ranks/rank[@type='family']"):
            kind = SUBDOMAIN_TYPES.get(rank.get("name"))
            if kind and rank.get("value") not in (None, "Not Ranked"):
                types.add(kind)
        info.game_types = sorted(types)
        if MECHANIC_COOP in info.mechanics:
            info.mode = "cooperative"
        elif MECHANIC_SEMI in info.mechanics:
            info.mode = "semi"
        info.min_players = _value_int(game, "minplayers")
        info.max_players = _value_int(game, "maxplayers")
        info.min_playtime = _value_int(game, "minplaytime")
        info.max_playtime = _value_int(game, "maxplaytime")
        info.playing_time = _value_int(game, "playingtime")
        weight = game.find("statistics/ratings/averageweight")
        info.weight = _float(weight.get("value")) if weight is not None else None
        if not info.weight:
            info.weight = None
        result[bgg_id] = info
    return result


def parse_plays(text: str) -> tuple[int, list[Play]]:
    """Eine Seite Partien; liefert (Gesamtzahl, Partien)."""
    root = _root(text)
    _check_errors(root)
    plays = []
    for el in root.findall("play"):
        play_id = _int(el.get("id"))
        if play_id is None:
            continue
        item = el.find("item")
        players = []
        for p in el.findall("players/player"):
            name = (p.get("name") or "").strip()
            username = (p.get("username") or "").strip() or None
            if not name and not username:
                continue
            players.append(
                PlayPlayer(
                    name=name or username or "",
                    username=username,
                    score=(p.get("score") or "").strip() or None,
                    win=p.get("win") == "1",
                )
            )
        plays.append(
            Play(
                play_id=play_id,
                bgg_id=_int(item.get("objectid")) if item is not None else None,
                date=el.get("date") or None,
                quantity=_int(el.get("quantity")) or 1,
                length=_int(el.get("length")) or None,
                comments=(el.findtext("comments") or "").strip() or None,
                players=players,
            )
        )
    return _int(root.get("total")) or 0, plays
