"""Data coordinator for Hoymiles S-Miles Home."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import logging
from typing import Any

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    HoymilesAuthError,
    HoymilesConnectionError,
    HoymilesHomeClient,
    microinverters,
)
from .const import (
    BATTERY_SETTINGS_INTERVAL,
    BATTERY_ENERGY_CALCULATION_VERSION,
    DEFAULT_PORT_COUNT,
    DOMAIN,
    ENERGY_SAVE_INTERVAL,
    LIVE_MIN_INTERVAL,
    MAX_ENERGY_SAMPLE_GAP,
    MODULE_INTERVAL,
    STATION_INTERVAL,
    STORAGE_VERSION,
)
from .energy import integrate_battery_energy, integrate_positive_energy

_LOGGER = logging.getLogger(__name__)


class HoymilesHomeCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinate fast live data and slower chart data."""

    def __init__(self, hass, client: HoymilesHomeClient, station_id: int) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=LIVE_MIN_INTERVAL,
        )
        self.client = client
        self.station_id = station_id
        self.device_tree: list[dict[str, Any]] = []
        self.inverters: list[dict[str, Any]] = []
        self.modules: dict[int, dict[int, dict[str, float | None]]] = {}
        self.station: dict[str, Any] = {}
        self.battery_settings: dict[str, Any] = {
            "readable": False,
            "error": "not_yet_read",
        }
        self._modules_updated = datetime.min.replace(tzinfo=UTC)
        self._station_updated = datetime.min.replace(tzinfo=UTC)
        self._battery_settings_updated = datetime.min.replace(tzinfo=UTC)
        self._energy_store: Store[dict[str, Any]] = Store(
            hass,
            STORAGE_VERSION,
            f"{DOMAIN}.{station_id}.battery_energy",
        )
        self._energy_date = dt_util.now().date().isoformat()
        self._charge_wh = 0.0
        self._discharge_wh = 0.0
        self._consumption_wh = 0.0
        self._last_battery_power: float | None = None
        self._last_battery_relay_status: int | None = None
        self._last_battery_sample: datetime | None = None
        self._last_load_power: float | None = None
        self._last_load_sample: datetime | None = None
        self._next_energy_save = datetime.min.replace(tzinfo=UTC)
        self._battery_settings_lock = asyncio.Lock()

    async def async_initialize(self) -> None:
        """Restore today's calculated battery energy."""
        stored = await self._energy_store.async_load()
        if (
            not isinstance(stored, dict)
            or stored.get("date") != self._energy_date
            or stored.get("calculation_version")
            != BATTERY_ENERGY_CALCULATION_VERSION
        ):
            return
        for key, attribute in (
            ("charge_wh", "_charge_wh"),
            ("discharge_wh", "_discharge_wh"),
            ("consumption_wh", "_consumption_wh"),
        ):
            value = stored.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                setattr(self, attribute, max(float(value), 0.0))

    def _energy_store_data(self) -> dict[str, Any]:
        return {
            "calculation_version": BATTERY_ENERGY_CALCULATION_VERSION,
            "date": self._energy_date,
            "charge_wh": self._charge_wh,
            "discharge_wh": self._discharge_wh,
            "consumption_wh": self._consumption_wh,
        }

    async def async_save_energy(self) -> None:
        """Persist calculated battery energy immediately."""
        await self._energy_store.async_save(self._energy_store_data())

    async def _async_refresh_battery_settings(self) -> None:
        """Refresh read-only battery settings without delaying live telemetry."""
        try:
            async with self._battery_settings_lock:
                self.battery_settings = await self.client.async_battery_settings(
                    self.station_id
                )
        except (HoymilesAuthError, HoymilesConnectionError) as err:
            self.battery_settings = {
                "readable": False,
                "error": str(err),
            }
            _LOGGER.debug("Could not read battery settings: %s", err)

    def _update_battery_energy(
        self, live: dict[str, Any], now: datetime
    ) -> dict[str, Any]:
        """Update the local daily charge/discharge energy counters."""
        local_date = dt_util.now().date().isoformat()
        if local_date != self._energy_date:
            self._energy_date = local_date
            self._charge_wh = 0.0
            self._discharge_wh = 0.0
            self._consumption_wh = 0.0
            self._last_battery_power = None
            self._last_battery_relay_status = None
            self._last_battery_sample = None
            self._last_load_power = None
            self._last_load_sample = None

        value = live.get("power", {}).get("bat")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            current_power = float(value)
            relay_value = live.get("brs")
            current_relay_status = (
                int(relay_value)
                if isinstance(relay_value, (int, float))
                and not isinstance(relay_value, bool)
                else None
            )
            if (
                self._last_battery_power is not None
                and self._last_battery_sample is not None
            ):
                elapsed = (now - self._last_battery_sample).total_seconds()
                if 0 < elapsed <= MAX_ENERGY_SAMPLE_GAP.total_seconds():
                    self._charge_wh, self._discharge_wh = integrate_battery_energy(
                        self._charge_wh,
                        self._discharge_wh,
                        self._last_battery_power,
                        current_power,
                        elapsed,
                        self._last_battery_relay_status,
                        current_relay_status,
                    )
            self._last_battery_power = current_power
            self._last_battery_relay_status = current_relay_status
            self._last_battery_sample = now

        load_value = live.get("power", {}).get("load")
        if isinstance(load_value, (int, float)) and not isinstance(load_value, bool):
            current_load_power = max(float(load_value), 0.0)
            if self._last_load_power is not None and self._last_load_sample is not None:
                elapsed = (now - self._last_load_sample).total_seconds()
                if 0 < elapsed <= MAX_ENERGY_SAMPLE_GAP.total_seconds():
                    self._consumption_wh = integrate_positive_energy(
                        self._consumption_wh,
                        self._last_load_power,
                        current_load_power,
                        elapsed,
                    )
            self._last_load_power = current_load_power
            self._last_load_sample = now

        if now >= self._next_energy_save:
            self._energy_store.async_delay_save(self._energy_store_data, 5)
            self._next_energy_save = now + ENERGY_SAVE_INTERVAL

        return {
            "date": self._energy_date,
            "charge_wh": round(self._charge_wh, 3),
            "discharge_wh": round(self._discharge_wh, 3),
            "consumption_wh": round(self._consumption_wh, 3),
        }

    async def _async_apply_battery_settings(
        self, mode: int, mode_data: dict[str, Any]
    ) -> None:
        """Write battery settings, read them back and notify entities."""
        async with self._battery_settings_lock:
            if self.battery_settings.get("writable") is not True:
                raise HoymilesConnectionError(
                    "Battery settings are not verified against current app data"
                )
            request_method = self.battery_settings.get("request_method")
            await self.client.async_write_battery_settings(
                self.station_id,
                mode,
                mode_data,
                request_method=request_method,
            )
            refreshed = await self.client.async_battery_settings(self.station_id)
            self.battery_settings = refreshed
            if self.data is not None:
                self.async_set_updated_data(
                    {
                        **self.data,
                        "battery_settings": refreshed,
                    }
                )
            if refreshed.get("mode") != mode:
                raise HoymilesConnectionError(
                    "Battery did not confirm the requested mode"
                )
            confirmed = refreshed.get("active_settings")
            if not isinstance(confirmed, dict):
                raise HoymilesConnectionError(
                    "Battery returned no active settings after the write"
                )
            for key, requested in mode_data.items():
                if isinstance(requested, (str, int, float, bool)) and (
                    confirmed.get(key) != requested
                ):
                    raise HoymilesConnectionError(
                        f"Battery did not confirm the requested {key}"
                    )

    async def async_set_battery_reserve_soc(self, reserve_soc: int) -> None:
        """Set reserve SOC for the active battery mode."""
        mode = self.battery_settings.get("mode")
        active_settings = self.battery_settings.get("active_settings")
        if not isinstance(mode, int) or not isinstance(active_settings, dict):
            raise HoymilesConnectionError("Active battery settings are unavailable")
        updated = deepcopy(active_settings)
        updated["reserve_soc"] = int(reserve_soc)
        await self._async_apply_battery_settings(mode, updated)

    async def async_set_battery_mode(self, mode: int) -> None:
        """Switch to a battery mode while preserving its complete settings."""
        mode_settings = self.battery_settings.get("mode_settings")
        if not isinstance(mode_settings, dict):
            raise HoymilesConnectionError("Battery mode settings are unavailable")
        settings = mode_settings.get(mode)
        if not isinstance(settings, dict):
            raise HoymilesConnectionError(f"Battery mode {mode} is unavailable")
        await self._async_apply_battery_settings(mode, deepcopy(settings))

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            live = await self.client.async_live(self.station_id)
            now = datetime.now(UTC)
            battery_energy = self._update_battery_energy(live, now)
            delay_ms = live.get("dly")
            if isinstance(delay_ms, (int, float)):
                self.update_interval = max(
                    LIVE_MIN_INTERVAL,
                    timedelta(milliseconds=delay_ms),
                )

            if not self.device_tree:
                self.device_tree = await self.client.async_device_tree(self.station_id)
                self.inverters = microinverters(self.device_tree)

            if now - self._station_updated >= STATION_INTERVAL:
                try:
                    self.station = await self.client.async_station_realtime(
                        self.station_id
                    )
                except HoymilesAuthError:
                    raise
                except HoymilesConnectionError as err:
                    _LOGGER.debug("Could not update station totals: %s", err)
                else:
                    self._station_updated = now

            if now - self._battery_settings_updated >= BATTERY_SETTINGS_INTERVAL:
                self._battery_settings_updated = now
                self.hass.async_create_task(
                    self._async_refresh_battery_settings(),
                    f"{DOMAIN} battery settings",
                )

            if now - self._modules_updated >= MODULE_INTERVAL:
                chart_date = dt_util.now().date().isoformat()
                modules = {
                    inverter_id: dict(ports)
                    for inverter_id, ports in self.modules.items()
                }
                for inverter in self.inverters:
                    inverter_id = inverter["id"]
                    modules.setdefault(inverter_id, {})
                    for port in range(1, DEFAULT_PORT_COUNT + 1):
                        try:
                            modules[inverter_id][port] = (
                                await self.client.async_module_values(
                                    self.station_id,
                                    inverter_id,
                                    port,
                                    chart_date,
                                )
                            )
                        except HoymilesAuthError:
                            raise
                        except HoymilesConnectionError as err:
                            _LOGGER.debug(
                                "Could not update inverter %s port %s: %s",
                                inverter_id,
                                port,
                                err,
                            )
                self.modules = modules
                self._modules_updated = now

            return {
                "live": live,
                "station": self.station,
                "device_tree": self.device_tree,
                "inverters": self.inverters,
                "modules": self.modules,
                "battery_energy": battery_energy,
                "battery_settings": self.battery_settings,
            }
        except HoymilesAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except HoymilesConnectionError as err:
            raise UpdateFailed(str(err)) from err
