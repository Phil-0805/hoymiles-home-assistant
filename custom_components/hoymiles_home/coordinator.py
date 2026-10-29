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
    HoymilesRateLimitError,
    microinverters,
)
from .battery import battery_settings_confirmed
from .const import (
    BATTERY_SETTINGS_INTERVAL,
    BATTERY_ENERGY_CALCULATION_VERSION,
    DOMAIN,
    ENERGY_SAVE_INTERVAL,
    LIVE_MIN_INTERVAL,
    MAX_ENERGY_SAMPLE_GAP,
    MODULE_INTERVAL,
    STATION_INTERVAL,
    STORAGE_VERSION,
)
from .energy import integrate_battery_energy, integrate_positive_energy
from .inverter import inverter_ports
from .telemetry import PV_POWER_SOURCE, live_connected, number

_LOGGER = logging.getLogger(__name__)

BATTERY_WRITE_CONFIRM_ATTEMPTS = 8
BATTERY_WRITE_CONFIRM_INTERVAL = 3


class HoymilesHomeCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinate fast live data and slower chart data."""

    def __init__(
        self, hass, client: HoymilesHomeClient, station_id: int,
        pv_power_source: str = "auto",
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=LIVE_MIN_INTERVAL,
        )
        self.client = client
        self.station_id = station_id
        self.pv_power_source = pv_power_source
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
        self._battery_settings_task: asyncio.Task | None = None
        self._stopped = False
        self.module_updated: dict[tuple[int, int], datetime] = {}

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
            value = number(stored.get(key))
            if value is not None:
                setattr(self, attribute, max(float(value), 0.0))

    async def async_shutdown(self) -> None:
        """Cancel our background read before the entry is removed or reloaded."""
        self._stopped = True
        await super().async_shutdown()
        if self._battery_settings_task and not self._battery_settings_task.done():
            self._battery_settings_task.cancel()
            try:
                await self._battery_settings_task
            except asyncio.CancelledError:
                pass

    def _start_battery_settings_refresh(self) -> asyncio.Task | None:
        if self._stopped:
            return None
        if self._battery_settings_task is None or self._battery_settings_task.done():
            self._battery_settings_task = self.hass.async_create_background_task(
                self._async_refresh_battery_settings(),
                f"{DOMAIN} battery settings",
            )
        return self._battery_settings_task

    async def async_refresh_battery_settings(self) -> None:
        """Manually refresh read-only settings, coalescing concurrent requests."""
        task = self._start_battery_settings_refresh()
        if task is not None:
            await asyncio.shield(task)

    def module_is_fresh(self, inverter_id: int, port: int) -> bool:
        updated = self.module_updated.get((inverter_id, port))
        return updated is not None and (
            datetime.now(UTC) - updated <= MODULE_INTERVAL * 2
        )

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
            async with self._battery_settings_lock, asyncio.timeout(120):
                self.battery_settings = await self.client.async_battery_settings(
                    self.station_id
                )
        except (HoymilesAuthError, HoymilesConnectionError, TimeoutError) as err:
            self.battery_settings = {
                "readable": False,
                "error": str(err) or "Battery settings read timed out",
            }
            _LOGGER.debug("Could not read battery settings: %s", err)
        if not self._stopped:
            self._battery_settings_updated = datetime.now(UTC)
            if self.data is not None:
                self.data["battery_settings"] = self.battery_settings
                # Settings-only updates must not mark a failed live poll healthy.
                self.async_update_listeners()

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

        power = live.get("power")
        power = power if isinstance(power, dict) and live_connected(live) else {}
        value = number(power.get("bat"))
        if value is not None:
            current_power = float(value)
            relay_value = number(live.get("brs"))
            current_relay_status = (
                int(relay_value)
                if relay_value is not None and relay_value in (0, 1, 2)
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
        else:
            self._last_battery_power = None
            self._last_battery_sample = None
            self._last_battery_relay_status = None

        load_value = number(power.get("load"))
        if load_value is not None:
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
        else:
            self._last_load_power = None
            self._last_load_sample = None

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
        self, mode: int | None, *, reserve_soc: int | None = None
    ) -> None:
        """Write battery settings, read them back and notify entities."""
        async with self._battery_settings_lock:
            # Build the payload after taking the lock, using the latest readback.
            if reserve_soc is not None:
                mode = self.battery_settings.get("mode")
                settings = self.battery_settings.get("active_settings")
            else:
                modes = self.battery_settings.get("mode_settings")
                settings = modes.get(mode) if isinstance(modes, dict) else None
            if isinstance(mode, bool) or not isinstance(mode, int) or not isinstance(settings, dict):
                raise HoymilesConnectionError("Battery mode settings are unavailable")
            mode_data = deepcopy(settings)
            if reserve_soc is not None:
                mode_data["reserve_soc"] = reserve_soc
                if self.battery_settings.get("request_method") == "station_action_83":
                    mode_data["soc_l"] = reserve_soc
            if self.battery_settings.get("writable") is not True:
                raise HoymilesConnectionError(
                    "Battery settings are not verified against current app data"
                )
            if reserve_soc is not None and self.battery_settings.get("reserve_soc_verified") is not True:
                raise HoymilesConnectionError("Reserve SOC is not verified against current app data")
            request_method = self.battery_settings.get("request_method")
            await self.client.async_write_battery_settings(
                self.station_id,
                mode,
                mode_data,
                request_method=request_method,
            )
            for attempt in range(BATTERY_WRITE_CONFIRM_ATTEMPTS):
                refreshed = await self.client.async_battery_settings(self.station_id)
                self.battery_settings = refreshed
                if self.data is not None:
                    self.data["battery_settings"] = refreshed
                    self.async_update_listeners()
                if battery_settings_confirmed(refreshed, mode, mode_data):
                    return
                if attempt + 1 < BATTERY_WRITE_CONFIRM_ATTEMPTS:
                    await asyncio.sleep(BATTERY_WRITE_CONFIRM_INTERVAL)
            raise HoymilesConnectionError(
                "Battery did not confirm the requested settings in time"
            )

    async def async_set_battery_reserve_soc(self, reserve_soc: int) -> None:
        """Set reserve SOC using a fresh settings snapshot under the write lock."""
        if isinstance(reserve_soc, bool) or not isinstance(reserve_soc, int) or not 10 <= reserve_soc <= 100:
            raise HoymilesConnectionError("Reserve SOC must be an integer from 10 to 100")
        await self._async_apply_battery_settings(None, reserve_soc=reserve_soc)

    async def async_set_battery_mode(self, mode: int) -> None:
        """Switch mode while preserving the latest complete settings block."""
        await self._async_apply_battery_settings(mode)

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            live = await self.client.async_live(self.station_id)
            now = datetime.now(UTC)
            battery_energy = self._update_battery_energy(live, now)
            delay_ms = number(live.get("dly"))
            try:
                self.update_interval = max(
                    LIVE_MIN_INTERVAL, timedelta(milliseconds=delay_ms or 0)
                )
            except OverflowError:
                self.update_interval = LIVE_MIN_INTERVAL

            if not self.device_tree:
                self.device_tree = await self.client.async_device_tree(self.station_id)
                self.inverters = microinverters(self.device_tree)
                self.inverters = await self.client.async_enrich_inverters(
                    self.station_id, self.inverters
                )

            if now - self._station_updated >= STATION_INTERVAL:
                try:
                    self.station = await self.client.async_station_realtime(
                        self.station_id
                    )
                except (HoymilesAuthError, HoymilesRateLimitError):
                    raise
                except HoymilesConnectionError as err:
                    _LOGGER.debug("Could not update station totals: %s", err)
                else:
                    self._station_updated = now

            if now - self._battery_settings_updated >= BATTERY_SETTINGS_INTERVAL:
                self._battery_settings_updated = now
                self._start_battery_settings_refresh()

            if now - self._modules_updated >= MODULE_INTERVAL:
                chart_date = dt_util.now().date().isoformat()
                modules = {
                    inverter_id: dict(ports)
                    for inverter_id, ports in self.modules.items()
                }
                for inverter in self.inverters:
                    inverter_id = inverter["id"]
                    modules.setdefault(inverter_id, {})
                    for port in inverter_ports(inverter):
                        try:
                            modules[inverter_id][port] = (
                                await self.client.async_module_values(
                                    self.station_id,
                                    inverter_id,
                                    port,
                                    chart_date,
                                )
                            )
                            self.module_updated[(inverter_id, port)] = datetime.now(UTC)
                        except (HoymilesAuthError, HoymilesRateLimitError):
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
                PV_POWER_SOURCE: self.pv_power_source,
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
        except HoymilesRateLimitError as err:
            raise UpdateFailed(str(err), retry_after=err.retry_after) from err
        except HoymilesConnectionError as err:
            raise UpdateFailed(str(err)) from err
