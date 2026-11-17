"""Fotos vom Regal-Scanner als Medienquelle, nur damit HA AI Task sie als Anhang lesen kann.

Die Fotos liegen nur für die Dauer der Erkennung in einer temporären Datei und tauchen
nicht im Medien-Browser auf.
"""
from __future__ import annotations

from pathlib import Path

from homeassistant.components.media_player import MediaClass, MediaType
from homeassistant.components.media_source import (
    BrowseMediaSource,
    MediaSource,
    MediaSourceItem,
    PlayMedia,
    Unresolvable,
)
from homeassistant.core import HomeAssistant

from .const import DOMAIN

DATA_PHOTOS = f"{DOMAIN}_photos"  # Kennung -> (Pfad, MIME-Typ)


async def async_get_media_source(hass: HomeAssistant) -> MediaSource:
    return PhotoSource(hass)


def photo_id(key: str) -> str:
    return f"media-source://{DOMAIN}/{key}"


class PhotoSource(MediaSource):
    name = "BGRegal"

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(DOMAIN)
        self.hass = hass

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        entry = self.hass.data.get(DATA_PHOTOS, {}).get(item.identifier)
        if entry is None:
            raise Unresolvable(f"Foto {item.identifier} gibt es nicht (mehr)")
        path, mime = entry
        return PlayMedia(url="", mime_type=mime, path=Path(path))

    async def async_browse_media(self, item: MediaSourceItem) -> BrowseMediaSource:
        # Die Fotos sind nur kurz da; im Medien-Browser bleibt der Ordner leer
        return BrowseMediaSource(
            domain=DOMAIN, identifier=None, media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.IMAGE, title=self.name, can_play=False,
            can_expand=True, children=[],
        )
