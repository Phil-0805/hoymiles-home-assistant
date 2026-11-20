"""App output-power setting, distinct from configuration 515's upper limit."""

import asyncio
from copy import deepcopy
from datetime import UTC, datetime
import json

from . import device_settings as settings_runtime
from .device_settings import DeviceSettings, setting_integer, settings_equal
from .errors import HoymilesAuthError, HoymilesConnectionError, HoymilesSettingsError
from .inverter import standalone_hms_target


def output_phases(data):
    if isinstance(data, str):
        # Some app responses encode this tiny flat array as JSON text. Keep its
        # decoder bounded without relaxing the HTTP client's object-root rule.
        if len(data) > 128:
            raise HoymilesSettingsError("invalid_output_phases", "Output phase information is oversized")
        try:
            data = json.loads(data)
        except (ValueError, RecursionError):
            raise HoymilesSettingsError("invalid_output_phases", "Invalid output phase information") from None
    if (not isinstance(data, list) or len(data) > 3
            or any(type(phase) is not str or phase not in {"A", "B", "C"} for phase in data)
            or len(set(data)) != len(data)):
        raise HoymilesSettingsError("invalid_output_phases", "Output phase information is unavailable", data)
    return sorted(data)


def validate_output_settings(settings):
    if not isinstance(settings, dict):
        raise HoymilesConnectionError("Output power settings are unavailable")
    phases = output_phases(settings.get("phases"))
    action = 1532 if phases else 84
    if type(settings.get("action")) is not int or settings["action"] != action:
        raise HoymilesConnectionError("Output power action does not match the phase layout")
    keys = {"total", *phases}
    values, limits = settings.get("values"), settings.get("limits")
    if (not isinstance(values, dict) or not isinstance(limits, dict)
            or set(values) != keys or set(limits) != keys):
        raise HoymilesConnectionError("Output power values or limits are incomplete")
    for key in keys:
        # The inspected Android code reads Java Integer values. This bound only
        # validates that representation; the actual maximum must come from data.
        if (type(limits[key]) is not int or not 100 <= limits[key] <= 2**31 - 1
                or type(values[key]) is not int or not 0 <= values[key] <= 2**31 - 1):
            raise HoymilesConnectionError("Output power values or limits are invalid")
    return {"action": action, "phases": phases, "values": dict(values), "limits": dict(limits)}


def parse_output_settings(data, phases):
    phases = output_phases(phases)
    if not isinstance(data, dict):
        raise HoymilesSettingsError("invalid_output_settings", "Output power settings are unavailable", data)
    values = {"total": setting_integer(data.get("out_power_total" if phases else "power"), 2**31 - 1)}
    limits = {"total": setting_integer(data.get("max_power"), 2**31 - 1)}
    for phase in phases:
        values[phase] = setting_integer(data.get(f"out_power_{phase.lower()}"), 2**31 - 1)
        limits[phase] = setting_integer(data.get(f"power_{phase.lower()}"), 2**31 - 1)
    try:
        return validate_output_settings({"action": 1532 if phases else 84,
                                         "phases": phases, "values": values, "limits": limits})
    except HoymilesConnectionError:
        raise HoymilesSettingsError("invalid_output_settings", "Output power values or limits are invalid", data) from None


def output_write_data(settings, value):
    settings = validate_output_settings(settings)
    if type(value) is not int or not 100 <= value <= settings["limits"]["total"]:
        raise HoymilesConnectionError("Output power must be within the freshly reported range")
    if settings["action"] == 84:
        return {"power": value}
    if any(settings["values"][phase] > settings["limits"][phase] for phase in settings["phases"]):
        raise HoymilesConnectionError("A preserved phase setting exceeds its freshly reported limit")
    return {"type": 0, "power_total": value,
            **{f"power_{phase.lower()}": settings["values"][phase] for phase in settings["phases"]}}


