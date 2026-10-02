"""Config flow for Hoymiles S-Miles Home."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .api import HoymilesAuthError, HoymilesConnectionError, HoymilesHomeClient
from .const import CONF_STATION_ID, DOMAIN


class HoymilesHomeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the integration config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            client = HoymilesHomeClient(
                async_get_clientsession(self.hass),
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
            )
            try:
                await client.async_login()
                devices = await client.async_device_tree(user_input[CONF_STATION_ID])
                if not devices:
                    errors["base"] = "invalid_station"
            except HoymilesAuthError:
                errors["base"] = "invalid_auth"
            except HoymilesConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            if not errors:
                await self.async_set_unique_id(
                    f"{user_input[CONF_USERNAME].lower()}_{user_input[CONF_STATION_ID]}"
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Hoymiles Home {user_input[CONF_STATION_ID]}",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                    vol.Required(CONF_STATION_ID): vol.Coerce(int),
                }
            ),
            errors=errors,
        )
