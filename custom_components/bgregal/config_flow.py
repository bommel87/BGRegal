"""Einrichtung (BGG-Name + Token) und Optionen."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_END_SCENE,
    CONF_LOAN_DAYS,
    CONF_LONG_MONTHS,
    CONF_MEDIA_PLAYER,
    CONF_NOTIFY,
    CONF_SCAN_HOURS,
    CONF_TOKEN,
    CONF_USERNAME,
    DEFAULTS,
    DOMAIN,
)
from .core.client import BggClient
from .core.errors import BggAuthError, BggError, BggNotFoundError


class BgRegalConfigFlow(ConfigFlow, domain=DOMAIN):
    """Fragt BGG-Benutzername und API-Token ab und prüft beides."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            token = user_input[CONF_TOKEN].strip()
            client = BggClient(async_get_clientsession(self.hass), username, token)
            try:
                await client.validate_user()
            except BggAuthError:
                errors["base"] = "invalid_auth"
            except BggNotFoundError:
                errors[CONF_USERNAME] = "user_not_found"
            except BggError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(username.lower())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"BGRegal ({username})",
                    data={CONF_USERNAME: username, CONF_TOKEN: token},
                )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_TOKEN): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return BgRegalOptionsFlow()


class BgRegalOptionsFlow(OptionsFlow):
    """Sync-Intervall, Wiedergabegerät, Sitzungsende, Erinnerungen, Benachrichtigung."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            # Leere Auswahlfelder kommen gar nicht mit -> als "nicht gesetzt" speichern
            for key in (CONF_MEDIA_PLAYER, CONF_END_SCENE, CONF_NOTIFY):
                user_input.setdefault(key, "")
            return self.async_create_entry(data=user_input)

        opts = {**DEFAULTS, **self.config_entry.options}
        notify_services = sorted(
            f"notify.{name}" for name in self.hass.services.async_services().get("notify", {})
        )

        def optional(key: str) -> vol.Optional:
            value = opts.get(key)
            return vol.Optional(key, description={"suggested_value": value} if value else None)

        schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_HOURS, default=opts[CONF_SCAN_HOURS]): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, max=48, step=1, unit_of_measurement="h")
                ),
                optional(CONF_MEDIA_PLAYER): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="media_player")
                ),
                optional(CONF_END_SCENE): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["scene", "script"])
                ),
                vol.Required(CONF_LOAN_DAYS, default=opts[CONF_LOAN_DAYS]): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, max=365, step=1, unit_of_measurement="d")
                ),
                vol.Required(CONF_LONG_MONTHS, default=opts[CONF_LONG_MONTHS]): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, max=120, step=1)
                ),
                optional(CONF_NOTIFY): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=notify_services, custom_value=True)
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
