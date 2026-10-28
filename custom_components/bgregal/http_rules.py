"""Anleitungen (PDF) je Spiel hochladen, ansehen und löschen – nur mit HA-Anmeldung."""
from __future__ import annotations

from http import HTTPStatus

from aiohttp import web
from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.exceptions import HomeAssistantError

from .core.rules import MAX_BYTES, RuleBookError
from .services import get_regal

CHUNK = 256 * 1024


class RulesUploadView(HomeAssistantView):
    """POST multipart/form-data mit einem oder mehreren Feldern „file“."""

    url = "/api/bgregal/rules/{bgg_id}"
    name = "api:bgregal:rules_upload"
    requires_auth = True

    async def post(self, request: web.Request, bgg_id: str) -> web.Response:
        hass = request.app[KEY_HASS]
        try:
            regal = get_regal(hass)
            game = regal.find_game(int(bgg_id))
        except (HomeAssistantError, ValueError) as err:
            return self.json_message(str(err), HTTPStatus.NOT_FOUND)
        try:
            reader = await request.multipart()
        except (AssertionError, ValueError):
            return self.json_message("multipart/form-data erwartet", HTTPStatus.BAD_REQUEST)
        saved = []
        while (field := await reader.next()) is not None:
            if field.name != "file" or not field.filename:
                continue
            # Ganz lesen (höchstens MAX_BYTES), dann im Executor prüfen und speichern
            chunks, size = [], 0
            while chunk := await field.read_chunk(CHUNK):
                size += len(chunk)
                if size > MAX_BYTES:
                    return self.json_message("Die Datei ist größer als 100 MB",
                                             HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                chunks.append(chunk)
            try:
                saved.append(await hass.async_add_executor_job(
                    regal.rules.add, game["bgg_id"], field.filename, chunks))
            except RuleBookError as err:
                return self.json_message(str(err), HTTPStatus.BAD_REQUEST)
        if not saved:
            return self.json_message("Keine Datei im Feld „file“", HTTPStatus.BAD_REQUEST)
        await regal.async_refresh()
        return self.json({"saved": saved})


class RulesFileView(HomeAssistantView):
    """GET liefert das PDF, DELETE löscht es."""

    url = "/api/bgregal/rules/{bgg_id}/{filename}"
    name = "api:bgregal:rules_file"
    requires_auth = True

    async def get(self, request: web.Request, bgg_id: str, filename: str) -> web.StreamResponse:
        hass = request.app[KEY_HASS]
        try:
            pdf = await hass.async_add_executor_job(get_regal(hass).rules.path, int(bgg_id), filename)
        except (HomeAssistantError, RuleBookError, ValueError) as err:
            return self.json_message(str(err), HTTPStatus.NOT_FOUND)
        return web.FileResponse(
            pdf, headers={"Content-Type": "application/pdf", "Cache-Control": "no-store"}
        )

    async def delete(self, request: web.Request, bgg_id: str, filename: str) -> web.Response:
        hass = request.app[KEY_HASS]
        try:
            regal = get_regal(hass)
            await hass.async_add_executor_job(regal.rules.remove, int(bgg_id), filename)
        except (HomeAssistantError, RuleBookError, ValueError) as err:
            return self.json_message(str(err), HTTPStatus.NOT_FOUND)
        await regal.async_refresh()
        return self.json({"removed": filename})
