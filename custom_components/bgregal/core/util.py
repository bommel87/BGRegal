"""Kleine Hilfsfunktionen."""
from __future__ import annotations

import re

_SPOTIFY_URL = re.compile(
    r"https?://open\.spotify\.com/(?:intl-[a-z]+/)?(playlist|album)/([A-Za-z0-9]+)"
)
_SPOTIFY_URI = re.compile(r"spotify:(playlist|album):[A-Za-z0-9]+")
_PROFILE = re.compile(r"(scene|script)\.[a-z0-9_]+")


def normalize_playlist(value: str) -> str:
    """Spotify-Link oder -URI -> URI. Leer = löschen. ValueError bei allem anderen."""
    v = (value or "").strip()
    if not v:
        return ""
    if _SPOTIFY_URI.fullmatch(v):
        return v
    m = _SPOTIFY_URL.match(v)
    if m:
        return f"spotify:{m.group(1)}:{m.group(2)}"
    raise ValueError(v)


def playlist_media_type(uri: str) -> str:
    parts = uri.split(":")
    return parts[1] if len(parts) >= 3 else "playlist"


def normalize_ean(value: str) -> str | None:
    """EAN/UPC/GTIN: nur Ziffern (Leerzeichen und Striche entfernt). Leer = löschen ("").
    None, wenn es keine gültige Länge (8, 12, 13, 14) hat."""
    digits = re.sub(r"[\s-]", "", value or "")
    if not digits:
        return ""
    if not digits.isdigit() or len(digits) not in (8, 12, 13, 14):
        return None
    return digits


def valid_light_profile(value: str) -> bool:
    return not value or bool(_PROFILE.fullmatch(value))
