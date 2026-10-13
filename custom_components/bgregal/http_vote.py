"""Abstimmseite für Gäste ohne Home-Assistant-Zugang.

Jeder Spieleabend hat einen zufälligen, geheimen Schlüssel im Link. Wer den Link kennt, kann
nur für diesen Abend abstimmen – sonst nichts. Abstimmen geht bis 6 Uhr am Morgen danach.
"""
from __future__ import annotations

import re
from http import HTTPStatus
from pathlib import Path
from typing import Any

from aiohttp import web
from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.exceptions import HomeAssistantError

from .services import get_regal

TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{16,64}")
PAGE = Path(__file__).parent / "frontend" / "vote.html"
MAX_VOTES = 50


async def _evening(request: web.Request, token: str):
    if not TOKEN_RE.fullmatch(token):
        return None, None
    hass = request.app[KEY_HASS]
    try:
        regal = get_regal(hass)
    except HomeAssistantError:
        return None, None
    evening = await hass.async_add_executor_job(regal.store.evening_by_token, token)
    return regal, evening


class VotePageView(HomeAssistantView):
    """Liefert die Abstimmseite (HTML)."""

    url = "/api/bgregal/vote/{token}"
    name = "api:bgregal:vote_page"
    requires_auth = False

    async def get(self, request: web.Request, token: str) -> web.StreamResponse:
        _, evening = await _evening(request, token)
        if evening is None:
            return web.Response(status=HTTPStatus.NOT_FOUND, text="Not found")
        html = await request.app[KEY_HASS].async_add_executor_job(PAGE.read_text, "utf-8")
        return web.Response(
            text=html,
            content_type="text/html",
            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
                     "X-Robots-Tag": "noindex"},
        )


class VoteApiView(HomeAssistantView):
    """Daten des Abends lesen und Stimmen abgeben."""

    url = "/api/bgregal/vote/{token}/data"
    name = "api:bgregal:vote_data"
    requires_auth = False

    async def get(self, request: web.Request, token: str) -> web.Response:
        regal, evening = await _evening(request, token)
        if evening is None:
            return self.json_message("Not found", HTTPStatus.NOT_FOUND)
        return self.json(self._public(regal, evening))

    async def post(self, request: web.Request, token: str) -> web.Response:
        regal, evening = await _evening(request, token)
        if evening is None:
            return self.json_message("Not found", HTTPStatus.NOT_FOUND)
        try:
            body = await request.json()
            voter = str(body["voter"])[:60]
            games = [int(g) for g in body.get("games", [])][:MAX_VOTES]
        except (ValueError, KeyError, TypeError):
            return self.json_message("Bad request", HTTPStatus.BAD_REQUEST)
        try:
            await regal.async_public_vote(token, voter, games)
        except HomeAssistantError as err:
            return self.json_message(str(err), HTTPStatus.BAD_REQUEST)
        evening = await request.app[KEY_HASS].async_add_executor_job(regal.store.evening_by_token, token)
        return self.json(self._public(regal, evening))

    @staticmethod
    def _public(regal, evening: dict[str, Any]) -> dict[str, Any]:
        """Nur, was Gäste sehen dürfen: keine IDs anderer Abende, keine Zuordnungen."""
        games = {g["bgg_id"]: g for g in regal.snapshot.get("games", [])}
        candidates = []
        for bgg_id in evening["candidates"]:
            g = games.get(bgg_id)
            if g is None:
                continue
            candidates.append({
                "bgg_id": bgg_id, "name": g["name"], "thumbnail": g.get("thumbnail"),
                "min_players": g.get("min_players"), "max_players": g.get("max_players"),
                "playing_time": g.get("playing_time"), "mode": g.get("mode"),
            })
        return {
            "title": evening["title"],
            "start": evening["start"],
            "guests": [regal.me, *evening["guests"]],
            "candidates": candidates,
            "votes": evening["votes"],
            "open": regal.evening_open(evening),
        }
