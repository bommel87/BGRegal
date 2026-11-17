"""Regal-Scanner: Fotos aus dem Panel entgegennehmen und auswerten – nur mit HA-Anmeldung."""
from __future__ import annotations

from http import HTTPStatus

from aiohttp import web
from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.exceptions import HomeAssistantError

from .const import PHOTO_MAX_BYTES, PHOTO_MAX_COUNT
from .services import get_regal

CHUNK = 256 * 1024


class ShelfPhotoView(HomeAssistantView):
    """POST multipart/form-data: Feld „shelf“ und ein oder mehrere Felder „file“ (Bilder).

    Liefert das Ergebnis wie der Dienst scan_shelf_photo; geändert wird noch nichts."""

    url = "/api/bgregal/shelf_scan"
    name = "api:bgregal:shelf_scan"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        hass = request.app[KEY_HASS]
        try:
            reader = await request.multipart()
        except (AssertionError, ValueError):
            return self.json_message("multipart/form-data erwartet", HTTPStatus.BAD_REQUEST)
        shelf, photos = "", []
        while (field := await reader.next()) is not None:
            if field.name == "shelf":
                shelf = (await field.text()).strip()
                continue
            if field.name != "file":
                continue
            mime = field.headers.get("Content-Type", "")
            if not mime.startswith("image/"):
                return self.json_message("Nur Bilder sind möglich", HTTPStatus.BAD_REQUEST)
            if len(photos) >= PHOTO_MAX_COUNT:
                return self.json_message(f"Höchstens {PHOTO_MAX_COUNT} Fotos", HTTPStatus.BAD_REQUEST)
            chunks, size = [], 0
            while chunk := await field.read_chunk(CHUNK):
                size += len(chunk)
                if size > PHOTO_MAX_BYTES:
                    return self.json_message("Ein Foto ist größer als 20 MB",
                                             HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                chunks.append(chunk)
            photos.append((b"".join(chunks), mime))
        if not shelf:
            return self.json_message("Regal fehlt", HTTPStatus.BAD_REQUEST)
        try:
            result = await get_regal(hass).async_scan_shelf_upload(shelf, photos)
        except HomeAssistantError as err:
            return self.json_message(str(err), HTTPStatus.BAD_REQUEST)
        return self.json(result)
