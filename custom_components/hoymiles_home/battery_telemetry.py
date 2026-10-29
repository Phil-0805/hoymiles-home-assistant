"""Read-only battery device temperatures with bounded background polling."""

import asyncio
from datetime import UTC, datetime, timedelta
import re

from .const import MODULE_INTERVAL
from .errors import HoymilesAuthError, HoymilesConnectionError, HoymilesRateLimitError
from .telemetry import number


def parse_battery_temperatures(payload):
    """Read only serial, parent and Celsius temp from the dedicated device list."""
    if not isinstance(payload, list) or len(payload) > 64:
        raise HoymilesConnectionError("Invalid battery temperature response")
    result = {}

    def add(item, parent=None):
        if not isinstance(item, dict):
            return
        serial = item.get("sn")
        if not isinstance(serial, str) or not re.fullmatch(r"[0-9A-Fa-f]{12,24}", serial):
            return
        serial = serial.upper()
        if serial == parent:
            return  # A unit may also list its own identifier among its packs.
        value = number(item.get("temp"))
        # Do not infer tenths of degrees or reinterpret arbitrary/sentinel values.
        if value is not None and not -80 <= value <= 120:
            value = None
        record = {"temperature": value, "parent": parent}
        if serial in result and result[serial] != record:
            raise HoymilesConnectionError("Ambiguous battery temperature identity")
        result[serial] = record
        packs = item.get("pack_list", []) if parent is None else []
        if not isinstance(packs, list) or len(packs) > 64:
            raise HoymilesConnectionError("Invalid battery pack response")
        for pack in packs:
            add(pack, serial)
        if len(result) > 128:
            raise HoymilesConnectionError("Battery temperature response exceeds device limit")

    for item in payload:
        add(item)
    return result


class BatteryTelemetryPoller:
    """One optional read every five minutes, independent of live refresh latency."""

    def __init__(self, hass, client, station_id, enabled, on_update):
        self.hass, self.client, self.station_id = hass, client, station_id
        self.enabled, self.on_update = enabled, on_update
        self.values, self.updated = {}, {}
        self.task, self.stopped = None, False
        self.next_allowed = datetime.min.replace(tzinfo=UTC)
        self.status = "pending" if enabled else "disabled"

    def start(self):
        if not self.enabled or self.stopped or datetime.now(UTC) < self.next_allowed:
            return None
        if self.task is None or self.task.done():
            self.next_allowed = datetime.now(UTC) + MODULE_INTERVAL
            self.task = self.hass.async_create_background_task(self._async_poll(), "hoymiles_home battery temperatures")
        return self.task

    def is_fresh(self, serial):
        stamp = self.updated.get(serial)
        return stamp is not None and timedelta(0) <= datetime.now(UTC) - stamp <= MODULE_INTERVAL * 2

    async def _async_poll(self):
        try:
            async with asyncio.timeout(60):
                records = await self.client.async_battery_temperatures(self.station_id)
            now = datetime.now(UTC)
            for serial, record in records.items():
                if serial not in self.values:
                    self.values[serial] = record
                # Missing readings do not renew an older value's response age.
                if record["temperature"] is not None:
                    self.values[serial] = record
                    self.updated[serial] = now
            self.status = "readable" if any(record["temperature"] is not None for record in records.values()) else "no_data"
        except HoymilesRateLimitError as err:
            self.next_allowed = max(self.next_allowed, datetime.now(UTC) + timedelta(seconds=err.retry_after))
            self.status = "rate_limited"
        except (HoymilesAuthError, HoymilesConnectionError, TimeoutError):
            self.status = "unavailable"
        finally:
            if not self.stopped:
                self.on_update()

    async def async_shutdown(self):
        self.stopped = True
        if self.task and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
