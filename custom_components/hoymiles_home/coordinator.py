"""Data coordinator for Hoymiles S-Miles Home."""

from __future__ import annotations

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
    DEFAULT_PORT_COUNT,
    DOMAIN,
    ENERGY_SAVE_INTERVAL,
    LIVE_MIN_INTERVAL,
    MAX_ENERGY_SAMPLE_GAP,
    MODULE_INTERVAL,
    STATION_INTERVAL,
    STORAGE_VERSION,
)
from .energy import integrate_battery_energy

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
        self._modules_updated = datetime.min.replace(tzinfo=UTC)
        self._station_updated = datetime.min.replace(tzinfo=UTC)
        self._energy_store: Store[dict[str, Any]] = Store(
            hass,
            STORAGE_VERSION,
            f"{DOMAIN}.{station_id}.battery_energy",
        )
        self._energy_date = dt_util.now().date().isoformat()
        self._charge_wh = 0.0
        self._discharge_wh = 0.0
        self._last_battery_power: float | None = None
        self._last_battery_sample: datetime | None = None
        self._next_energy_save = datetime.min.replace(tzinfo=UTC)

    async def async_initialize(self) -> None:
        """Restore today's calculated battery energy."""
        stored = await self._energy_store.async_load()
        if not isinstance(stored, dict) or stored.get("date") != self._energy_date:
            return
        for key, attribute in (
            ("charge_wh", "_charge_wh"),
            ("discharge_wh", "_discharge_wh"),
        ):
            value = stored.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                setattr(self, attribute, max(float(value), 0.0))

    def _energy_store_data(self) -> dict[str, Any]:
        return {
            "date": self._energy_date,
            "charge_wh": self._charge_wh,
            "discharge_wh": self._discharge_wh,
        }

    async def async_save_energy(self) -> None:
        """Persist calculated battery energy immediately."""
        await self._energy_store.async_save(self._energy_store_data())

    def _update_battery_energy(
        self, live: dict[str, Any], now: datetime
    ) -> dict[str, Any]:
        """Update the local daily charge/discharge energy counters."""
        local_date = dt_util.now().date().isoformat()
        if local_date != self._energy_date:
            self._energy_date = local_date
            self._charge_wh = 0.0
            self._discharge_wh = 0.0
            self._last_battery_power = None
            self._last_battery_sample = None

        value = live.get("power", {}).get("bat")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            current_power = float(value)
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
                    )
            self._last_battery_power = current_power
            self._last_battery_sample = now

        if now >= self._next_energy_save:
            self._energy_store.async_delay_save(self._energy_store_data, 5)
            self._next_energy_save = now + ENERGY_SAVE_INTERVAL

        return {
            "date": self._energy_date,
            "charge_wh": round(self._charge_wh, 3),
            "discharge_wh": round(self._discharge_wh, 3),
        }

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
            }
        except HoymilesAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except HoymilesConnectionError as err:
            raise UpdateFailed(str(err)) from err