class OutputPowerSettings(DeviceSettings):
    """Reuse scheduled reads and cooldowns; preserve current phase settings."""

    def __init__(self, *args, get_inverters=None, get_live_state=None):
        super().__init__(*args, features=("output_power",))
        self.output = None
        self.confirmed_target = None
        self.get_inverters = get_inverters or (lambda: [])
        self.get_live_state = get_live_state or (lambda: None)
        self._rejected_read_target = None

    @property
    def polling_paused(self):
        # No clock/zero-power heuristic, and never extend this gate to storage.
        target = standalone_hms_target(self.get_tree(), self.get_inverters())
        state = self.get_live_state()
        return (target is not None and (state == "offline" or
                state == "unavailable" and self._rejected_read_target == {
                    "station_id": self.station_id, **target}))

    def available(self, feature):
        return not self.polling_paused and super().available(feature)

    def _defer_read(self, feature):
        if self.polling_paused:
            self.status[feature] = "waiting_for_live"
            self._clear_read_retry(feature)
            return True
        return False

    def start(self):
        if not self.enabled or self.stopped or not self.may_write():
            return None
        previous = self.status.get("output_power")
        if self._defer_read("output_power"):
            if previous != "waiting_for_live":
                self.on_update()
            return None
        if previous == "waiting_for_live":
            self.status["output_power"] = "pending"
            if not self.stopped:
                self.on_update()
        # Keep the previous deadline: recovery must not accelerate polling.
        return super().start()

    async def async_refresh(self):
        if self.enabled and not self.stopped and self.may_write() and self._defer_read("output_power"):
            self.on_update()
            return False
        return await super().async_refresh()

    def _target(self, feature):
        tree = self.get_tree()
        standalone = standalone_hms_target(tree, self.get_inverters())
        if standalone is not None:
            return {"station_id": self.station_id, **standalone}
        return super()._target(feature)

    async def _read(self, feature, target=None):
        read_target = deepcopy(target if target is not None else self._target(feature))
        try:
            return validate_output_settings(await self.client.async_output_power_settings(self.station_id))
        except HoymilesConnectionError as error:
            # Missing Live alone does not prove settings are unreadable. Bind
            # an actual READ rejection to the unchanged target, never a write
            # error or a different device selected while this read was running.
            if (getattr(error, "reason", None) == "cloud_rejected"
                    and read_target is not None and "inverter" in read_target
                    and read_target == self._target(feature)):
                self._rejected_read_target = read_target
            raise

    def _store(self, feature, value):
        self._rejected_read_target = None
        self.output = deepcopy(value)
        self.confirmed_target = deepcopy(self.target)
        self._mark_readable(feature)

    def display_status(self):
        """A confirmed setting can outlive a failed read, bound to its target.

        This is presentation only. Every change still runs the existing locked
        fresh-read preflight and full readback; a retained range grants no write.
        """
        if (not self.enabled or self.stopped or not self.may_write()
                or self.output is None or self.confirmed_target is None
                or "output_power" not in self.updated
                or self.target != self.confirmed_target
                or self._target("output_power") != self.confirmed_target):
            return "unavailable"
        return "current" if self.available("output_power") else "last_confirmed"

    def confirmed_age_seconds(self):
        stamp = self.updated.get("output_power")
        if stamp is None:
            return None
        return max(0, min(2**31 - 1, int((datetime.now(UTC) - stamp).total_seconds())))

    async def async_set_power(self, value):
        if type(value) is not int or not 100 <= value <= 2**31 - 1:
            raise HoymilesConnectionError("Output power must be a whole watt value of at least 100 W")
        feature = "output_power"
        try:
            async with self.lock, asyncio.timeout(120):
                self._check_controls()
                if self.output is None:
                    raise HoymilesConnectionError("Output power settings are unavailable")
                target = self._target(feature)
                if target is None or target != self.target:
                    raise HoymilesConnectionError("Output control target changed or is ambiguous")
                cached = self.output
                fresh = await self._read(feature)
                self._store(feature, fresh)
                if (fresh["action"], fresh["phases"]) != (cached["action"], cached["phases"]):
                    raise HoymilesConnectionError("Output phase layout changed during preflight")
                output_write_data(fresh, value)
                expected = deepcopy(fresh)
                expected["values"]["total"] = value
                if settings_equal(fresh, expected):
                    return
                self._check_controls()
                if self._target(feature) != target:
                    raise HoymilesConnectionError("Output control target changed during preflight")
                await self.client.async_write_output_power_settings(self.station_id, fresh, value)
                for attempt in range(settings_runtime.READBACK_ATTEMPTS):
                    if self.stopped:
                        raise HoymilesConnectionError("Output power controls were unloaded")
                    actual = await self._read(feature)
                    self._store(feature, actual)
                    if settings_equal(actual, expected):
                        return
                    if attempt + 1 < settings_runtime.READBACK_ATTEMPTS:
                        await asyncio.sleep(settings_runtime.READBACK_DELAY)
                raise HoymilesConnectionError("Device did not confirm the requested output power")
        except (HoymilesConnectionError, HoymilesAuthError, TimeoutError) as err:
            self._failure(feature, err)
            if isinstance(err, TimeoutError):
                raise HoymilesConnectionError("Output power operation timed out") from None
            raise
        finally:
            if not self.stopped:
                self.on_update()
