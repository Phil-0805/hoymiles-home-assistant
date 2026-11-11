"""Independent slow telemetry polling, with its own lifecycle and freshness."""

import asyncio
from datetime import UTC, datetime, timedelta

from .errors import HoymilesAuthError, HoymilesConnectionError, HoymilesRateLimitError
from .const import MODULE_INTERVAL
from .inverter import inverter_ports, inverter_model
from .telemetry import number


class ModulePoller:
    """Keep slow chart requests out of the live power refresh path."""

    def __init__(self, hass, client, station_id, timezone, detailed, on_update):
        self.hass, self.client, self.station_id = hass, client, station_id
        self.timezone, self.detailed, self.on_update = timezone, detailed, on_update
        self.modules, self.updated, self.details, self.detail_updated = {}, {}, {}, {}
        self.detail_field_updated = {}
        self.task = None
        self.stopped = False
        self.next_allowed = datetime.min.replace(tzinfo=UTC)
        self.details_status = "disabled" if not detailed else "pending"

    def start(self, inverters):
        if self.stopped or datetime.now(UTC) < self.next_allowed:
            return None
        if self.task is None or self.task.done():
            self.task = self.hass.async_create_background_task(
                self._async_poll(list(inverters)), "hoymiles_home module data"
            )
        return self.task

    async def async_shutdown(self):
        self.stopped = True
        if self.task and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

    def is_fresh(self, device_id, port):
        stamp = self.updated.get((device_id, port))
        return stamp is not None and datetime.now(UTC) - stamp <= MODULE_INTERVAL * 2

    def detail_is_fresh(self, device_id, key=None):
        stamp = (self.detail_updated.get(device_id) if key is None
                 else self.detail_field_updated.get((device_id, key)))
        if stamp is None:
            return False
        age = datetime.now(UTC) - stamp
        return -timedelta(minutes=1) <= age <= MODULE_INTERVAL * 2

    async def _async_poll(self, inverters):
        now = datetime.now(UTC)
        date = now.astimezone(self.timezone).date().isoformat()
        modules = {key: dict(value) for key, value in self.modules.items()}
        try:
            async with asyncio.timeout(120):
                if self.detailed:
                    await self._async_details(inverters, date)
                for inverter in inverters:
                    device_id = inverter["id"]
                    modules.setdefault(device_id, {})
                    for port in inverter_ports(inverter):
                        try:
                            modules[device_id][port] = await self.client.async_module_values(
                                self.station_id, device_id, port, date
                            )
                            self.updated[(device_id, port)] = datetime.now(UTC)
                        except (HoymilesAuthError, HoymilesRateLimitError):
                            raise
                        except HoymilesConnectionError:
                            continue
        except HoymilesRateLimitError as err:
            self.next_allowed = datetime.now(UTC) + timedelta(seconds=err.retry_after)
        except (HoymilesAuthError, TimeoutError):
            pass  # Live polling handles reauthentication; freshness still expires.
        finally:
            if not self.stopped:
                self.modules = modules
                self.on_update()

    async def _async_details(self, inverters, date):
        known = {item["id"] for item in inverters}
        self.details = {key: dict(value) for key, value in self.details.items() if key in known}
        self.detail_updated = {key: value for key, value in self.detail_updated.items() if key in known}
        self.detail_field_updated = {key: value for key, value in self.detail_field_updated.items() if key[0] in known}
        try:
            snapshot = await self.client.async_module_snapshot(self.station_id, date)
        except (HoymilesAuthError, HoymilesRateLimitError):
            self.details_status = "unavailable"
            raise
        except HoymilesConnectionError:
            self.details_status = "unavailable"
            return
        self._merge_details(snapshot, known, date)
        # Only supplement explicit HMS models, once per existing slow poll.
        # Working/fresh metrics do not cause additional requests.
        missing = [item["id"] for item in inverters
                   if inverter_model(item) != "Hoymiles microinverter"
                   and type(item.get("id")) is int and item["id"] > 0
                   and any(not self.detail_is_fresh(item["id"], key)
                           for key in ("frequency", "temperature", "voltage"))]
        if missing:
            try:
                chart = await self.client.async_micro_details(self.station_id, missing, date)
            except (HoymilesAuthError, HoymilesRateLimitError):
                self.details_status = "unavailable"
                raise
            except HoymilesConnectionError:
                pass
            else:
                self._merge_details(chart, known, date)
        self.details_status = "readable" if any(
            self.detail_is_fresh(identity, key)
            for identity in known for key in ("frequency", "temperature", "voltage")
        ) else "no_data"

    def _merge_details(self, snapshot, known, date):
        if not isinstance(snapshot, dict) or not isinstance(snapshot.get("inverters"), dict):
            return
        for device_id, values in snapshot["inverters"].items():
            if device_id not in known:
                continue
            for key in ("frequency", "temperature", "voltage"):
                value = number(values.get(key))
                time = values.get(f"{key}_time", values.get("time"))
                if value is None or not isinstance(time, str):
                    continue
                stamp = datetime.fromisoformat(f"{date}T{time}:00").replace(
                    tzinfo=self.timezone
                ).astimezone(UTC)
                if stamp > datetime.now(UTC) + timedelta(minutes=1):
                    continue
                previous = self.detail_field_updated.get((device_id, key))
                if previous is not None and stamp < previous:
                    continue
                self.details.setdefault(device_id, {})[key] = value
                self.details[device_id][f"{key}_sample_time"] = stamp.isoformat()
                self.detail_field_updated[(device_id, key)] = stamp
                self.detail_updated[device_id] = max(stamp, self.detail_updated.get(device_id, stamp))
                self.details[device_id]["sample_time"] = self.detail_updated[device_id].isoformat()
