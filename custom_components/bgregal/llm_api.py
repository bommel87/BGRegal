"""LLM-API „Spielregeln (BGRegal)“ für HA Assist: Regelfragen aus Anleitungen (PDF) und Links (Errata, FAQ)."""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import llm
from homeassistant.helpers.aiohttp_client import async_get_clientsession

try:  # neuere HA-Versionen beschreiben Werkzeug-Parameter mit probatio
    import probatio as vol
except ImportError:
    import voluptuous as vol

from .const import DOMAIN
from .core import links as lnk
from .core import session as sess
from .runtime import BgRegal
from .services import get_regal

API_ID = DOMAIN
API_PROMPT = (
    "Du beantwortest Fragen zu Brettspielregeln. Hole dir die Anleitung immer mit get_game_rules "
    "und antworte nur auf Grundlage dieses Textes. Steht die Antwort nicht in der Anleitung, sag das "
    "offen, statt zu raten. Errata und FAQ aus den Links gehen der Anleitung vor. Nennt die Frage kein "
    "Spiel, ist das Spiel der laufenden Sitzung gemeint. Antworte kurz, in der Sprache der Frage, und "
    "nenne die Quelle (Seite der Anleitung oder Titel des Links)."
)


def _result(data: dict[str, Any]) -> Any:
    # ToolResult gibt es erst ab HA 2026.x; ältere Versionen erwarten ein dict
    tool_result = getattr(llm, "ToolResult", None)
    return tool_result(data=data) if tool_result else data


async def _link_text(hass: HomeAssistant, regal: BgRegal, bgg_id: int, url: str) -> str:
    """Text hinter einem Link; frisch aus dem Zwischenspeicher, sonst neu abrufen."""
    cached = await hass.async_add_executor_job(regal.links.get, bgg_id, url)
    if cached and cached[1]:
        return cached[0]
    try:
        data, content_type, charset = await lnk.download(async_get_clientsession(hass), url)
        text = await hass.async_add_executor_job(lnk.to_text, data, content_type, charset)
    except Exception as err:  # noqa: BLE001 – Netzfehler, kaputte Seiten
        if cached:
            return cached[0]
        raise lnk.LinkError(str(err) or type(err).__name__) from err
    await hass.async_add_executor_job(regal.links.put, bgg_id, url, text)
    return text


def _running_game(regal: BgRegal) -> dict[str, Any] | None:
    session = regal.snapshot.get("session")
    if session and session["state"] == sess.RUNNING:
        try:
            return regal.find_game(session["bgg_id"])
        except HomeAssistantError:
            return None
    return None


class GetGameRulesTool(llm.Tool):
    name = "get_game_rules"
    description = (
        "Liefert den Text der Anleitung(en) eines Brettspiels aus der Sammlung, mit Seitenmarken, "
        "sowie den Text hinterlegter Links (Errata, FAQ, Almanach). "
        "Ohne Spielnamen das Spiel der laufenden Sitzung."
    )
    parameters = vol.Schema({vol.Optional("game", description="Name des Spiels, z. B. 'Catan'"): str})
    integration = DOMAIN

    async def async_call(
        self, hass: HomeAssistant, tool_input: llm.ToolInput, llm_context: llm.LLMContext
    ) -> Any:
        regal = get_regal(hass)
        name = (tool_input.tool_args.get("game") or "").strip()
        if name:
            try:
                game = regal.find_game(name=name)
            except HomeAssistantError as err:
                return _result({"error": str(err)})
        elif (game := _running_game(regal)) is None:
            return _result({"error": "Es läuft keine Sitzung. Frag nach, welches Spiel gemeint ist."})
        rulebooks = []
        for entry in await hass.async_add_executor_job(regal.rules.list, game["bgg_id"]):
            try:
                text = await hass.async_add_executor_job(regal.rules.text, game["bgg_id"], entry["name"])
            except Exception as err:  # noqa: BLE001 – ein kaputtes PDF darf die Antwort nicht verhindern
                text = f"(nicht lesbar: {err})"
            rulebooks.append({"file": entry["name"], "text": text or "(kein Text, vermutlich ein Scan)"})
        links = []
        for link in game.get("links", []):
            try:
                text = await _link_text(hass, regal, game["bgg_id"], link["url"])
                links.append({**link, "text": text or "(kein Text gefunden)"})
            except lnk.LinkError as err:
                links.append({**link, "error": f"nicht abrufbar: {err}"})
        if not rulebooks and not links:
            return _result({"game": game["name"], "error": "Für dieses Spiel ist keine Anleitung hinterlegt."})
        return _result({"game": game["name"], "rulebooks": rulebooks, "links": links})


class ListRulebooksTool(llm.Tool):
    name = "list_rulebooks"
    description = "Listet die Spiele, für die eine Anleitung oder ein Link hinterlegt ist."
    integration = DOMAIN

    async def async_call(
        self, hass: HomeAssistant, tool_input: llm.ToolInput, llm_context: llm.LLMContext
    ) -> Any:
        regal = get_regal(hass)
        index = await hass.async_add_executor_job(regal.rules.index)
        games = regal.snapshot.get("games", [])
        return _result({"games": sorted(g["name"] for g in games if g["bgg_id"] in index or g.get("links"))})


class RulesAPI(llm.API):
    """Erscheint beim Assist-Agenten unter „Steuern von Home Assistant“."""

    async def async_get_api_instance(self, llm_context: llm.LLMContext) -> llm.APIInstance:
        prompt = API_PROMPT
        try:
            if game := _running_game(get_regal(self.hass)):
                prompt += f" Laufende Sitzung: {game['name']}."
        except HomeAssistantError:
            pass
        return llm.APIInstance(
            api=self,
            api_prompt=prompt,
            llm_context=llm_context,
            tools=[GetGameRulesTool(), ListRulebooksTool()],
        )


@callback
def async_setup_llm_api(hass: HomeAssistant) -> None:
    llm.async_register_api(hass, RulesAPI(hass=hass, id=API_ID, name="Spielregeln (BGRegal)"))
