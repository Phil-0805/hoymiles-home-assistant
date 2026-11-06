"""App output-power setting, distinct from configuration 515's upper limit."""

import asyncio
from copy import deepcopy
from datetime import UTC, datetime
import json

from . import device_settings as settings_runtime
from .device_settings import DeviceSettings, setting_integer, settings_equal
from .errors import HoymilesAuthError, HoymilesConnectionError, HoymilesSettingsError


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

    def __init__(self, *args):
        super().__init__(*args, features=("output_power",))
        self.output = None

    async def _read(self, feature, target=None):
        return validate_output_settings(await self.client.async_output_power_settings(self.station_id))

    def _store(self, feature, value):
        self.output = deepcopy(value)
        self.updated[feature] = datetime.now(UTC)
        self.status[feature] = "readable"
        self.last_error.pop(feature, None)

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
                    raise HoymilesConnectionError("Battery controller changed or is ambiguous")
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
                    raise HoymilesConnectionError("Battery controller changed during preflight")
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
