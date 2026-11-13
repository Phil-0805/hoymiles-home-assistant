"""Asynchronous S-Miles Home API client."""

from __future__ import annotations

import asyncio
import base64
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import hashlib
import json
import re
from typing import Any

from aiohttp import ClientError, ClientResponseError, ClientSession, ClientTimeout
from argon2.low_level import Type, hash_secret_raw

from .battery_telemetry import parse_battery_temperatures
from .device_settings import parse_cutoffs, parse_heating, parse_lighting, setting_integer
from .output_power import output_phases, output_write_data, parse_output_settings, validate_output_settings
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
    AUTH_BASE_URLS,
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
    INSTALLER_USER_AGENT, ENDUSER_USER_AGENT, CLIENT_PROFILES,
    WORK_MODE_SETTINGS_ACTION,
)
from .protobuf import ProtobufDecodeError, latest_module_samples
from .telemetry import number
from .inverter import inverter_model
from .module_data import MAX_MODULE_BYTES, decode_module_snapshot
from .micro_data import MICRO_QUOTAS, decode_micro_details
from .security import trusted_hoymiles_url, trusted_auth_redirect, trusted_auth_base
from .cloud_logging import (
    CloudDiagnosticError, LOGGER as CLOUD_LOGGER, failure_reason, response_summary,
    live_response_summary, request_stage, cloud_failure_reason, work_mode_response_summary,
)
from .cloud_runtime import AccountRuntime, retry_delay
from .enduser import (
    ES_CLASSIFICATIONS, SUPPORTED_CLASSIFICATIONS,
    parse_live as parse_enduser_live, parse_totals as parse_enduser_totals,
)
from .errors import (
    HoymilesError, HoymilesAuthError, HoymilesConnectionError, HoymilesRateLimitError, HoymilesSettingsError,
    HoymilesTelemetryError,
)

MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_JSON_DEPTH = 32


async def _bounded_json(response) -> dict[str, Any]:
    """Limit decoded HTTP bytes and nesting before recursive payload consumers."""
    chunks, size = [], 0
    async for chunk in response.content.iter_chunked(65536):
        size += len(chunk)
        if size > MAX_JSON_BYTES:
            raise HoymilesConnectionError("JSON response exceeds size limit")
        chunks.append(chunk)
    return _decode_json(b"".join(chunks))


def _decode_json(raw: bytes | str) -> dict[str, Any]:
    """Apply the same limits to HTTP bodies and JSON embedded in text fields."""
    try:
        size = len(raw.encode("utf-8")) if isinstance(raw, str) else len(raw)
        if size > MAX_JSON_BYTES:
            raise HoymilesConnectionError("JSON response exceeds size limit")
        data = json.loads(raw)
    except (ValueError, UnicodeError, RecursionError):
        raise CloudDiagnosticError("invalid_json", "Invalid JSON response") from None
    if not isinstance(data, dict):
        raise CloudDiagnosticError("unexpected_response", "Unexpected API response")
    pending = [(data, 0)]
    while pending:
        value, depth = pending.pop()
        if depth > MAX_JSON_DEPTH:
            raise HoymilesConnectionError("JSON response exceeds nesting limit")
        if isinstance(value, dict):
            pending.extend((item, depth + 1) for item in value.values() if isinstance(item, (dict, list)))
        elif isinstance(value, list):
            pending.extend((item, depth + 1) for item in value if isinstance(item, (dict, list)))
    return data


