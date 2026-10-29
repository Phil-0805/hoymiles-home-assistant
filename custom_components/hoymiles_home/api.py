"""Asynchronous S-Miles Home API client."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from typing import Any

from aiohttp import ClientError, ClientResponseError, ClientSession, ClientTimeout
from argon2.low_level import Type, hash_secret_raw

from .battery import (
    BatterySettingsError,
    battery_setting_targets,
    confirmed_reserve_soc,
    parse_battery_settings,
    parse_work_mode_settings,
    work_mode_command_data,
    reserve_soc_candidates,
    soc_setting_candidates,
)
from .const import (
    AUTH_BASE_URL,
    BATTERY_CONFIG_URL,
    BATTERY_SETTINGS_ACTION,
    BATTERY_SETTINGS_MAX_POLLS,
    BATTERY_SETTINGS_POLL_INTERVAL,
    BATTERY_USER_SETTINGS_URLS,
    DATA_BASE_URL,
    STATION_SETTING_READ_URL,
    STATION_SETTING_STATUS_URL,
    STATION_SETTING_WRITE_URL,
    TOKEN_LIFETIME,
    USER_AGENT,
    WORK_MODE_SETTINGS_ACTION,
)
from .protobuf import latest_values
from .telemetry import number
from .inverter import inverter_model
from .module_data import MAX_MODULE_BYTES, decode_module_snapshot
from .security import trusted_hoymiles_url
from .cloud_runtime import AccountRuntime, retry_delay
from .errors import (
    HoymilesError, HoymilesAuthError, HoymilesConnectionError, HoymilesRateLimitError,
)


class HoymilesHomeClient:
    """Client for the consumer S-Miles Home API."""

    def __init__(self, session: ClientSession, email: str, password: str,
                 runtime: AccountRuntime | None = None) -> None:
        self._session = session
        self._email = email
        self._password = password
        self.runtime = runtime or AccountRuntime()
        self._live_uri: str | None = None

    @property
    def _token(self):
        return self.runtime.token

    @_token.setter
    def _token(self, value):
        self.runtime.token = value

    @property
    def _token_expires(self):
        return self.runtime.token_expires

    @_token_expires.setter
    def _token_expires(self, value):
        self.runtime.token_expires = value

    @property
    def _login_retry_at(self):
        return self.runtime.login_retry_at

    @_login_retry_at.setter
    def _login_retry_at(self, value):
        self.runtime.login_retry_at = value

    @property
    def _lock(self):
        return self.runtime.login_lock

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
        if not trusted_hoymiles_url(url):
            raise HoymilesConnectionError("Untrusted Hoymiles API URL")
        try:
            async with self.runtime.request():
                async with self._session.post(
                    url,
                    json=payload,
                    headers=self.headers,
                    timeout=ClientTimeout(total=30),
                    allow_redirects=False,
                ) as response:
                    if 300 <= response.status < 400:
                        raise HoymilesConnectionError("Hoymiles API redirected unexpectedly")
                    response.raise_for_status()
                    data = await response.json(content_type=None)
        except ClientResponseError as err:
            if err.status == 429:
                retry_after = retry_delay((err.headers or {}).get("Retry-After"))
                self.runtime.pause(retry_after)
                raise HoymilesRateLimitError(
                    "Hoymiles request rate limit reached", retry_after
                ) from err
            if err.status == 401:
                self._token_expires = datetime.min.replace(tzinfo=UTC)
                raise HoymilesAuthError("Hoymiles authentication expired (HTTP 401)") from err
            raise HoymilesConnectionError(
                f"Hoymiles API request failed (HTTP {err.status})"
            ) from err
        except (ClientError, TimeoutError, ValueError) as err:
            # aiohttp exception strings may include signed URLs or tokens.
            raise HoymilesConnectionError(
                f"Hoymiles request failed ({type(err).__name__})"
            ) from err
        if not isinstance(data, dict):
            raise HoymilesConnectionError("Unexpected API response")
        return data

    @staticmethod
    def _unwrap(response: dict[str, Any]) -> Any:
        if str(response.get("status")) not in {"0", "100"}:
            message = str(response.get("message") or "Hoymiles API rejected request")
            if "logins exceeds the daily maximum limit" in message.lower():
                raise HoymilesRateLimitError("Hoymiles daily login limit reached", 3600)
            if "login" in message.lower() or "token" in message.lower():
                raise HoymilesAuthError(message)
            raise HoymilesConnectionError(message)
        return response.get("data")

    async def async_login(self) -> None:
        """Authenticate explicitly, serializing account token changes."""
        async with self._lock:
            await self._async_login_unlocked()

    async def _async_login_unlocked(self) -> None:
        """Run Argon2 outside the event loop; caller holds the login lock."""
        pre = await self._json(
            f"{AUTH_BASE_URL}/iam/pub/3/auth/pre-insp", {"u": self._email}
        )
        data = self._unwrap(pre) or {}
        try:
            salt = bytes.fromhex(data["a"])
            nonce = data["n"]
        except (KeyError, TypeError, ValueError) as err:
            raise HoymilesAuthError("Incomplete pre-inspection response") from err
        challenge = (await asyncio.to_thread(
            hash_secret_raw,
            self._password.encode(), salt, 3, 32768, 1, 32, Type.ID
        )).hex()
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
        if self._token and datetime.now(UTC) < self._token_expires:
            return
        async with self._lock:
            # Another coroutine may have refreshed the token while we waited.
            if not self._token or datetime.now(UTC) >= self._token_expires:
                remaining = (self._login_retry_at - datetime.now(UTC)).total_seconds()
                if remaining > 0:
                    raise HoymilesRateLimitError("Hoymiles login retry is paused", remaining)
                try:
                    await self._async_login_unlocked()
                except HoymilesRateLimitError as err:
                    self._login_retry_at = datetime.now(UTC) + timedelta(seconds=err.retry_after)
                    raise

    async def async_device_tree(self, station_id: int) -> list[dict[str, Any]]:
        await self.async_ensure_login()
        response = await self._json(
            f"{DATA_BASE_URL}/pvmc/api/0/station/select_device_c", {"sid": station_id}
        )
        return self._unwrap(response) or []

    async def async_enrich_inverters(
        self, station_id: int, inverters: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Try read-only web metadata without making Home-account setup depend on it.

        The consumer tree often omits model_no. Web endpoints may expose it,
        but some Home accounts cannot access them. Probe only during initial
        discovery, with a shared time budget and no raw payload/error logging.
        Never replace identity fields from a supplemental response.
        """
        enriched = [dict(inverter) for inverter in inverters]
        pending = []
        for inverter in enriched:
            if inverter_model(inverter) != "Hoymiles microinverter":
                inverter["_model_discovery"] = {"result": "identified", "source": "home_tree"}
            else:
                inverter["_model_discovery"] = {"result": "unresolved", "source": "none"}
                pending.append(inverter)
        if not pending:
            return enriched

        def apply(inverter: dict[str, Any], candidate: Any, source: str) -> bool:
            if not isinstance(candidate, dict):
                return False
            if candidate.get("id", inverter["id"]) != inverter["id"]:
                return False
            if inverter.get("sn") and candidate.get("sn") and inverter["sn"] != candidate["sn"]:
                return False
            model = inverter_model(candidate)
            if model == "Hoymiles microinverter":
                return False
            inverter["model_no"] = model
            inverter["_model_discovery"].update(result="identified", source=source)
            return True

        try:
            async with asyncio.timeout(12):
                try:
                    tree = self._unwrap(await self._json(
                        f"{DATA_BASE_URL}/pvm/api/0/station/select_device_of_tree",
                        {"id": station_id},
                    ))
                except HoymilesError:
                    for inverter in pending:
                        inverter["_model_discovery"]["web_tree"] = "unavailable"
                else:
                    candidates = {node["id"]: node for node in microinverters(tree)}
                    for inverter in pending:
                        found = apply(inverter, candidates.get(inverter["id"]), "web_tree")
                        inverter["_model_discovery"]["web_tree"] = "identified" if found else "no_model"

                # Bound supplemental requests on unusually large plants.
                for inverter in pending[:20]:
                    if inverter["_model_discovery"]["result"] == "identified":
                        continue
                    try:
                        detail = self._unwrap(await self._json(
                            f"{DATA_BASE_URL}/pvm/api/0/dev/micro/find",
                            {"id": inverter["id"], "sid": station_id},
                        ))
                    except HoymilesError:
                        inverter["_model_discovery"]["detail"] = "unavailable"
                    else:
                        found = apply(inverter, detail, "micro_detail")
                        inverter["_model_discovery"]["detail"] = "identified" if found else "no_model"
        except TimeoutError:
            for inverter in pending:
                if inverter["_model_discovery"]["result"] != "identified":
                    inverter["_model_discovery"]["timeout"] = True
        return enriched

    async def async_list_stations(self) -> list[dict[str, Any]]:
        """Discover Home-account stations, without confusing device IDs with sids."""
        await self.async_ensure_login()
        stations: dict[int, dict[str, Any]] = {}
        page_size = 100
        # Bound discovery even if the undocumented endpoint repeats a full page.
        for page in range(1, 21):
            response = await self._json(
                f"{DATA_BASE_URL}/pvmc/api/0/station/select_by_page_c",
                {"page": page, "page_size": page_size},
            )
            data = self._unwrap(response)
            if not isinstance(data, dict) or not isinstance(data.get("list"), list):
                raise HoymilesConnectionError("Unexpected station list response")
            rows = data["list"]
            if not rows:
                return list(stations.values())
            previous_count = len(stations)
            for row in rows:
                if not isinstance(row, dict):
                    continue
                # This is a station-list endpoint: id is a station ID here only.
                # Prefer the Home API's sid; never fall back from an invalid sid.
                raw_id = row.get("sid", row.get("id"))
                if isinstance(raw_id, bool) or not isinstance(raw_id, (int, str)):
                    continue
                if isinstance(raw_id, str):
                    raw_id = raw_id.strip()
                    if not raw_id.isascii() or not raw_id.isdecimal():
                        continue
                try:
                    station_id = int(raw_id)
                except (TypeError, ValueError):
                    continue
                if station_id <= 0:
                    continue
                name = row.get("name")
                stations[station_id] = {
                    "sid": station_id,
                    "name": name.strip() if isinstance(name, str) else "",
                }
            if len(stations) == previous_count:
                raise HoymilesConnectionError("Station list has no new valid station IDs")
            if len(rows) < page_size:
                return list(stations.values())
        raise HoymilesConnectionError("Station discovery exceeded its page limit")

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
        if not isinstance(uri, str) or not trusted_hoymiles_url(uri):
            raise HoymilesConnectionError("Live API returned an untrusted URI")
        return uri

    async def async_live(self, station_id: int) -> dict[str, Any]:
        await self.async_ensure_login()
        for _attempt in range(2):
            try:
                if not self._live_uri:
                    self._live_uri = await self._get_live_uri(station_id)
                response = await self._json(self._live_uri, {"sid": station_id, "m": 0})
                payload = self._unwrap(response) if "status" in response else response
            except HoymilesRateLimitError:
                self._live_uri = None
                raise
            except HoymilesAuthError:
                self._live_uri = None
                if _attempt:
                    raise
                self._token_expires = datetime.min.replace(tzinfo=UTC)
                await self.async_ensure_login()
                continue
            except HoymilesConnectionError:
                self._live_uri = None
                if _attempt:
                    raise
                continue
            # The realtime server returns the live values inside the regular
            # {status, data} envelope. The working Node-RED client unwraps that
            # envelope in postUrl(), so accept both forms here for resilience.
            if isinstance(payload, dict) and (
                isinstance(payload.get("flow"), list)
                or number(payload.get("con")) in (0, 1)
            ):
                return payload
            self._live_uri = None
        raise HoymilesConnectionError("Live URI expired")

    async def _async_binary_data(self, url: str, payload: dict[str, Any]) -> bytes:
        """Read a bounded binary payload, rejecting redirects and JSON errors."""
        if not trusted_hoymiles_url(url):
            raise HoymilesConnectionError("Untrusted Hoymiles API URL")
        try:
            async with self.runtime.request():
                async with self._session.post(
                    url, json=payload, headers=self.headers,
                    timeout=ClientTimeout(total=30), allow_redirects=False,
                ) as response:
                    if 300 <= response.status < 400:
                        raise HoymilesConnectionError("Hoymiles API redirected unexpectedly")
                    if response.status == 401:
                        self._token_expires = datetime.min.replace(tzinfo=UTC)
                        raise HoymilesAuthError("Hoymiles authentication expired (HTTP 401)")
                    response.raise_for_status()
                    chunks, size = [], 0
                    async for chunk in response.content.iter_chunked(65536):
                        size += len(chunk)
                        if size > MAX_MODULE_BYTES:
                            raise HoymilesConnectionError("Chart response exceeds size limit")
                        chunks.append(chunk)
                    raw = b"".join(chunks)
        except ClientResponseError as err:
            if err.status == 429:
                retry_after = retry_delay((err.headers or {}).get("Retry-After"))
                self.runtime.pause(retry_after)
                raise HoymilesRateLimitError("Hoymiles chart rate limit reached", retry_after) from err
            raise HoymilesConnectionError(f"Chart request failed (HTTP {err.status})") from err
        except (ClientError, TimeoutError) as err:
            raise HoymilesConnectionError(
                f"Hoymiles chart request failed ({type(err).__name__})"
            ) from err
        if raw.lstrip().startswith(b"{"):
            try:
                self._unwrap(json.loads(raw))
            except (ValueError, TypeError) as err:
                raise HoymilesConnectionError("Invalid chart error response") from err
            raise HoymilesConnectionError("Chart endpoint returned no chart data")
        return raw

    async def async_module_values(
        self, station_id: int, device_id: int, port: int, date: str
    ) -> dict[str, float | None]:
        await self.async_ensure_login()
        raw = await self._async_binary_data(
            f"{DATA_BASE_URL}/pvmc/api/0/module_data/count_by_day_c",
            {"sid": station_id, "date": date,
             "mi_list": [{"id": device_id, "port": port}],
             "quota": ["MODULE_POWER", "MODULE_V", "MODULE_I"]},
        )
        try:
            return latest_values(raw, device_id=device_id, port=port)
        except (ValueError, UnicodeError) as err:
            raise HoymilesConnectionError("Invalid chart response") from err

    async def async_module_snapshot(self, station_id: int, date: str) -> dict[str, Any]:
        """Optional read-only inverter telemetry; never replaces live power."""
        await self.async_ensure_login()
        raw = await self._async_binary_data(
            f"{DATA_BASE_URL}/pvmc/api/0/module_data/dmdd_c",
            {"sid": station_id, "date": date},
        )
        try:
            return decode_module_snapshot(raw, station_id, date)
        except (ValueError, UnicodeError) as err:
            raise HoymilesConnectionError("Invalid inverter details response") from err

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

    async def _async_poll_station_setting_job(self, job_id: str) -> dict[str, Any]:
        """Poll the command-status endpoint used by the current Home app."""
        for _attempt in range(BATTERY_SETTINGS_MAX_POLLS):
            await asyncio.sleep(BATTERY_SETTINGS_POLL_INTERVAL)
            response = await self._json(STATION_SETTING_STATUS_URL, {"id": job_id})
            status = self._unwrap(response)
            if isinstance(status, str):
                try:
                    status = json.loads(status)
                except ValueError as err:
                    raise HoymilesConnectionError(
                        "Work mode returned invalid JSON"
                    ) from err
            if not isinstance(status, dict):
                raise HoymilesConnectionError("Work mode returned an invalid status")
            if status.get("code") == 2:
                continue
            return status
        raise HoymilesConnectionError("Work mode request timed out")

    async def _async_work_mode_settings(self, station_id: int) -> dict[str, Any]:
        """Read the real Eigenverbrauch settings exactly as the Home app does."""
        response = await self._json(
            STATION_SETTING_READ_URL,
            {"action": WORK_MODE_SETTINGS_ACTION, "data": {"sid": station_id}},
        )
        job_id = self._unwrap(response)
        if not isinstance(job_id, (str, int)):
            raise HoymilesConnectionError("Work mode read returned no command id")
        status = await self._async_poll_station_setting_job(str(job_id))
        try:
            return parse_work_mode_settings(status)
        except BatterySettingsError as err:
            raise HoymilesConnectionError(str(err)) from err

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

    async def _async_verify_battery_settings(
        self, station_id: int, settings: dict[str, Any]
    ) -> dict[str, Any]:
        """Verify action-1013 data against current S-Miles Home app settings."""
        probes: list[dict[str, Any]] = []
        candidates: list[dict[str, Any]] = []

        probe_requests = [(BATTERY_USER_SETTINGS_URLS[0], {"sid": station_id})]
        probe_requests.extend(
            (BATTERY_USER_SETTINGS_URLS[1], payload)
            for payload in (
                {"sid": station_id},
                {"id": station_id},
                {"station_id": station_id},
                {"stationId": station_id},
            )
        )

        for url, request_payload in probe_requests:
            endpoint = url.rsplit("/", 1)[-1]
            request_key = next(iter(request_payload))
            try:
                response = await self._json(url, request_payload)
                payload = self._unwrap(response)
            except (HoymilesAuthError, HoymilesConnectionError) as err:
                probes.append(
                    {
                        "endpoint": endpoint,
                        "request_key": request_key,
                        "status": "error",
                        "error": str(err),
                    }
                )
                continue

            found = reserve_soc_candidates(payload)
            probes.append(
                {
                    "endpoint": endpoint,
                    "request_key": request_key,
                    "status": "ok",
                    "reserve_soc_candidates": found,
                    "soc_setting_candidates": soc_setting_candidates(payload),
                }
            )
            candidates.extend(found)

        verified = confirmed_reserve_soc(candidates, settings.get("mode"))
        verified_source = "station_user_settings"
        active = settings.get("active_settings")
        if (
            verified is None
            and settings.get("request_method") == "station"
            and isinstance(active, dict)
            and isinstance(active.get("reserve_soc"), (int, float))
            and not isinstance(active.get("reserve_soc"), bool)
        ):
            # A station-addressed result is the authoritative configuration.
            # Only the device-addressed fallback has proven stale on HiBattery.
            verified = int(active["reserve_soc"])
            verified_source = "station_action_1013"
        settings["app_user_agent"] = USER_AGENT
        settings["user_setting_probes"] = probes
        settings["reserve_soc_verified"] = verified is not None
        settings["writable"] = verified is not None

        mode_settings = settings.get("mode_settings")
        mode = settings.get("mode")
        if verified is not None:
            if isinstance(active, dict):
                active["reserve_soc"] = verified
            if (
                isinstance(mode_settings, dict)
                and isinstance(mode_settings.get(mode), dict)
            ):
                mode_settings[mode]["reserve_soc"] = verified
            settings["reserve_soc_source"] = verified_source
            return settings

        if isinstance(active, dict):
            legacy_value = active.pop("reserve_soc", None)
            if legacy_value is not None:
                settings["unverified_action_1013_reserve_soc"] = legacy_value
        if (
            isinstance(mode_settings, dict)
            and isinstance(mode_settings.get(mode), dict)
        ):
            mode_settings[mode].pop("reserve_soc", None)
        settings["reserve_soc_source"] = "unverified_action_1013"
        return settings

    async def async_battery_settings(self, station_id: int) -> dict[str, Any]:
        """Read battery settings, with a HiBattery-addressed fallback."""
        await self.async_ensure_login()
        try:
            return await self._async_work_mode_settings(station_id)
        except HoymilesConnectionError as err:
            # Retain the older read path for devices/firmware that do not
            # implement the consumer app's command-83 work-mode protocol.
            # Python clears the exception target when leaving an except block.
            work_mode_error = str(err)
        station_payload = {
            "action": BATTERY_SETTINGS_ACTION,
            "data": {"sid": station_id},
        }
        try:
            settings = await self._async_battery_settings_request(
                station_payload, "station"
            )
            verified = await self._async_verify_battery_settings(station_id, settings)
            verified["work_mode_request_error"] = work_mode_error
            return verified
        except HoymilesConnectionError as err:
            if "device list is empty" not in str(err).lower():
                raise
            station_error = err

        errors = [
            f"work mode request: {work_mode_error}",
            f"station request: {station_error}",
        ]
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
                settings = await self._async_battery_settings_request(
                    device_payload, "device"
                )
                verified = await self._async_verify_battery_settings(
                    station_id, settings
                )
                verified["work_mode_request_error"] = work_mode_error
                return verified
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
        """Write a complete battery mode payload through the current app API."""
        await self.async_ensure_login()
        if request_method == "station_action_83":
            try:
                command_data = work_mode_command_data(mode, mode_data)
            except BatterySettingsError as err:
                raise HoymilesConnectionError(str(err)) from err
            response = await self._json(
                STATION_SETTING_WRITE_URL,
                {"action": WORK_MODE_SETTINGS_ACTION, "data": {"sid": station_id, **command_data}},
            )
            job_id = self._unwrap(response)
            if not isinstance(job_id, (str, int)):
                raise HoymilesConnectionError("Work mode write returned no command id")
            status = await self._async_poll_station_setting_job(str(job_id))
            if status.get("code") != 0:
                raise HoymilesConnectionError(
                    str(status.get("message") or "Work mode write failed")
                )
            return
        response = await self._json(
            BATTERY_CONFIG_URL,
            {"sid": station_id, "mode": mode, "data": deepcopy(mode_data)},
        )
        result = self._unwrap(response)
        if result is False:
            raise HoymilesConnectionError("Battery configuration was rejected")


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
