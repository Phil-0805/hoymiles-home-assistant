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
        self.modules: dict[…2948 tokens truncated…int) -> None:
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