class HoymilesHomeClient:
    """Client for the consumer S-Miles Home API."""

    def __init__(self, session: ClientSession, email: str, password: str,
                 runtime: AccountRuntime | None = None, *, profile: str = "home") -> None:
        if profile not in CLIENT_PROFILES:
            raise ValueError("Unsupported Hoymiles client profile")
        self._session = session
        self._email = email
        self._password = password
        self.runtime = runtime or AccountRuntime()
        self.profile = profile
        self.supports_home_features = profile == "home"
        self._auth_state = {"home": self.runtime, "installer": self.runtime.installer_session,
                            "enduser": self.runtime.enduser_session}[profile]
        self._station_classifications: dict[int, int] = {}
        self._station_metadata_lock = asyncio.Lock()
        self._live_uri: str | None = None
        self._cloud_log_states = {}
        self._auth_version = None
        self._auth_dc = None

    @property
    def _token(self):
        return self._auth_state.token

    @_token.setter
    def _token(self, value):
        self._auth_state.token = value

    @property
    def _token_expires(self):
        return self._auth_state.token_expires

    @_token_expires.setter
    def _token_expires(self, value):
        self._auth_state.token_expires = value

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
        agent = {"home": USER_AGENT, "installer": INSTALLER_USER_AGENT,
                 "enduser": ENDUSER_USER_AGENT}[self.profile]
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Charset": "UTF-8",
            "language": "en_us",
            "User-Agent": (agent.rsplit("/", 1)[0] + f"/{self._auth_state.auth_dc}"
                           if self._auth_state.auth_dc in AUTH_BASE_URLS else agent),
        }
        if self._token:
            headers["Authorization"] = self._token
        return headers

    def _cloud_report(self, stage, reason, response=None, *, http_status=None, redirect_policy=None):
        # One warning per changed failure shape, without storing private input.
        summary = (live_response_summary(response.get("data"))
                   if stage == "live_data" and reason == "invalid_live_data" and isinstance(response, dict)
                   else work_mode_response_summary(response)
                   if stage == "work_mode_read" and reason == "invalid_work_mode_settings"
                   else response_summary(response))
        if http_status is not None:
            code = http_status if type(http_status) is int and 100 <= http_status <= 599 else "unavailable"
            summary = f"http_status={code} {summary}"
        if redirect_policy in {"allowed_auth_target", "blocked_target", "unsupported_status", "hop_limit", "not_auth_request"}:
            summary = f"redirect_policy={redirect_policy} {summary}"
        if stage == "login" and type(self._auth_version) is int and self._auth_version in (1, 2, 3):
            summary = f"{summary} auth_version={self._auth_version}"
        auth_dc = self._auth_dc if self._auth_dc is not None else self._auth_state.auth_dc
        if stage in {"login_region", "login_challenge", "login"} and type(auth_dc) is int and auth_dc in AUTH_BASE_URLS:
            summary = f"{summary} auth_dc={auth_dc}"
        if not self.supports_home_features:
            summary = f"{summary} client_profile={self.profile}"
        key = (stage, reason)
        if self._cloud_log_states.get(key) != summary:
            self._cloud_log_states[key] = summary
            if stage in {"live_uri_mobile", "live_uri_web"} and reason == "missing_uri":
                CLOUD_LOGGER.info("Cloud live address unavailable: stage=%s reason=%s %s", stage, reason, summary)
            else:
                CLOUD_LOGGER.warning("Cloud request failed: stage=%s reason=%s %s", stage, reason, summary)

    def _cloud_stage(self, url, payload=None):
        return request_stage(url, payload, self._live_uri)

    async def _json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.supports_home_features:
            # Verified read-only subset; never reuse Home commands with this token.
            allowed = {
                f"{base}/iam/pub/3/auth/{op}" for base in AUTH_BASE_URLS.values()
                for op in ("pre-insp", "login")
            } | {f"{DATA_BASE_URL}{path}" for path in (
                "/pvm/api/0/station/select_by_page", "/pvm/api/0/station/select_device_of_tree",
                "/pvm/api/0/station/get_sd_uri", "/pvm-data/api/0/station/data/count_station_real_data",
            )}
            if self.profile == "enduser":
                allowed |= {f"{DATA_BASE_URL}/pvm/api/0/{path}" for path in (
                    "station_v3/next_p_a", "station/find",
                )}
            if url not in allowed and url != self._live_uri:
                raise CloudDiagnosticError("unsupported_profile_operation", "Operation is unavailable for the Installer/Enduser monitoring profiles")
        if not trusted_hoymiles_url(url):
            raise HoymilesConnectionError("Untrusted Hoymiles API URL")
        stage = self._cloud_stage(url, payload)
        is_auth = stage in {"login_region", "login_challenge", "login"}
        headers = self.headers
        if is_auth:
            # These public authentication operations need no previous token.
            headers.pop("Authorization", None)
        try:
            for hop in range(2):
                async with self.runtime.request():
                    async with self._session.post(
                        url,
                        json=payload,
                        headers=headers,
                        timeout=ClientTimeout(total=30),
                        allow_redirects=False,
                    ) as response:
                        if 300 <= response.status < 400:
                            target = response.headers.get("Location")
                            policy = (
                                "not_auth_request" if not is_auth else
                                "unsupported_status" if response.status not in (302, 307) else
                                "hop_limit" if hop else
                                "blocked_target" if not trusted_auth_redirect(url, target) else
                                "allowed_auth_target"
                            )
                            if policy != "allowed_auth_target":
                                self._cloud_report(stage, "redirect_rejected", http_status=response.status,
                                                   redirect_policy=policy)
                                raise CloudDiagnosticError("redirect_rejected", "Hoymiles API redirected unexpectedly")
                            CLOUD_LOGGER.info(
                                "Cloud auth redirect followed: stage=%s http_status=%s target_policy=known_auth_endpoint",
                                stage, response.status,
                            )
                            url = target
                            continue
                        response.raise_for_status()
                        data = await _bounded_json(response)
                        break
        except ClientResponseError as err:
            # HTTP status is numeric; response text, URLs and headers are omitted.
            self._cloud_report(stage, "http_error", http_status=err.status)
            if err.status == 429:
                retry_after = retry_delay((err.headers or {}).get("Retry-After"))
                self.runtime.pause(retry_after)
                raise HoymilesRateLimitError(
                    "Hoymiles request rate limit reached", retry_after
                ) from None
            if err.status == 401:
                self._token_expires = datetime.min.replace(tzinfo=UTC)
                raise HoymilesAuthError("Hoymiles authentication expired (HTTP 401)") from None
            if 400 <= err.status < 500:
                # A rejected request is not an occasion for accelerated reads.
                raise CloudDiagnosticError("http_error", f"Hoymiles API request failed (HTTP {err.status})") from None
            raise HoymilesConnectionError(
                f"Hoymiles API request failed (HTTP {err.status})"
            ) from None
        except HoymilesConnectionError as err:
            if failure_reason(err) != "redirect_rejected":
                self._cloud_report(stage, failure_reason(err))
            raise
        except (ClientError, TimeoutError, ValueError) as err:
            self._cloud_report(stage, "timeout" if isinstance(err, TimeoutError) else "transport_error")
            # aiohttp exception strings may include signed URLs or tokens.
            raise HoymilesConnectionError(
                f"Hoymiles request failed ({type(err).__name__})"
            ) from None
        if not isinstance(data, dict):
            raise HoymilesConnectionError("Unexpected API response")
        expects_envelope = stage in {
            "login_region", "login_challenge", "login", "station_discovery", "station_validation",
            "live_uri_mobile", "live_uri_web",
        }
        if "status" in data or expects_envelope:
            reason = cloud_failure_reason(data)
            if reason:
                self._cloud_report(stage, reason, data)
            if reason == "session_expired":
                self._token = None
                self._token_expires = datetime.min.replace(tzinfo=UTC)
                self._live_uri = None
                raise HoymilesAuthError("Hoymiles session expired")
            if reason == "rate_limited":
                self.runtime.pause(3600)
                raise HoymilesRateLimitError("Hoymiles daily login limit reached", 3600)
        return data

    @staticmethod
    def _unwrap(response: dict[str, Any]) -> Any:
        reason = cloud_failure_reason(response)
        if reason:
            if reason == "session_expired":
                raise HoymilesAuthError("Hoymiles session expired")
            if reason in {"client_update_required", "home_app_required"}:
                raise CloudDiagnosticError(reason, "Hoymiles rejected the client profile")
            message = str(response.get("message") or "Hoymiles API rejected request")
            if "logins exceeds the daily maximum limit" in message.lower():
                raise HoymilesRateLimitError("Hoymiles daily login limit reached", 3600)
            if "login" in message.lower() or "token" in message.lower():
                raise HoymilesAuthError("Hoymiles authentication rejected")
            if "device list is empty" in message.lower():
                # Keep the known fallback signal, never the arbitrary text.
                raise HoymilesConnectionError("Hoymiles device list is empty")
            raise CloudDiagnosticError("cloud_rejected", "Hoymiles API rejected request")
        return response.get("data")

    async def async_login(self) -> None:
        """Authenticate explicitly, serializing account token changes."""
        async with self._lock:
            await self._async_login_unlocked()

    async def _async_login_unlocked(self) -> None:
        """Follow the server-selected app protocol; never retry another algorithm."""
        self._auth_version = None
        self._auth_dc = None
        self._auth_state.auth_dc = None
        self._token = None
        self._token_expires = datetime.min.replace(tzinfo=UTC)
        self._live_uri = None
        self._station_classifications.clear()
        if self.supports_home_features:
            region = await self._json(f"{AUTH_BASE_URL}/iam/pub/0/c/region_c", {"email": self._email})
            routing = self._unwrap(region)
            dc = setting_integer(routing.get("dc"), 4) if isinstance(routing, dict) else None
            base = routing.get("login_url") if isinstance(routing, dict) else None
            if dc not in AUTH_BASE_URLS or not trusted_auth_base(base) or base.rstrip("/") != AUTH_BASE_URLS[dc]:
                self._cloud_report("login_region", "invalid_auth_routing", region)
                raise CloudDiagnosticError("invalid_auth_routing", "Invalid Hoymiles authentication routing")
            self._auth_state.auth_dc = dc
            base = AUTH_BASE_URLS[dc]
        else:
            # Installer and Enduser clear stored DC before pre-inspection.
            base = DATA_BASE_URL
        pre = await self._json(
            f"{base}/iam/pub/3/auth/pre-insp", {"u": self._email}
        )
        data = self._unwrap(pre)
        if not isinstance(data, dict):
            self._cloud_report("login_challenge", "invalid_challenge", pre)
            raise HoymilesAuthError("Incomplete pre-inspection response")
        version = setting_integer(data.get("v"), 3)
        if version not in (1, 2, 3):
            self._cloud_report("login_challenge", "unsupported_auth_version", pre)
            raise CloudDiagnosticError("unsupported_auth_version", "Unsupported S-Miles Home login protocol")
        self._auth_version = version
        dc = setting_integer(data.get("dc"), 4)
        if dc not in (AUTH_BASE_URLS if self.supports_home_features else (0, 1)):
            self._cloud_report("login_challenge", "unsupported_auth_region", pre)
            raise CloudDiagnosticError("unsupported_auth_region", "Unsupported S-Miles Home authentication region")
        self._auth_dc = dc
        self._auth_state.auth_dc = dc
        if not self.supports_home_features and setting_integer(data.get("f", 0), 2**31 - 1) != 0:
            self._cloud_report("login_challenge", "account_action_required", pre)
            raise CloudDiagnosticError("account_action_required", "Complete the required account action in the official app")
        try:
            nonce = data.get("n")
            if nonce is not None and (not isinstance(nonce, str) or not 1 <= len(nonce) <= 1024):
                raise ValueError("Invalid authentication challenge")
            if version == 3:
                salt = bytes.fromhex(data["a"])
                if not 8 <= len(salt) <= 64 or nonce is None:
                    raise ValueError("Invalid authentication challenge")
        except (KeyError, TypeError, ValueError):
            self._cloud_report("login_challenge", "invalid_challenge", pre)
            raise HoymilesAuthError("Incomplete pre-inspection response") from None
        if version == 3:
            challenge = (await asyncio.to_thread(
                hash_secret_raw,
                self._password.encode(), salt, 3, 32768, 1, 32, Type.ID
            )).hex()
        elif version == 1 and not self.supports_home_features:
            challenge = hashlib.md5(self._password.encode()).hexdigest()
        else:
            # ToolsUtil.e / web encryptPwd: MD5 hex + '.' + SHA-256 Base64.
            # Selected only by an explicit v=1/2 challenge over trusted HTTPS.
            password_bytes = self._password.encode()
            challenge = (hashlib.md5(password_bytes).hexdigest() + "."
                         + base64.b64encode(hashlib.sha256(password_bytes).digest()).decode("ascii"))
        login = await self._json(
            f"{AUTH_BASE_URLS[dc] if self.supports_home_features else DATA_BASE_URL}/iam/pub/3/auth/login",
            {"u": self._email, "ch": challenge, **({"n": nonce} if nonce is not None else {})},
        )
        login_data = self._unwrap(login)
        token = login_data.get("token") if isinstance(login_data, dict) else None
        if not isinstance(token, str) or not 1 <= len(token) <= 16384:
            self._cloud_report("login", "missing_token", login)
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
                except HoymilesConnectionError:
                    # A shared lock alone coalesces successful logins only.
                    # Pause failed transport attempts across all station clients.
                    self._login_retry_at = datetime.now(UTC) + timedelta(seconds=60)
                    raise

    async def async_device_tree(self, station_id: int) -> list[dict[str, Any]]:
        await self.async_ensure_login()
        if self.profile == "enduser":
            await self._async_enduser_classification(station_id)
        response = await self._json(
            f"{DATA_BASE_URL}/pvmc/api/0/station/select_device_c" if self.supports_home_features
            else f"{DATA_BASE_URL}/pvm/api/0/station/select_device_of_tree",
            {"sid": station_id} if self.supports_home_features else {"id": station_id},
        )
        tree = self._unwrap(response)
        if tree is None or self.supports_home_features and not tree:
            tree = []
        if not self.supports_home_features:
            self._validate_installer_tree(tree, station_id)
        return tree

    @staticmethod
    def _validate_installer_tree(tree, station_id):
        if not isinstance(tree, list):
            raise CloudDiagnosticError("unexpected_response", "Invalid Installer device tree")
        pending = list(tree)
        seen = {}
        visited = 0
        while pending:
            visited += 1
            if visited > 4096:
                raise CloudDiagnosticError("unexpected_response", "Installer tree exceeds size limit")
            node = pending.pop()
            if (not isinstance(node, dict) or type(node.get("id")) is not int or node["id"] <= 0
                    or type(node.get("type")) is not int
                    or ("station_id" in node and (type(node["station_id"]) is not int
                                                 or node["station_id"] != station_id))):
                raise CloudDiagnosticError("unexpected_response", "Invalid Installer device identity")
            identity = (node["type"], node["id"])
            if identity in seen and seen[identity] != node:
                raise CloudDiagnosticError("unexpected_response", "Ambiguous Installer device identity")
            seen[identity] = node
            children = node.get("children", [])
            if children is None:
                children = []
            if not isinstance(children, list):
                raise CloudDiagnosticError("unexpected_response", "Invalid Installer device children")
            pending.extend(children)
            if len(seen) > 4096:
                raise CloudDiagnosticError("unexpected_response", "Installer tree exceeds size limit")

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
        if not self.supports_home_features:
            return enriched
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
            if ("id" in candidate and (type(candidate["id"]) is not int
                                       or candidate["id"] != inverter["id"])):
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
                    candidates = {node["id"]: node for node in microinverters(tree, reject_ambiguous=True)}
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
        if self.profile == "enduser":
            return await self._async_list_enduser_stations()
        stations: dict[int, dict[str, Any]] = {}
        page_size = 100
        # Bound discovery even if the undocumented endpoint repeats a full page.
        for page in range(1, 21):
            response = await self._json(
                f"{DATA_BASE_URL}/pvmc/api/0/station/select_by_page_c" if self.supports_home_features
                else f"{DATA_BASE_URL}/pvm/api/0/station/select_by_page",
                {"page": page, "page_size": page_size},
            )
            data = self._unwrap(response)
            if not isinstance(data, dict) or not isinstance(data.get("list"), list):
                self._cloud_report("station_discovery", "unexpected_response", response)
                raise CloudDiagnosticError("unexpected_response", "Unexpected station list response")
            rows = data["list"]
            if not rows:
                return list(stations.values())
            previous_count = len(stations)
            for row in rows:
                if not isinstance(row, dict):
                    continue
                # This is a station-list endpoint: id is a station ID here only.
                # Prefer the Home API's sid; never fall back from an invalid sid.
                raw_id = row.get("sid", row.get("id")) if self.supports_home_features else row.get("id")
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

    async def _async_enduser_classification(self, station_id: int) -> int:
        """Read station metadata once per client session, including manual setup."""
        if type(station_id) is not int or station_id <= 0:
            raise CloudDiagnosticError("unexpected_response", "Invalid Enduser station identity")
        async with self._station_metadata_lock:
            if station_id not in self._station_classifications:
                data = self._unwrap(await self._json(
                    f"{DATA_BASE_URL}/pvm/api/0/station/find", {"id": station_id}))
                if (not isinstance(data, dict) or type(data.get("id")) is not int
                        or data["id"] != station_id or type(data.get("classify")) is not int):
                    raise CloudDiagnosticError("unexpected_response", "Invalid Enduser station identity")
                if data["classify"] not in SUPPORTED_CLASSIFICATIONS:
                    raise CloudDiagnosticError("unsupported_profile_operation", "Unsupported Enduser station classification")
                self._station_classifications[station_id] = data["classify"]
            return self._station_classifications[station_id]

    async def _async_list_enduser_stations(self) -> list[dict[str, Any]]:
        """Follow the app's unfiltered list and bounded continuation tokens."""
        stations = {}
        token = None
        for page in range(1, 21):
            body = {"classify": 0, "page": page, "page_size": 10}
            if token is not None:
                body["ntk"] = token
            data = self._unwrap(await self._json(
                f"{DATA_BASE_URL}/pvm/api/0/station_v3/next_p_a", body))
            if not isinstance(data, dict) or not isinstance(data.get("list"), list):
                raise CloudDiagnosticError("unexpected_response", "Invalid Enduser station list")
            rows = data["list"]
            if len(rows) > 10:
                raise CloudDiagnosticError("unexpected_response", "Invalid Enduser page size")
            previous = len(stations)
            for row in rows:
                if not isinstance(row, dict) or type(row.get("id")) is not int or row["id"] <= 0:
                    raise CloudDiagnosticError("unexpected_response", "Invalid Enduser station identity")
                name = row.get("name")
                stations[row["id"]] = {"sid": row["id"], "name": name.strip() if isinstance(name, str) else ""}
            if rows and len(stations) == previous:
                raise CloudDiagnosticError("unexpected_response", "Enduser station page did not advance")
            if not rows or len(rows) < 10:
                return list(stations.values())
            token = data.get("ntk")
            # The app omits absent/empty ntk and still advances the page number.
            # ntk may identify the list snapshot rather than a unique cursor.
            if token == "":
                token = None
            if token is not None and (not isinstance(token, str) or len(token) > 4096):
                raise CloudDiagnosticError("unexpected_response", "Invalid Enduser continuation")
        raise CloudDiagnosticError("unexpected_response", "Enduser discovery exceeded page limit")

    async def async_station_realtime(self, station_id: int) -> dict[str, Any]:
        await self.async_ensure_login()
        es = (self.profile == "enduser" and
              await self._async_enduser_classification(station_id) in ES_CLASSIFICATIONS)
        response = await self._json(
            f"{DATA_BASE_URL}/pvmc/api/0/station_data/count_station_real_data_c" if self.supports_home_features
            else f"{DATA_BASE_URL}/pvm-data/api/0/station/data/count_station_real_data",
            {"sid": station_id, **({"off_real": 1} if es else {})},
        )
        data = self._unwrap(response)
        if self.profile == "enduser":
            return parse_enduser_totals(data)
        if data is not None and not isinstance(data, dict):
            raise HoymilesConnectionError("Unexpected station totals response")
        return data or {}

    async def async_battery_temperatures(self, station_id: int) -> dict:
        """Read the battery device list used by the official topology display."""
        await self.async_ensure_login()
        response = await self._json(
            f"{DATA_BASE_URL}/pvm/api/0/dev/au_inv/au_s_c", {"id": station_id}
        )
        return parse_battery_temperatures(self._unwrap(response))

    async def _get_live_uri(self, station_id: int) -> str:
        # Both routes are present in the manufacturer's clients. Use the web
        # route only when the mobile route succeeded but omitted its URI.
        routes = (
            ("live_uri_mobile", "/pvmc/api/0/station/get_sd_uri_c"),
            ("live_uri_web", "/pvm/api/0/station/get_sd_uri"),
        ) if self.supports_home_features else (("live_uri_web", "/pvm/api/0/station/get_sd_uri"),)
        for stage, path in routes:
            response = await self._json(f"{DATA_BASE_URL}{path}", {"sid": station_id})
            data = self._unwrap(response)
            if data is not None and not isinstance(data, dict):
                self._cloud_report(stage, "unexpected_response", response)
                raise CloudDiagnosticError("unexpected_response", "Unexpected live URI response")
            uri = data.get("uri") if isinstance(data, dict) else None
            if uri is None or uri == "":
                self._cloud_report(stage, "missing_uri", response)
                continue
            if not isinstance(uri, str):
                self._cloud_report(stage, "invalid_uri_type", response)
                raise CloudDiagnosticError("invalid_uri_type", "Live API returned an invalid URI type")
            if not trusted_hoymiles_url(uri):
                self._cloud_report(stage, "untrusted_uri", response)
                raise CloudDiagnosticError("untrusted_uri", "Live API returned an untrusted URI")
            pending = [self._cloud_log_states.pop((route, "missing_uri"), None)
                       for route in ("live_uri_mobile", "live_uri_web")]
            if any(item is not None for item in pending):
                CLOUD_LOGGER.info("Cloud live address recovered: stage=%s", stage)
            if stage == "live_uri_web" and self.supports_home_features:
                CLOUD_LOGGER.info("Live server address recovered using manufacturer web route")
            return uri
        raise CloudDiagnosticError("missing_uri", "Live API returned no URI (mobile and web routes)"
                                   if self.supports_home_features else "Live API returned no URI")

    async def async_live(self, station_id: int) -> dict[str, Any]:
        # Retain b4's bounded URI recovery. A reduced reply with a delay hint is
        # not an outage if that recovery returns actual telemetry in this call.
        previous_invalid_refresh = ("live_data", "invalid_live_data") in self._cloud_log_states
        delay_hint_retried = False
        await self.async_ensure_login()
        classification = (await self._async_enduser_classification(station_id)
                          if self.profile == "enduser" else None)
        if self.profile == "enduser" and getattr(self, "_live_station_id", None) != station_id:
            self._live_uri = None
            self._live_station_id = station_id
        for _attempt in range(2):
            try:
                if not self._live_uri:
                    self._live_uri = await self._get_live_uri(station_id)
                response = await self._json(self._live_uri, {"sid": station_id, "m": 0}
                                           if self.supports_home_features else {"m": 0, "t": 1})
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
                if self.profile == "enduser":
                    classification = await self._async_enduser_classification(station_id)
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
                if self.profile == "enduser":
                    try:
                        payload = parse_enduser_live(payload, classification)
                    except CloudDiagnosticError:
                        self._cloud_report("live_data", "invalid_live_data")
                        raise
                if delay_hint_retried:
                    CLOUD_LOGGER.info(
                        "Cloud live retry recovered: stage=live_data first_sample=delay_without_telemetry"
                    )
                # A valid sample ends the failure episode, even on a later poll.
                # Log recovery at the same visible level, then re-arm deduplication
                # so a separate future outage is not hidden forever.
                if self._cloud_log_states.pop(("live_data", "invalid_live_data"), None) is not None:
                    CLOUD_LOGGER.warning(
                        "Cloud request recovered: stage=live_data previous_reason=invalid_live_data recovery_scope=%s",
                        "later_refresh" if previous_invalid_refresh else "same_refresh",
                    )
                return payload
            has_delay_hint = (
                isinstance(payload, dict)
                and not any(key in payload for key in ("flow", "con", "power"))
                and type(payload.get("dly")) is int
                and 0 <= payload["dly"] <= 2**63 - 1
            )
            if _attempt == 0 and has_delay_hint:
                # Do not call a successful bounded recovery a failed refresh.
                # A second invalid reply still warns and fails normally below.
                delay_hint_retried = True
            else:
                self._cloud_report("live_data", "invalid_live_data", {"data": payload})
            self._live_uri = None
        raise CloudDiagnosticError("invalid_live_data", "Live response contains no usable telemetry after retry")

    async def _async_binary_data(self, url: str, payload: dict[str, Any]) -> bytes:
        """Read a bounded binary payload, rejecting redirects and JSON errors."""
        if not self.supports_home_features:
            raise CloudDiagnosticError("unsupported_profile_operation", "Home charts are unavailable for the Installer/Enduser monitoring profiles")
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
                raise HoymilesRateLimitError("Hoymiles chart rate limit reached", retry_after) from None
            raise HoymilesConnectionError(f"Chart request failed (HTTP {err.status})") from None
        except (ClientError, TimeoutError) as err:
            raise HoymilesConnectionError(
                f"Hoymiles chart request failed ({type(err).__name__})"
            ) from None
        if raw.lstrip().startswith(b"{"):
            try:
                self._unwrap(json.loads(raw))
            except (ValueError, TypeError, RecursionError) as err:
                raise HoymilesConnectionError("Invalid chart error response") from err
            raise HoymilesConnectionError("Chart endpoint returned no chart data")
        return raw

    async def async_module_values(
        self, station_id: int, device_id: int, port: int, date: str, *, latest_time=None
    ) -> dict[str, Any]:
        await self.async_ensure_login()
        raw = await self._async_binary_data(
            f"{DATA_BASE_URL}/pvmc/api/0/module_data/count_by_day_c",
            {"sid": station_id, "date": date,
             "mi_list": [{"id": device_id, "port": port}],
             "quota": ["MODULE_POWER", "MODULE_V", "MODULE_I"]},
        )
        try:
            return latest_module_samples(raw, device_id=device_id, port=port, latest_time=latest_time)
        except (ValueError, UnicodeError) as err:
            reason = err.reason if isinstance(err, ProtobufDecodeError) else "invalid_protobuf"
            raise HoymilesTelemetryError(reason) from None

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
            reason = err.reason if isinstance(err, ProtobufDecodeError) else "invalid_protobuf"
            raise HoymilesTelemetryError(reason) from None

    async def async_micro_details(self, station_id: int, device_ids: list[int], date: str, *, latest_time=None) -> dict[str, Any]:
        """Read the Home app's inverter chart, through the existing account budget."""
        if (type(station_id) is not int or station_id <= 0
                or not device_ids or len(device_ids) > 128
                or any(type(identity) is not int or identity <= 0 for identity in device_ids)
                or len(set(device_ids)) != len(device_ids)
                or not isinstance(date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date)):
            raise HoymilesConnectionError("Invalid microinverter chart target")
        await self.async_ensure_login()
        raw = await self._async_binary_data(
            f"{DATA_BASE_URL}/pvmc/api/0/micro_data/count_by_day_c",
            {"sid": station_id, "date": date, "mi_list": device_ids, "quota": list(MICRO_QUOTAS)},
        )
        try:
            return decode_micro_details(raw, device_ids, latest_time=latest_time)
        except (ValueError, UnicodeError) as err:
            reason = err.reason if isinstance(err, ProtobufDecodeError) else "invalid_protobuf"
            raise HoymilesTelemetryError(reason) from None

    async def _async_battery_settings_request(
        self, payload: dict[str, Any], request_method: str
    ) -> dict[str, Any]:
        """Submit and poll one read-only action-1013 request."""
        response = await self._json(
            f"{DATA_BASE_URL}/pvm-ctl/api/0/dev/setting/read",
            payload,
        )
        result = self._unwrap(response)

        if type(result) in (str, int):
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
            if isinstance(status, dict) and type(status.get("code")) is int and status["code"] == 2:
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
                status = _decode_json(status)
            if not isinstance(status, dict):
                raise HoymilesConnectionError("Work mode returned an invalid status")
            code = setting_integer(status.get("code"), 2**31 - 1)
            if code is None:
                raise HoymilesSettingsError("invalid_settings", "Invalid station command status", status)
            status = {**status, "code": code}
            if code == 2:
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
        if type(job_id) not in (str, int) or not str(job_id) or len(str(job_id)) > 256:
            raise HoymilesConnectionError("Work mode read returned no command id")
        status = await self._async_poll_station_setting_job(str(job_id))
        try:
            return parse_work_mode_settings(status)
        except BatterySettingsError as err:
            self._cloud_report("work_mode_read", "invalid_work_mode_settings", status)
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
        if type(result) not in (str, int) or not str(result) or len(str(result)) > 256:
            raise HoymilesConnectionError(
                "Battery settings write returned no command id"
            )
        status = await self._async_poll_battery_settings_job(str(result))
        if type(status.get("code")) is not int or status["code"] != 0:
            raise HoymilesConnectionError(
                "Battery settings write failed"
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
            except (HoymilesAuthError, HoymilesRateLimitError):
                raise
            except HoymilesConnectionError as err:
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
        except HoymilesRateLimitError:
            raise
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
        if len(targets) != 1:
            raise HoymilesConnectionError("Multiple compatible battery controllers; device settings are ambiguous") from station_error

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
            except HoymilesRateLimitError:
                raise
            except HoymilesConnectionError as device_error:
                errors.append(f"device settings request: {device_error}")

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
                    "Work mode write failed"
                )
            return
        response = await self._json(
            BATTERY_CONFIG_URL,
            {"sid": station_id, "mode": mode, "data": deepcopy(mode_data)},
        )
        result = self._unwrap(response)
        if result is False:
            raise HoymilesConnectionError("Battery configuration was rejected")

    async def async_output_power_settings(self, station_id):
        """Select the output action only from an explicit phase response."""
        await self.async_ensure_login()
        phases = self._unwrap(await self._json(
            f"{DATA_BASE_URL}/pvmc/api/0/station/phase/type_s_c", {"sid": station_id},
        ))
        phases = output_phases(phases)
        action = 1532 if phases else 84
        # Both app and web read action 1532 with sid only; type=0 belongs
        # exclusively to the output write, not the settings read.
        result = await self._async_output_power_action(station_id, action, {})
        if isinstance(result, str):
            try:
                result = _decode_json(result)
            except HoymilesConnectionError:
                raise HoymilesSettingsError("invalid_json", "Invalid output power JSON") from None
        return parse_output_settings(result, phases)

    async def async_write_output_power_settings(self, station_id, settings, value):
        settings = validate_output_settings(settings)
        data = output_write_data(settings, value)
        await self._async_output_power_action(station_id, settings["action"], data, write=True)

    async def _async_output_power_action(self, station_id, action, data, *, write=False):
        if type(action) is not int or action not in (84, 1532):
            raise HoymilesConnectionError("Unsupported output power action")
        await self.async_ensure_login()
        response = await self._json(
            STATION_SETTING_WRITE_URL if write else STATION_SETTING_READ_URL,
            {"action": action, "data": {**data, "sid": station_id}},
        )
        job_id = self._unwrap(response)
        if type(job_id) not in (str, int) or not str(job_id) or len(str(job_id)) > 256:
            raise HoymilesSettingsError("invalid_command_id", "Output power command returned no id")
        result = await self._async_poll_station_setting_job(str(job_id))
        if type(result.get("code")) is not int or result["code"] != 0:
            raise HoymilesSettingsError("command_failed", "Output power command failed", result)
        return result.get("data")

    async def async_cutoff_settings(self, target):
        """Mirror DisChargeActivity's device-addressed action 1537 read."""
        result = await self._async_cutoff_action(target, {})
        if isinstance(result, str):
            try:
                result = _decode_json(result)
            except HoymilesConnectionError:
                raise HoymilesSettingsError("invalid_json", "Invalid battery cutoff JSON") from None
        return parse_cutoffs(result)

    async def async_write_cutoff_settings(self, target, settings):
        await self._async_cutoff_action(target, parse_cutoffs(settings), write=True)

    async def _async_cutoff_action(self, target, data, *, write=False):
        addressing = self._light_target_payload(target, allow_empty_dtu=True)
        await self.async_ensure_login()
        response = await self._json(
            STATION_SETTING_WRITE_URL if write else STATION_SETTING_READ_URL,
            {"action": 1537, **addressing, "data": data},
        )
        job_id = self._unwrap(response)
        if type(job_id) not in (str, int) or not str(job_id) or len(str(job_id)) > 256:
            raise HoymilesSettingsError("invalid_command_id", "Battery cutoff command returned no id")
        result = await self._async_poll_station_setting_job(str(job_id))
        if type(result.get("code")) is not int or result["code"] != 0:
            raise HoymilesSettingsError("command_failed", "Battery cutoff command failed", result)
        return result.get("data")

    async def _async_device_settings_action(self, payload, *, write=False):
        """Use the manufacturer's device-settings transport, never a guessed station action."""
        if type(payload.get("action")) is not int or payload["action"] not in (1518, 1529):
            raise HoymilesConnectionError("Unsupported device settings action")
        await self.async_ensure_login()
        endpoint = "write" if write else "read"
        result = self._unwrap(await self._json(
            f"{DATA_BASE_URL}/pvm-ctl/api/0/dev/setting/{endpoint}", payload,
        ))
        if type(result) not in (str, int) or not str(result) or len(str(result)) > 256:
            raise HoymilesSettingsError("invalid_command_id", "Device settings returned no command id")
        for _ in range(BATTERY_SETTINGS_MAX_POLLS):
            await asyncio.sleep(BATTERY_SETTINGS_POLL_INTERVAL)
            status = self._unwrap(await self._json(
                f"{DATA_BASE_URL}/pvm-ctl/api/0/dev/setting/status", {"id": str(result)},
            ))
            if isinstance(status, str):
                status = _decode_json(status)
            if not isinstance(status, dict) or type(status.get("code")) is not int:
                raise HoymilesSettingsError("invalid_settings", "Invalid device settings status", status)
            if status["code"] == 2:
                continue
            if status["code"] != 0:
                raise HoymilesSettingsError("command_failed", "Device settings operation failed", status)
            return status.get("data")
        raise HoymilesConnectionError("Device settings operation timed out")

    async def async_heating_settings(self, station_id):
        return parse_heating(await self._async_device_settings_action(
            {"action": 1518, "data": {"sid": station_id}},
        ))

    async def async_write_heating_settings(self, station_id, enabled):
        data = parse_heating({"enable": enabled})
        await self._async_device_settings_action(
            {"action": 1518, "data": {"sid": station_id, **data}}, write=True,
        )

    @staticmethod
    def _light_target_payload(target, *, allow_empty_dtu=False):
        if (not isinstance(target, dict) or set(target) != {"dev_sn", "dtu_sn"}
                or not all(isinstance(value, str) and (
                    (allow_empty_dtu and key == "dtu_sn" and value == "")
                    or re.fullmatch(r"[0-9A-Fa-f]{12,24}", value))
                    for key, value in target.items())):
            raise HoymilesConnectionError("Invalid light/display target")
        return dict(target)

    async def async_light_display_settings(self, station_id, target):
        addressing = self._light_target_payload(target)
        data = await self._async_device_settings_action(
            {"action": 1529, **addressing, "sid": station_id},
        )
        if isinstance(data, str):
            try:
                data = _decode_json(data)
            except HoymilesConnectionError:
                raise HoymilesSettingsError("invalid_json", "Invalid light/display JSON") from None
        if not isinstance(data, dict) or ("sid" in data and setting_integer(data["sid"], station_id) != station_id):
            raise HoymilesSettingsError("invalid_station", "Invalid light/display station", data)
        data = {key: value for key, value in data.items() if key != "sid"}
        parse_lighting(data, addressing)
        return data

    async def async_write_light_display_settings(self, station_id, target, settings):
        addressing = self._light_target_payload(target)
        parse_lighting(settings, addressing)
        await self._async_device_settings_action(
            {"action": 1529, **addressing, "data": {**deepcopy(settings), "sid": station_id}}, write=True,
        )


def microinverters(tree: Any, *, children_only: bool = False, reject_ambiguous: bool = False) -> list[dict[str, Any]]:
    """Return type-3 devices from a nested Home device tree."""
    found: dict[int, dict[str, Any]] = {}
    ambiguous = set()

    def visit(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, dict):
            if (type(value.get("type")) is int and value["type"] == 3
                    and type(value.get("id")) is int and value["id"] > 0):
                previous = found.get(value["id"])
                if reject_ambiguous and previous is not None and (
                        inverter_model(previous) != inverter_model(value) or previous.get("sn") != value.get("sn")):
                    ambiguous.add(value["id"])
                found[value["id"]] = value
            for child in ([value.get("children")] if children_only else value.values()):
                visit(child)

    visit(tree)
    return [value for identity, value in found.items() if identity not in ambiguous]
