"""Config flow for Hoymiles S-Miles Home."""

from __future__ import annotations

from typing import Any
from zoneinfo import available_timezones
from homeassistant.core import callback

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import HoymilesAuthError, HoymilesConnectionError, HoymilesHomeClient
from .const import CONF_INVERTER_DETAILS, CONF_STATION_ID, CONF_STATION_TIMEZONE, DOMAIN
from .telemetry import PV_POWER_SOURCE, PV_POWER_SOURCES


class HoymilesHomeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Authenticate, then select one station or enter its ID manually."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return HoymilesHomeOptionsFlow()

    def __init__(self) -> None:
        self._client: HoymilesHomeClient | None = None
        self._credentials: dict[str, str] = {}
        self._stations: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._credentials = {
                CONF_USERNAME: user_input[CONF_USERNAME].strip(),
                CONF_PASSWORD: user_input[CONF_PASSWORD],
            }
            self._client = HoymilesHomeClient(
                async_get_clientsession(self.hass, verify_ssl=True),
                self._credentials[CONF_USERNAME],
                self._credentials[CONF_PASSWORD],
            )
            self._stations = []
            try:
                await self._client.async_login()
            except HoymilesAuthError:
                errors["base"] = "invalid_auth"
            except HoymilesConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            if not errors:
                try:
                    self._stations = await self._client.async_list_stations()
                except HoymilesAuthError:
                    errors["base"] = "invalid_auth"
                except Exception:  # noqa: BLE001
                    # Discovery is optional: keep the established sid setup path.
                    return self._manual_form({"base": "discovery_failed"})
                else:
                    if self._stations:
                        return await self.async_step_select_station()
                    return self._manual_form({"base": "no_stations"})

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_select_station(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if self._client is None:
            return await self.async_step_user()
        errors: dict[str, str] = {}
        if user_input is not None:
            return await self._async_finish(user_input, "select_station")
        return self._station_form(errors)

    async def async_step_manual_station(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if self._client is None:
            return await self.async_step_user()
        if user_input is not None:
            return await self._async_finish(user_input, "manual_station")
        return self._manual_form({})

    def _station_form(self, errors: dict[str, str]) -> ConfigFlowResult:
        options = [
            {
                "value": str(station["sid"]),
                "label": (
                    f"{station['name']} ({station['sid']})"
                    if station["name"] else str(station["sid"])
                ),
            }
            for station in self._stations
        ]
        return self.async_show_form(
            step_id="select_station",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_STATION_ID): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            mode=SelectSelectorMode.DROPDOWN,
                            custom_value=True,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    def _manual_form(self, errors: dict[str, str]) -> ConfigFlowResult:
        return self.async_show_form(
            step_id="manual_station",
            data_schema=vol.Schema(
                {vol.Required(CONF_STATION_ID): vol.All(vol.Coerce(int), vol.Range(min=1))}
            ),
            errors=errors,
        )

    async def _async_finish(
        self, user_input: dict[str, Any], step_id: str
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        raw_id = user_input[CONF_STATION_ID]
        try:
            if isinstance(raw_id, bool) or not isinstance(raw_id, (str, int)):
                raise ValueError
            if isinstance(raw_id, str):
                raw_id = raw_id.strip()
                if not raw_id.isascii() or not raw_id.isdecimal():
                    raise ValueError
            station_id = int(raw_id)
            if station_id <= 0:
                raise ValueError
        except (TypeError, ValueError):
            errors[CONF_STATION_ID] = "invalid_station_id"
        else:
            try:
                devices = await self._client.async_device_tree(station_id)
                if not devices:
                    errors["base"] = "invalid_station"
            except HoymilesAuthError:
                return await self._async_login_form_with_error()
            except HoymilesConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            if not errors:
                # Keep the existing identity and persisted schema for upgrades.
                await self.async_set_unique_id(
                    f"{self._credentials[CONF_USERNAME].lower()}_{station_id}"
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Hoymiles Home {station_id}",
                    data={**self._credentials, CONF_STATION_ID: station_id},
                )
        if step_id == "select_station":
            return self._station_form(errors)
        return self._manual_form(errors)

    async def _async_login_form_with_error(self) -> ConfigFlowResult:
        """Return to credentials if the session expires during station selection."""
        self._client = None
        self._credentials = {}
        self._stations = []
        result = await self.async_step_user()
        result["errors"] = {"base": "invalid_auth"}
        return result


class HoymilesHomeOptionsFlow(config_entries.OptionsFlow):
    """Allow comparison of PV fields without recreating the station."""

    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title="", data={**self.config_entry.options, **user_input}
            )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(
                    PV_POWER_SOURCE,
                    default=self.config_entry.options.get(PV_POWER_SOURCE, "auto"),
                ): SelectSelector(SelectSelectorConfig(
                    options=list(PV_POWER_SOURCES),
                    translation_key=PV_POWER_SOURCE,
                    mode=SelectSelectorMode.DROPDOWN,
                )),
                vol.Optional(
                    CONF_INVERTER_DETAILS,
                    default=self.config_entry.options.get(CONF_INVERTER_DETAILS, False),
                ): BooleanSelector(),
                vol.Optional(
                    CONF_STATION_TIMEZONE,
                    default=self.config_entry.options.get(CONF_STATION_TIMEZONE, self.hass.config.time_zone),
                ): SelectSelector(SelectSelectorConfig(
                    options=sorted(available_timezones()), mode=SelectSelectorMode.DROPDOWN,
                )),
            }),
        )
