"""Opt-in heating and light/display settings with verified readback."""

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
import re

from .errors import HoymilesAuthError, HoymilesConnectionError, HoymilesRateLimitError

SETTINGS_INTERVAL = timedelta(minutes=30)
MANUAL_COOLDOWN = timedelta(seconds=30)
READBACK_ATTEMPTS = 3
READBACK_DELAY = 3
DISPLAY_FIELDS = {"ldb": 255, "sot": 3600}
STRIP_FIELDS = {"r": 255, "g": 255, "b": 255, "slb": 255, "slot": 3600}
LIGHT_FIELDS = {**DISPLAY_FIELDS, **STRIP_FIELDS}


def light_target(tree):
    """Select one explicit AC battery controller, never guess among devices."""
    found = {}

    def visit(value):
        if isinstance(value, list):
            for child in value:
                visit(child)
        elif isinstance(value, dict):
            sn, dtu = value.get("sn"), value.get("dtu_sn") or value.get("sn")
            if (type(value.get("type")) is int and value["type"] == 12
                    and isinstance(sn, str) and re.fullmatch(r"[0-9A-Fa-f]{12,24}", sn)
                    and isinstance(dtu, str) and re.fullmatch(r"[0-9A-Fa-f]{12,24}", dtu)):
                found[(sn, dtu)] = {"dev_sn": sn, "dtu_sn": dtu}
            for child in value.values():
                visit(child)

    visit(tree)
    return next(iter(found.values())) if len(found) == 1 else None


def parse_heating(data):
    """This is permission to heat, not proof that the heater is active."""
    if not isinstance(data, dict) or type(data.get("enable")) is not int or data["enable"] not in (0, 1):
        raise HoymilesConnectionError("Invalid battery heating settings")
    return {"enable": data["enable"]}


def parse_lighting(data, target):
    """Keep the full private snapshot; expose only validated known fields."""
    if not isinstance(data, dict) or len(data) > 64:
        raise HoymilesConnectionError("Invalid light/display settings")
    try:
        if len(json.dumps(data, allow_nan=False)) > 16384:
            raise ValueError("oversized settings")
    except (ValueError, TypeError, RecursionError):
        raise HoymilesConnectionError("Invalid light/display settings") from None
    values = {}
    for key, maximum in LIGHT_FIELDS.items():
        value = data.get(key)
        if key in data and (type(value) is not int or not 0 <= value <= maximum):
            raise HoymilesConnectionError("Invalid light/display value")
        if type(value) is int and 0 <= value <= maximum:
            values[key] = value
    if not DISPLAY_FIELDS.keys() <= values.keys():
        raise HoymilesConnectionError("Display settings are incomplete")
    # The vendor web UI suppresses strip controls for these series. This is a
    # restriction on controls, not a model identification from the serial.
    if target["dev_sn"].startswith(("2805", "2806")) or not STRIP_FIELDS.keys() <= values.keys():
        values = {key: value for key, value in values.items() if key in DISPLAY_FIELDS}
    return {"values": values, "snapshot": deepcopy(data)}


def light_update(settings, updates):
    if (not isinstance(updates, dict) or not updates
            or not updates.keys() <= settings["values"].keys()
            or not updates.keys() <= LIGHT_FIELDS.keys()):
        raise HoymilesConnectionError("Unsupported light/display change")
    for key, value in updates.items():
        if type(value) is not int or not 0 <= value <= LIGHT_FIELDS[key]:
            raise HoymilesConnectionError("Light/display value is outside its supported range")
    snapshot = deepcopy(settings["snapshot"])
    snapshot.update(updates)
    return snapshot


