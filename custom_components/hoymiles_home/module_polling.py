"""Independent slow telemetry polling, with its own lifecycle and freshness."""

import asyncio
import re
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
        self.module_field_updated = {}
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

    def is_fresh(self, device_id, port, quota=None):
        stamp = (self.updated.get((device_id, port)) if quota is None
                 else self.module_field_updated.get((device_id, port, quota)))
        return (not self.stopped and stamp is not None
                and -timedelta(minutes=1) <= datetime.now(UTC) - stamp <= MODULE_INTERVAL * 2)

    def detail_is_fresh(self, device_id, key=None):
        stamp = (self.detail_updated.get(device_id) if key is None
                 else self.detail_field_updated.get((device_id, key)))
        if self.stopped or stamp is None:
            return False
        age = datetime.now(UTC) - stamp
        return -timedelta(minutes=1) <= age <= MODULE_INTERVAL * 2

    async def _async_poll(self, inverters):
        now = datetime.now(UTC)
        date = now.astimezone(self.timezone).date().isoformat()
        ports = {item["id"]: set(inverter_ports(item)) for item in inverters}
        modules = {identity: {port: dict(values) for port, values in data.items() if port in ports[identity]}
                   for identity, data in self.modules.items() if identity in ports}
        self.updated = {key: stamp for key, stamp in self.updated.items()
                        if key[0] in ports and key[1] in ports[key[0]]}
        self.module_field_updated = {key: stamp for key, stamp in self.module_field_updated.items()
                                    if key[0] in ports and key[1] in ports[key[0]]}
        try:
            async with asyncio.timeout(120):
                if self.detailed:
                    await self._async_details(inverters, date)
                for inverter in inverters:
                    device_id = inverter["id"]
                    modules.setdefault(device_id, {})
                    for port in inverter_ports(inverter):
                        modules[device_id].setdefault(port, {})
                        try:
                            values = await self.client.async_module_values(
                                self.station_id, device_id, port, date, latest_time=self._chart_cutoff(date)
                            )
                            self._merge_module(modules, device_id, port, values, date)
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

    def _chart_cutoff(self, date):
        now = datetime.now(UTC).astimezone(self.timezone)
        return "23:59" if date < now.date().isoformat() else now.strftime("%H:%M")

    def _sample_stamp(self, date, time):
        if not isinstance(time, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", time):
            return None
        try:
            wall = datetime.fromisoformat(f"{date}T{time}:00")
        except ValueError:
            return None
        local = wall.replace(tzinfo=self.timezone)
        # A wall-clock chart cannot disambiguate a repeated or missing DST hour.
        if local.utcoffset() != local.replace(fold=1).utcoffset():
            return None
        stamp = local.astimezone(UTC)
        return stamp if stamp <= datetime.now(UTC) + timedelta(minutes=1) else None

    def _merge_module(self, modules, identity, port, values, date):
        if not isinstance(values, dict):
            return
        times = values.get("_sample_times", {})
        if not isinstance(times, dict):
            return
        for key in ("MODULE_POWER", "MODULE_V", "MODULE_I"):
            value = number(values.get(key))
            stamp = self._sample_stamp(date, times.get(key))
            previous = self.module_field_updated.get((identity, port, key))
            if value is None or stamp is None or (previous is not None and stamp < previous):
                continue
            modules.setdefault(identity, {}).setdefault(port, {})[key] = value
            self.module_field_updated[(identity, port, key)] = stamp
            self.updated[(identity, port)] = max(stamp, self.updated.get((identity, port), stamp))

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
                chart = await self.client.async_micro_details(
                    self.station_id, missing, date, latest_time=self._chart_cutoff(date))
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
                stamp = self._sample_stamp(date, time)
                if value is None or stamp is None:
                    continue
                previous = self.detail_field_updated.get((device_id, key))
                if previous is not None and stamp < previous:
                    continue
                self.details.setdefault(device_id, {})[key] = value
                self.details[device_id][f"{key}_sample_time"] = stamp.isoformat()
                self.detail_field_updated[(device_id, key)] = stamp
                self.detail_updated[device_id] = max(stamp, self.detail_updated.get(device_id, stamp))
                self.details[device_id]["sample_time"] = self.detail_updated[device_id].isoformat()
