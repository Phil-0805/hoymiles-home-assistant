"""Independent slow telemetry polling, with its own lifecycle and freshness."""

import asyncio
import re
from datetime import UTC, datetime, timedelta

from .errors import (
    HoymilesAuthError, HoymilesConnectionError, HoymilesRateLimitError, TELEMETRY_READ_REASONS,
)
from .const import MODULE_INTERVAL
from .inverter import inverter_ports, inverter_model
from .telemetry import number

# Chart labels can lag receipt by more than one polling cycle. Keep source time
# separate from observed progress: duplicate replies must not renew freshness.
# These are client policies, not manufacturer quotas or timestamp guarantees.
SOURCE_MAX_AGE = MODULE_INTERVAL * 4
PROGRESS_MAX_AGE = MODULE_INTERVAL * 2


class ModulePoller:
    """Keep slow chart requests out of the live power refresh path."""

    def __init__(self, hass, client, station_id, timezone, detailed, on_update):
        self.hass, self.client, self.station_id = hass, client, station_id
        self.timezone, self.detailed, self.on_update = timezone, detailed, on_update
        self.modules, self.updated, self.details, self.detail_updated = {}, {}, {}, {}
        self.detail_field_updated = {}
        self.module_field_updated = {}
        self.detail_field_progress = {}
        self.module_field_progress = {}
        self.module_read_status = {}
        self.detail_read_status = {"snapshot": "not_requested", "micro_chart": "not_requested"}
        self.task = None
        self.stopped = False
        self.next_allowed = datetime.min.replace(tzinfo=UTC)
        self.details_status = "disabled" if not detailed else "pending"

    @property
    def details_status(self):
        if self._details_status == "readable" and not any(
            self.detail_is_fresh(identity, key) for identity, key in self.detail_field_updated
        ):
            return "no_data"
        return self._details_status

    @details_status.setter
    def details_status(self, value):
        self._details_status = value

    def _sample_state(self, stamp, progress, now=None):
        if stamp is None:
            return "missing"
        if self.stopped:
            return "stopped"
        now = now or datetime.now(UTC)
        source_age = now - stamp
        progress_age = now - (progress or stamp)
        if min(source_age, progress_age) < -timedelta(minutes=1):
            return "future"
        if source_age < SOURCE_MAX_AGE and progress_age < PROGRESS_MAX_AGE:
            return "fresh"
        return "stale"

    @staticmethod
    def _read_failure(error):
        if isinstance(error, HoymilesAuthError):
            return "authentication"
        if isinstance(error, HoymilesRateLimitError):
            return "rate_limited"
        if isinstance(error, TimeoutError):
            return "timeout"
        reason = getattr(error, "reason", None)
        return reason if type(reason) is str and reason in TELEMETRY_READ_REASONS else "connection"

    def diagnostics(self, device_id, ports):
        """Expose field ages and fixed read outcomes, never chart data or identities."""
        now = datetime.now(UTC)

        def sample(stamp, progress):
            if stamp is None:
                return {"status": "missing", "age_seconds": None, "progress_age_seconds": None}
            age = (now - stamp).total_seconds()
            progress_age = (now - (progress or stamp)).total_seconds()
            return {"status": self._sample_state(stamp, progress, now),
                    "age_seconds": max(-2**31, min(2**31 - 1, int(age))),
                    "progress_age_seconds": max(-2**31, min(2**31 - 1, int(progress_age)))}

        return {
            "source_max_age_seconds": int(SOURCE_MAX_AGE.total_seconds()),
            "progress_max_age_seconds": int(PROGRESS_MAX_AGE.total_seconds()),
            "pv_inputs": [{
                "port": port,
                "read_status": self.module_read_status.get((device_id, port), "not_requested"),
                "fields": {name: sample(self.module_field_updated.get((device_id, port, quota)),
                                        self.module_field_progress.get((device_id, port, quota)))
                           for name, quota in (("power", "MODULE_POWER"), ("voltage", "MODULE_V"),
                                               ("current", "MODULE_I"))},
            } for port in ports],
            "detail_reads": dict(self.detail_read_status),
            "detail_fields": {key: sample(self.detail_field_updated.get((device_id, key)),
                                          self.detail_field_progress.get((device_id, key)))
                              for key in ("temperature", "frequency", "voltage")},
        }

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
        if quota is None and any(key[:2] == (device_id, port) for key in self.module_field_updated):
            return any(self.is_fresh(device_id, port, key[2]) for key in self.module_field_updated
                       if key[:2] == (device_id, port))
        stamp = (self.updated.get((device_id, port)) if quota is None
                 else self.module_field_updated.get((device_id, port, quota)))
        return self._sample_state(stamp, self.module_field_progress.get((device_id, port, quota))) == "fresh"

    def detail_is_fresh(self, device_id, key=None):
        if key is None and any(identity == device_id for identity, _ in self.detail_field_updated):
            return any(self.detail_is_fresh(device_id, field) for identity, field in self.detail_field_updated
                       if identity == device_id)
        stamp = (self.detail_updated.get(device_id) if key is None
                 else self.detail_field_updated.get((device_id, key)))
        return self._sample_state(stamp, self.detail_field_progress.get((device_id, key))) == "fresh"

    async def _async_poll(self, inverters):
        now = datetime.now(UTC)
        date = now.astimezone(self.timezone).date().isoformat()
        ports = {item["id"]: set(inverter_ports(item)) for item in inverters}
        modules = {identity: {port: dict(values) for port, values in data.items() if port in ports[identity]}
                   for identity, data in self.modules.items() if identity in ports}
        updated = {key: stamp for key, stamp in self.updated.items()
                   if key[0] in ports and key[1] in ports[key[0]]}
        field_updated = {key: stamp for key, stamp in self.module_field_updated.items()
                         if key[0] in ports and key[1] in ports[key[0]]}
        field_progress = {key: stamp for key, stamp in self.module_field_progress.items()
                          if key in field_updated}
        self.module_read_status = {key: status for key, status in self.module_read_status.items()
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
                            self.module_read_status[(device_id, port)] = "pending"
                            values = await self.client.async_module_values(
                                self.station_id, device_id, port, date, latest_time=self._chart_cutoff(date)
                            )
                            self._merge_module(modules, device_id, port, values, date,
                                               field_updated=field_updated, field_progress=field_progress,
                                               updated=updated)
                            self.module_read_status[(device_id, port)] = "success"
                        except (HoymilesAuthError, HoymilesRateLimitError) as err:
                            self.module_read_status[(device_id, port)] = self._read_failure(err)
                            raise
                        except HoymilesConnectionError as err:
                            self.module_read_status[(device_id, port)] = self._read_failure(err)
                            continue
        except HoymilesRateLimitError as err:
            self.next_allowed = datetime.now(UTC) + timedelta(seconds=err.retry_after)
        except TimeoutError:
            self.module_read_status = {key: "timeout" if status == "pending" else status
                                       for key, status in self.module_read_status.items()}
            self.detail_read_status = {key: "timeout" if status == "pending" else status
                                       for key, status in self.detail_read_status.items()}
        except HoymilesAuthError:
            pass  # Live polling handles reauthentication; freshness still expires.
        finally:
            if not self.stopped:
                # Commit values and their clocks together, including partial
                # success on timeout. Live ticks must not see old values with
                # metadata from an in-flight replacement batch.
                self.modules, self.updated = modules, updated
                self.module_field_updated, self.module_field_progress = field_updated, field_progress
                self.on_update()

    def _chart_cutoff(self, date):
        # Match _sample_stamp/detail_is_fresh's existing one-minute tolerance.
        # Clamp at the requested day's end instead of wrapping to 00:00.
        cutoff = (datetime.now(UTC) + timedelta(minutes=1)).astimezone(self.timezone)
        return "23:59" if date < cutoff.date().isoformat() else cutoff.strftime("%H:%M")

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

    def _merge_module(self, modules, identity, port, values, date, *,
                      field_updated=None, field_progress=None, updated=None):
        if not isinstance(values, dict):
            return
        times = values.get("_sample_times", {})
        if not isinstance(times, dict):
            return
        field_updated = self.module_field_updated if field_updated is None else field_updated
        field_progress = self.module_field_progress if field_progress is None else field_progress
        updated = self.updated if updated is None else updated
        for key in ("MODULE_POWER", "MODULE_V", "MODULE_I"):
            value = number(values.get(key))
            stamp = self._sample_stamp(date, times.get(key))
            previous = field_updated.get((identity, port, key))
            if value is None or stamp is None or (previous is not None and stamp < previous):
                continue
            old = modules.get(identity, {}).get(port, {}).get(key)
            if previous is None or stamp > previous or value != old:
                field_progress[(identity, port, key)] = datetime.now(UTC)
            modules.setdefault(identity, {}).setdefault(port, {})[key] = value
            field_updated[(identity, port, key)] = stamp
            updated[(identity, port)] = max(stamp, updated.get((identity, port), stamp))

    async def _async_details(self, inverters, date):
        known = {item["id"] for item in inverters}
        self.details = {key: dict(value) for key, value in self.details.items() if key in known}
        self.detail_updated = {key: value for key, value in self.detail_updated.items() if key in known}
        self.detail_field_updated = {key: value for key, value in self.detail_field_updated.items() if key[0] in known}
        self.detail_field_progress = {key: stamp for key, stamp in self.detail_field_progress.items()
                                     if key in self.detail_field_updated}
        self.detail_read_status = {"snapshot": "pending", "micro_chart": "not_requested"}
        try:
            snapshot = await self.client.async_module_snapshot(self.station_id, date)
        except (HoymilesAuthError, HoymilesRateLimitError) as err:
            self.detail_read_status["snapshot"] = self._read_failure(err)
            self.details_status = "unavailable"
            raise
        except HoymilesConnectionError as err:
            self.detail_read_status["snapshot"] = self._read_failure(err)
            self.details_status = "unavailable"
            return
        self.detail_read_status["snapshot"] = "success"
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
                self.detail_read_status["micro_chart"] = "pending"
                chart = await self.client.async_micro_details(
                    self.station_id, missing, date, latest_time=self._chart_cutoff(date))
            except (HoymilesAuthError, HoymilesRateLimitError) as err:
                self.detail_read_status["micro_chart"] = self._read_failure(err)
                self.details_status = "unavailable"
                raise
            except HoymilesConnectionError as err:
                self.detail_read_status["micro_chart"] = self._read_failure(err)
            else:
                self.detail_read_status["micro_chart"] = "success"
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
                old = self.details.get(device_id, {}).get(key)
                if previous is None or stamp > previous or value != old:
                    self.detail_field_progress[(device_id, key)] = datetime.now(UTC)
                self.details.setdefault(device_id, {})[key] = value
                self.details[device_id][f"{key}_sample_time"] = stamp.isoformat()
                self.detail_field_updated[(device_id, key)] = stamp
                self.detail_updated[device_id] = max(stamp, self.detail_updated.get(device_id, stamp))
                self.details[device_id]["sample_time"] = self.detail_updated[device_id].isoformat()
