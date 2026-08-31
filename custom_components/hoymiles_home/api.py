"""Asynchronous S-Miles Home API client."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout
from argon2.low_level import Type, hash_secret_raw

from .battery import (
    BatterySettingsError,
    battery_setting_command_data,
    battery_setting_targets,
    parse_battery_settings,
)
from .const import (
    AUTH_BASE_URL,
    BATTERY_SETTINGS_ACTION,
    BATTERY_SETTINGS_MAX_POLLS,
    BATTERY_SETTINGS_POLL_INTERVAL,
    DATA_BASE_URL,
    TOKEN_LIFETIME,
    USER_AGENT,
)
from .protobuf import latest_values


class HoymilesError(Exception):
    """Base API error."""


class HoymilesAuthError(HoymilesError):
    """Authentication error."""


class HoymilesConnectionError(HoymilesError):
    """Connection or response error."""


class HoymilesHomeClient:
    """Client for the consumer S-Miles Home API."""

    def __init__(self, session: ClientSession, email: str, password: str) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._token: str | None = None
        self._token_expires = datetime.min.replace(tzinfo=UTC)
        self._live_uri: str | None = None
        self._lock = asyncio.Lock()

    @property
    def headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Charset": "UTF-8",
            "language": "en_us",
            "User-Agent": USER_AGENT,
        }
        if self._token:
            headers["Authorization"] = self._token
        return headers

    async def _json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            async with self._session.post(
                url, json=payload, headers=self.headers, timeout=ClientTimeout(total=30)
            ) as response:
                response.raise_for_status()
                data = await response.json(content_type=None)
        except (ClientError, TimeoutError, ValueError) as err:
            raise HoymilesConnectionError(str(err)) from err
        if not isinstance(data, dict):
            raise HoymilesConnectionError("Unexpected API response")
        return data

    @staticmethod
    def _unwrap(response: dict[str, Any]) -> Any:
        if str(response.get("status")) not in {"0", "100"}:
            message = str(response.get("message") or "Hoymiles API rejected request")
            if "login" in message.lower() or "token" in message.lower():
                raise HoymilesAuthError(message)
            raise HoymilesConnectionError(message)
        return response.get("data")

    async def async_login(self) -> None:
        """Authenticate using the app-compatible Argon2id challenge."""
        async with self._lock:
            pre = await self._json(
                f"{AUTH_BASE_URL}/iam/pub/3/auth/pre-insp", {"u": self._email}
            )
            data = self._unwrap(pre) or {}
            try:
                salt = bytes.fromhex(data["a"])
                nonce = data["n"]
            except (KeyError, TypeError, ValueError) as err:
                raise HoymilesAuthError("Incomplete pre-inspection response") from err
            challenge = hash_secret_raw(
                self._password.encode(), salt, 3, 32768, 1, 32, Type.ID
            ).hex()
            login = await self._json(
                f"{AUTH_BASE_URL}/iam/pub/3/auth/login",
                {"u": self._email, "ch": challenge, "n": nonce},
            )
            token = (self._unwrap(login) or {}).get("token")
            if not token:
                raise HoymilesAuthError("Login returned no token")
            self._token = token
            self._token_expires = datetime.now(UTC) + TOKEN_LIFETIME
            self._live_uri = None

    async def async_ensure_login(self) -> None:
        if not self._token or datetime.now(UTC) >= self._token_expires:
            await self.async_login()

    async def async_device_tree(self, station_id: int) -> list[dict[str, Any]]:
        await self.async_ensure_login()
        response = await self._json(
            f"{DATA_BASE_URL}/pvmc/api/0/station/select_device_c", {"sid": station_id}
        )
        return self._unwrap(response) or []

    async def async_station_realtime(self, station_id: int) -> dict[str, Any]:
        await self.async_ensure_login()
        response = await self._json(
            f"{DATA_BASE_URL}/pvmc/api/0/station_data/count_station_real_data_c",
            {"sid": station_id},
        )
        return self._unwrap(response) or {}

    async def _get_live_uri(self, station_id: int) -> str:
        response = await self._json(
            f"{DATA_BASE_URL}/pvmc/api/0/station/get_sd_uri_c", {"sid": station_id}
        )
        uri = (self._unwrap(response) or {}).get("uri")
        if not uri:
            raise HoymilesConnectionError("Live API returned no URI")
        return uri

    async def async_live(self, station_id: int) -> dict[str, Any]:
        await self.async_ensure_login()
        for _attempt in range(2):
            if not self._live_uri:
                self._live_uri = await self._get_live_uri(station_id)
            response = await self._json(self._live_uri, {"sid": station_id, "m": 0})
            # The realtime server returns the live values inside the regular
            # {status, data} envelope. The working Node-RED client unwraps that
            # envelope in postUrl(), so accept both forms here for resilience.
            payload = self._unwrap(response) if "status" in response else response
            if isinstance(payload, dict) and "flow" in payload:
                return payload
            self._live_uri = None
        raise HoymilesConnectionError("Live URI expired")

    async def async_module_values(
        self, station_id: int, device_id: int, port: int, date: str
    ) -> dict[str, float | None]:
        await self.async_ensure_login()
        try:
            async with self._session.post(
                f"{DATA_BASE_URL}/pvmc/api/0/module_data/count_by_day_c",
                json={
                    "sid": station_id,
                    "date": date,
                    "mi_list": [{"id": device_id, "port": port}],
                    "quota": ["MODULE_POWER", "MODULE_V", "MODULE_I"],
                },
                headers=self.headers,
                timeout=ClientTimeout(total=30),
            ) as response:
                response.raise_for_status()
                raw = await response.read()
        except (ClientError, TimeoutError) as err:
            raise HoymilesConnectionError(str(err)) from err
        if raw.startswith(b"{"):
            raise HoymilesConnectionError(raw.decode(errors="replace")[:500])
        return latest_values(raw)

    async def _async_battery_settings_request(
        self, payload: dict[str, Any], request_method: str
    ) -> dict[str, Any]:
        """Submit and poll one read-only action-1013 request."""
        response = await self._json(
            f"{DATA_BASE_URL}/pvm-ctl/api/0/dev/setting/read",
            payload,
        )
        result = self._unwrap(response)

        if isinstance(result, (str, int)):
            result = await self._async_poll_battery_settings_job(str(result))

        try:
            parsed = parse_battery_settings(result)
            parsed["request_method"] = request_method
            return parsed
        except BatterySettingsError as err:
            raise HoymilesConnectionError(str(err)) from err

    async def _async_poll_battery_settings_job(
        self, job_id: str
    ) -> dict[str, Any]:
        """Poll an asynchronous battery settings command."""
        for _attempt in range(BATTERY_SETTINGS_MAX_POLLS):
            await asyncio.sleep(BATTERY_SETTINGS_POLL_INTERVAL)
            response = await self._json(
                f"{DATA_BASE_URL}/pvm-ctl/api/0/dev/setting/status",
                {"id": job_id},
            )
            status = self._unwrap(response)
            if isinstance(status, dict) and status.get("code") == 2:
                continue
            if not isinstance(status, dict):
                raise HoymilesConnectionError(
                    "Battery settings returned an invalid status"
                )
            return status
        raise HoymilesConnectionError("Battery settings request timed out")

    async def _async_write_battery_settings_request(
        self, payload: dict[str, Any]
    ) -> None:
        """Submit and verify one action-1013 write request."""
        response = await self._json(
            f"{DATA_BASE_URL}/pvm-ctl/api/0/dev/setting/write",
            payload,
        )
        result = self._unwrap(response)
        if not isinstance(result, (str, int)):
            raise HoymilesConnectionError(
                "Battery settings write returned no command id"
            )
        status = await self._async_poll_battery_settings_job(str(result))
        if status.get("code") != 0:
            message = status.get("message") or status.get("err_code")
            raise HoymilesConnectionError(
                str(message or f"Battery settings write returned {status.get('code')}")
            )

    async def async_battery_settings(self, station_id: int) -> dict[str, Any]:
        """Read battery settings, with a HiBattery-addressed fallback."""
        await self.async_ensure_login()
        station_payload = {
            "action": BATTERY_SETTINGS_ACTION,
            "data": {"sid": station_id},
        }
        try:
            return await self._async_battery_settings_request(
                station_payload, "station"
            )
        except HoymilesConnectionError as err:
            if "device list is empty" not in str(err).lower():
                raise
            station_error = err

        errors = [f"station request: {station_error}"]
        targets = battery_setting_targets(await self.async_device_tree(station_id))
        if not targets:
            raise HoymilesConnectionError(
                f"{errors[0]}; no compatible HiBattery target found"
            ) from station_error

        for target in targets:
            device_payload = {
                "action": BATTERY_SETTINGS_ACTION,
                **target,
                "data": {"sid": station_id},
            }
            try:
                return await self._async_battery_settings_request(
                    device_payload, "device"
                )
            except HoymilesConnectionError as device_error:
                serial = str(target["dev_sn"])
                errors.append(f"device …{serial[-4:]}: {device_error}")

        raise HoymilesConnectionError("; ".join(errors)) from station_error

    async def async_write_battery_settings(
        self,
        station_id: int,
        mode: int,
        mode_data: dict[str, Any],
        *,
        request_method: str | None,
    ) -> None:
        """Write a complete battery mode payload using the proven read target."""
        await self.async_ensure_login()
        command_data = battery_setting_command_data(
            station_id, mode, mode_data
        )

        if request_method == "device":
            targets = battery_setting_targets(
                await self.async_device_tree(station_id)
            )
            if not targets:
                raise HoymilesConnectionError(
                    "No compatible HiBattery target found for battery settings"
                )
            errors: list[str] = []
            for target in targets:
                payload = {
                    "action": BATTERY_SETTINGS_ACTION,
                    **target,
                    "data": command_data,
                }
                try:
                    await self._async_write_battery_settings_request(payload)
                    return
                except HoymilesConnectionError as err:
                    serial = str(target["dev_sn"])
                    errors.append(f"device …{serial[-4:]}: {err}")
            raise HoymilesConnectionError("; ".join(errors))

        payload = {
            "action": BATTERY_SETTINGS_ACTION,
            "data": command_data,
        }
        await self._async_write_battery_settings_request(payload)


def microinverters(tree: Any) -> list[dict[str, Any]]:
    """Return type-3 devices from a nested Home device tree."""
    found: dict[int, dict[str, Any]] = {}

    def visit(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, dict):
            if value.get("type") == 3 and isinstance(value.get("id"), int):
                found[value["id"]] = value
            for child in value.values():
                visit(child)

    visit(tree)
    return list(found.values())
