"""Config flow for Hoymiles S-Miles Home."""

from __future__ import annotations

from functools import lru_cache
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
from .const import CONF_BATTERY_CONTROLS, CONF_DEVICE_CONTROLS, CONF_BATTERY_TEMPERATURES, CONF_INVERTER_DETAILS, CONF_STATION_ID, CONF_STATION_TIMEZONE, DOMAIN
from .telemetry import PV_POWER_SOURCE, PV_POWER_SOURCES
from .const import CONF_CLIENT_PROFILE, CLIENT_PROFILES
from .cloud_logging import log_failure


def _profile_selector(default="home"):
    return {vol.Optional(CONF_CLIENT_PROFILE, default=default): SelectSelector(SelectSelectorConfig(
        options=list(CLIENT_PROFILES), translation_key=CONF_CLIENT_PROFILE,
        mode=SelectSelectorMode.DROPDOWN,
    ))}


@lru_cache(maxsize=1)
def _time_zone_options() -> list[str]:
    """Enumerate the timezone database once, only from the executor."""
    return sorted(available_timezones())


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

    async def async_step_reauth(self, entry_data) -> ConfigFlowResult:
        """Renew credentials on the existing entry, retaining all identities."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors = {}
        if user_input is not None:
            profile = user_input.get(CONF_CLIENT_PROFILE, entry.data.get(CONF_CLIENT_PROFILE, "home"))
            client = HoymilesHomeClient(
                async_get_clientsession(self.hass, verify_ssl=True),
                entry.data[CONF_USERNAME], user_input[CONF_PASSWORD],
                **({"profile": profile} if profile != "home" else {}),
            )
            try:
                await client.async_login()
                if not await client.async_device_tree(entry.data[CONF_STATION_ID]):
                    errors["base"] = "invalid_station"
            except HoymilesAuthError as err:
                log_failure("reauthentication", err)
                errors["base"] = "invalid_auth"
            except HoymilesConnectionError as err:
                log_failure("reauthentication", err)
                errors["base"] = "cannot_connect"
            if not errors:
                updates = {CONF_PASSWORD: user_input[CONF_PASSWORD]}
                if profile != "home" or CONF_CLIENT_PROFILE in entry.data:
                    updates[CONF_CLIENT_PROFILE] = profile
                return self.async_update_reload_and_abort(
                    entry, data_updates=updates,
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ), **_profile_selector(entry.data.get(CONF_CLIENT_PROFILE, "home"))}), errors=errors,
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._credentials = {
                CONF_USERNAME: user_input[CONF_USERNAME].strip(),
                CONF_PASSWORD: user_input[CONF_PASSWORD],
            }
            profile = user_input.get(CONF_CLIENT_PROFILE, "home")
            if profile != "home":
                self._credentials[CONF_CLIENT_PROFILE] = profile
            self._client = HoymilesHomeClient(
                async_get_clientsession(self.hass, verify_ssl=True),
                self._credentials[CONF_USERNAME],
                self._credentials[CONF_PASSWORD],
                **({"profile": profile} if profile != "home" else {}),
            )
            self._stations = []
            try:
                await self._client.async_login()
            except HoymilesAuthError as err:
                log_failure("login", err)
                errors["base"] = "invalid_auth"
            except HoymilesConnectionError as err:
                log_failure("login", err)
                errors["base"] = "cannot_connect"
            except Exception as err:  # noqa: BLE001
                log_failure("login", err)
                errors["base"] = "unknown"
            if not errors:
                try:
                    self._stations = await self._client.async_list_stations()
                except HoymilesAuthError as err:
                    log_failure("station_discovery", err)
                    errors["base"] = "invalid_auth"
                except Exception as err:  # noqa: BLE001
                    log_failure("station_discovery", err)
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
                    **_profile_selector(),
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
            except HoymilesAuthError as err:
                log_failure("station_validation", err)
                return await self._async_login_form_with_error()
            except HoymilesConnectionError as err:
                log_failure("station_validation", err)
                reason = getattr(err, "reason", None)
                errors["base"] = ("unsupported_station" if reason == "unsupported_profile_operation"
                                  else "invalid_station_response" if reason in {
                                      "invalid_enduser_metadata", "invalid_enduser_station_id",
                                      "invalid_enduser_classification", "invalid_enduser_tree"}
                                  else "cannot_connect")
            except Exception as err:  # noqa: BLE001
                log_failure("station_validation", err)
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
        if self.config_entry.data.get(CONF_CLIENT_PROFILE) == "enduser":
            return await self.async_step_enduser(user_input)
        if user_input is not None:
            options = {**self.config_entry.options, **user_input}
            options.pop(CONF_BATTERY_TEMPERATURES, None)
            return self.async_create_entry(
                title="", data=options
            )
        timezones = await self.hass.async_add_executor_job(_time_zone_options)
        schema = {
            vol.Required(
                PV_POWER_SOURCE,
                default=self.config_entry.options.get(PV_POWER_SOURCE, "auto"),
            ): SelectSelector(SelectSelectorConfig(
                options=list(PV_POWER_SOURCES),
                translation_key=PV_POWER_SOURCE,
                mode=SelectSelectorMode.DROPDOWN,
            )),
            vol.Optional(
                CONF_BATTERY_CONTROLS,
                default=self.config_entry.options.get(CONF_BATTERY_CONTROLS, False),
            ): BooleanSelector(),
            vol.Optional(
                CONF_DEVICE_CONTROLS,
                default=self.config_entry.options.get(CONF_DEVICE_CONTROLS, False),
            ): BooleanSelector(),
            vol.Optional(
                CONF_INVERTER_DETAILS,
                default=self.config_entry.options.get(CONF_INVERTER_DETAILS, False),
            ): BooleanSelector(),
            vol.Optional(
                CONF_STATION_TIMEZONE,
                default=self.config_entry.options.get(CONF_STATION_TIMEZONE, self.hass.config.time_zone),
            ): SelectSelector(SelectSelectorConfig(
                options=timezones, mode=SelectSelectorMode.DROPDOWN,
            )),
        }
        if self.config_entry.data.get(CONF_CLIENT_PROFILE) == "installer":
            unsupported = {CONF_BATTERY_CONTROLS, CONF_DEVICE_CONTROLS, CONF_INVERTER_DETAILS}
            schema = {key: value for key, value in schema.items() if key.schema not in unsupported}
        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema))

    async def async_step_enduser(self, user_input=None) -> ConfigFlowResult:
        """Only expose the setting supported by the Enduser monitoring profile."""
        if user_input is not None:
            return self.async_create_entry(title="", data={**self.config_entry.options, **user_input})
        timezones = await self.hass.async_add_executor_job(_time_zone_options)
        return self.async_show_form(step_id="enduser", data_schema=vol.Schema({
            vol.Required(CONF_STATION_TIMEZONE, default=self.config_entry.options.get(
                CONF_STATION_TIMEZONE, self.hass.config.time_zone)): SelectSelector(
                    SelectSelectorConfig(options=timezones, mode=SelectSelectorMode.DROPDOWN)),
        }))