def settings_equal(actual, expected):
    """Check complete settings, preserving numeric/boolean distinctions."""
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(settings_equal(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(settings_equal(a, b) for a, b in zip(actual, expected))
    return actual == expected


class DeviceSettings:
    """Optional settings reads, serialized writes and no optimistic state."""

    def __init__(self, hass, client, station_id, enabled, get_tree, may_write, on_update):
        self.hass, self.client, self.station_id = hass, client, station_id
        self.enabled, self.get_tree, self.may_write, self.on_update = enabled, get_tree, may_write, on_update
        self.heating, self.lighting, self.target = None, None, None
        self.status = {"heating": "pending", "lighting": "pending"} if enabled else {"heating": "disabled", "lighting": "disabled"}
        self.updated = {}
        self.lock = asyncio.Lock()
        self.task = None
        self.stopped = False
        self.last_attempt = self.next_allowed = datetime.min.replace(tzinfo=UTC)

    def available(self, feature):
        stamp = self.updated.get(feature)
        return (self.enabled and not self.stopped and self.status[feature] == "readable"
                and stamp is not None and timedelta(0) <= datetime.now(UTC) - stamp <= SETTINGS_INTERVAL * 2)

    def _check_controls(self):
        if not self.enabled or self.stopped or not self.may_write():
            raise HoymilesConnectionError("Device controls are disabled")

    def start(self):
        if not self.enabled or self.stopped or datetime.now(UTC) < self.next_allowed:
            return None
        return self._start()

    def _start(self):
        if self.task is None or self.task.done():
            self.last_attempt = datetime.now(UTC)
            self.next_allowed = max(self.next_allowed, self.last_attempt + SETTINGS_INTERVAL)
            self.task = self.hass.async_create_background_task(self._async_refresh(), "hoymiles_home device settings")
        return self.task

    async def async_refresh(self):
        if not self.enabled or self.stopped:
            return False
        running = self.task is not None and not self.task.done()
        if not running and (datetime.now(UTC) - self.last_attempt < MANUAL_COOLDOWN
                            or datetime.now(UTC) < getattr(self, "paused_until", datetime.min.replace(tzinfo=UTC))):
            return False
        await asyncio.shield(self._start())
        return True

    def _store(self, feature, value):
        if feature == "heating":
            self.heating = value
        else:
            self.lighting = value
        self.updated[feature] = datetime.now(UTC)
        self.status[feature] = "readable"

    def _failure(self, feature, error):
        self.status[feature] = "unavailable"
        if isinstance(error, HoymilesRateLimitError):
            self.paused_until = datetime.now(UTC) + timedelta(seconds=error.retry_after)
            self.next_allowed = max(self.next_allowed, self.paused_until)

    async def _read(self, feature, target=None):
        if feature == "heating":
            return parse_heating(await self.client.async_heating_settings(self.station_id))
        return parse_lighting(await self.client.async_light_display_settings(self.station_id, target), target)

    async def _async_refresh(self):
        try:
            async with self.lock, asyncio.timeout(120):
                if self.stopped:
                    return
                for feature in ("heating", "lighting"):
                    target = light_target(self.get_tree()) if feature == "lighting" else None
                    if feature == "lighting":
                        self.target = target
                        if target is None:
                            self.status[feature] = "no_unique_target"
                            continue
                    try:
                        self._store(feature, await self._read(feature, target))
                    except (HoymilesAuthError, HoymilesConnectionError, TimeoutError) as err:
                        self._failure(feature, err)
                        if isinstance(err, (HoymilesAuthError, HoymilesRateLimitError)):
                            return
        except TimeoutError as err:
            for feature in self.status:
                self._failure(feature, err)
        finally:
            if not self.stopped:
                self.on_update()

    async def async_set_heating(self, enabled):
        if type(enabled) is not bool:
            raise HoymilesConnectionError("Invalid heating permission")
        await self._async_write("heating", {"enable": int(enabled)})

    async def async_set_lighting(self, updates, *, turn_on=False):
        # Validate service values before any cloud request; recheck capability
        # against the fresh snapshot under the lock as well.
        if self.lighting is None:
            raise HoymilesConnectionError("Light/display settings are unavailable")
        updates = deepcopy(updates)
        if updates or not turn_on:
            light_update(self.lighting, updates)
        elif not isinstance(updates, dict):
            raise HoymilesConnectionError("Unsupported light/display change")
        if turn_on and not STRIP_FIELDS.keys() <= self.lighting["values"].keys():
            raise HoymilesConnectionError("Indicator strip is unavailable")
        await self._async_write("lighting", updates, turn_on=turn_on)

    async def _async_write(self, feature, updates, *, turn_on=False):
        try:
            async with self.lock, asyncio.timeout(120):
                self._check_controls()
                target = None
                if feature == "lighting":
                    target = light_target(self.get_tree())
                    if target is None or target != self.target:
                        raise HoymilesConnectionError("Battery controller changed or is ambiguous")
                fresh = await self._read(feature, target)
                self._store(feature, fresh)
                if turn_on and "slb" not in updates:
                    updates = {**updates, "slb": fresh["values"].get("slb") or 255}
                expected = updates if feature == "heating" else light_update(fresh, updates)
                if feature == "heating" and fresh == expected:
                    return
                if feature == "lighting" and settings_equal(fresh["snapshot"], expected):
                    return
                self._check_controls()
                if feature == "lighting" and light_target(self.get_tree()) != target:
                    raise HoymilesConnectionError("Battery controller changed during preflight")
                if feature == "heating":
                    await self.client.async_write_heating_settings(self.station_id, expected["enable"])
                else:
                    await self.client.async_write_light_display_settings(self.station_id, target, expected)
                for attempt in range(READBACK_ATTEMPTS):
                    if self.stopped:
                        raise HoymilesConnectionError("Device controls were unloaded")
                    actual = await self._read(feature, target)
                    self._store(feature, actual)
                    snapshot = actual if feature == "heating" else actual["snapshot"]
                    if settings_equal(snapshot, expected):
                        return
                    if attempt + 1 < READBACK_ATTEMPTS:
                        await asyncio.sleep(READBACK_DELAY)
                raise HoymilesConnectionError("Device did not confirm the requested settings")
        except (HoymilesConnectionError, HoymilesAuthError, TimeoutError) as err:
            self._failure(feature, err)
            if isinstance(err, TimeoutError):
                raise HoymilesConnectionError("Device settings operation timed out") from None
            raise
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
