"""Installer protocol from the static V3.14.0 APK; no account requests."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType

from custom_components.hoymiles_home.api import HoymilesHomeClient
from custom_components.hoymiles_home.cloud_runtime import AccountRuntime
from custom_components.hoymiles_home.const import DOMAIN
from custom_components.hoymiles_home.coordinator import HoymilesHomeCoordinator
from custom_components.hoymiles_home.errors import HoymilesConnectionError, HoymilesAuthError, HoymilesRateLimitError
from test_auth_redirects import response

SECRET = "PRIVATE_ACCOUNT_PASSWORD_TOKEN_NONCE"
BASE = "https://neapi.hoymiles.com"
PRE = BASE + "/iam/pub/3/auth/pre-insp"
LOGIN = BASE + "/iam/pub/3/auth/login"
LIVE = BASE + "/live?signature=" + SECRET


def ok(data):
    return response(data={"status": 0, "data": data})


def client(*responses, runtime=None):
    api = HoymilesHomeClient(MagicMock(), SECRET, "password", runtime=runtime, profile="installer")
    api.runtime.request = MagicMock()
    api.runtime.request.return_value.__aenter__ = AsyncMock()
    api.runtime.request.return_value.__aexit__ = AsyncMock(return_value=False)
    api._session.post.return_value.__aenter__.side_effect = responses
    return api


def ready(*responses):
    api = client(*responses)
    api._token = SECRET
    api._token_expires = datetime.now(UTC) + timedelta(hours=1)
    return api


@pytest.mark.parametrize("version,expected", [
    (1, "5f4dcc3b5aa765d61d8327deb882cf99"),
    (2, "5f4dcc3b5aa765d61d8327deb882cf99.XohImNooBHFR0OVvjcYpJ3NgPQ1qq73WKhHvch0VQtg="),
    (3, "68617368"),
])
@pytest.mark.parametrize("dc", [0, 1, "0", "1"])
async def test_explicit_installer_algorithm_and_identity_without_region_or_fallback(version, expected, dc, caplog):
    api = client(ok({"v": version, "dc": dc, "a": "0123456789abcdef", "n": SECRET}), ok({"token": SECRET}))
    with patch("custom_components.hoymiles_home.api.asyncio.to_thread", new=AsyncMock(return_value=b"hash")) as worker:
        await api.async_login()
    assert worker.await_count == (1 if version == 3 else 0)
    calls = api._session.post.call_args_list
    assert [c.args[0] for c in calls] == [PRE, LOGIN]
    assert calls[0].kwargs["headers"]["User-Agent"] == "smc/ad/3.14.0/159/0"
    assert calls[1].kwargs["headers"]["User-Agent"] == f"smc/ad/3.14.0/159/{dc}"
    assert calls[0].kwargs["json"] == {"u": SECRET}
    assert calls[1].kwargs["json"] == {"u": SECRET, "ch": expected, "n": SECRET}
    for c in calls:
        assert "Authorization" not in c.kwargs["headers"] and c.kwargs["allow_redirects"] is False
    assert api.runtime.request.call_count == 2
    assert SECRET not in caplog.text


@pytest.mark.parametrize("update", [{"dc": None}, {"dc": True}, {"dc": 2}, {"dc": 4}, {"dc": 41},
    {"v": None}, {"v": True}, {"v": 4}, {"n": None}, {"a": "not-hex"}])
async def test_unsupported_installer_challenge_never_guesses_protocol_or_region(update, caplog):
    api = client(ok({"v": 3, "dc": 0, "a": "0123456789abcdef", "n": SECRET, **update}))
    with pytest.raises((HoymilesConnectionError, HoymilesAuthError)):
        await api.async_login()
    assert api._session.post.call_count == 1
    assert SECRET not in caplog.text


@pytest.mark.parametrize("where", ["pre", "login"])
async def test_rejection_does_not_try_home_profile_or_another_host(where, caplog):
    responses = [] if where == "pre" else [ok({"v": 1, "dc": 0, "n": SECRET})]
    api = client(*responses, response(data={"status": 1, "message": "Synthetic rejection", "data": SECRET}))
    with pytest.raises(HoymilesConnectionError):
        await api.async_login()
    assert api._session.post.call_count == len(responses) + 1
    assert "client_profile=installer" in caplog.text and SECRET not in caplog.text


async def test_profiles_share_account_pacing_lock_and_pause_but_not_tokens():
    runtime = AccountRuntime()
    home = HoymilesHomeClient(MagicMock(), SECRET, SECRET, runtime)
    installer = HoymilesHomeClient(MagicMock(), SECRET, SECRET, runtime, profile="installer")
    other = HoymilesHomeClient(MagicMock(), SECRET, SECRET, runtime, profile="installer")
    home._token = "home-token"
    installer._token = "installer-token"
    assert other._token == "installer-token" and home._token == "home-token"
    assert home._lock is installer._lock
    runtime.pause(60)
    for api in (home, installer):
        with pytest.raises(HoymilesRateLimitError):
            async with api.runtime.request():
                pytest.fail("Account pause must apply to both profiles")


async def test_installer_read_path_uses_verified_payloads_and_shared_model():
    tree = [{"id": 456, "type": 3, "station_id": 123, "model_no": "synthetic", "children": None}]
    api = ready(ok({"list": [{"id": 123, "name": "synthetic", "dc": "0"}]}), ok(tree),
        ok({"uri": LIVE}), ok({"con": 1, "flow": [], "power": {"pv": "42"}, "dly": 5000}),
        ok({"today_eq": "1.2", "month_eq": "3.4"}))
    assert await api.async_list_stations() == [{"sid": 123, "name": "synthetic"}]
    assert await api.async_device_tree(123) == tree
    assert (await api.async_live(123))["power"]["pv"] == "42"
    assert (await api.async_station_realtime(123))["today_eq"] == "1.2"
    calls = api._session.post.call_args_list
    assert [(c.args[0], c.kwargs["json"]) for c in calls] == [
        (BASE + "/pvm/api/0/station/select_by_page", {"page": 1, "page_size": 100}),
        (BASE + "/pvm/api/0/station/select_device_of_tree", {"id": 123}),
        (BASE + "/pvm/api/0/station/get_sd_uri", {"sid": 123}),
        (LIVE, {"m": 0, "t": 1}),
        (BASE + "/pvm-data/api/0/station/data/count_station_real_data", {"sid": 123}),
    ]
    assert all(c.kwargs["headers"]["Authorization"] == SECRET for c in calls)


@pytest.mark.parametrize("tree", [{}, [None], [{"id": True, "type": 3}], [{"id": 0, "type": 3}],
    [{"id": 1, "type": 3, "station_id": 999}], [{"id": 1, "type": 3, "children": {}}],
    [{"id": 1, "type": 3, "sn": "A"}, {"id": 1, "type": 3, "sn": "B"}]])
async def test_invalid_tree_identity_is_not_used(tree):
    api = ready(ok(tree))
    with pytest.raises(HoymilesConnectionError):
        await api.async_device_tree(123)


@pytest.mark.parametrize("path", ["/pvmc/api/0/station_ctl/write_c", "/pvm-ctl/api/0/dev/setting/write",
    "/pvmc/api/0/station/select_device_c", "/unknown"])
async def test_unverified_commands_and_home_routes_never_reach_http(path):
    api = ready()
    with pytest.raises(HoymilesConnectionError, match="Installer"):
        await api._json(BASE + path, {"action": 83, "data": {"sid": 123}})
    api._session.post.assert_not_called()


async def test_installer_coordinator_never_schedules_home_features(hass):
    api = ready()
    api.async_live = AsyncMock(return_value={"con": 1, "power": {"pv": 42}, "dly": 5000})
    api.async_device_tree = AsyncMock(return_value=[{"id": 456, "type": 3}])
    api.async_station_realtime = AsyncMock(return_value={"today_eq": 1})
    coordinator = HoymilesHomeCoordinator(hass, api, 123, battery_controls=True, device_controls=True,
        battery_temperatures=True, inverter_details=True)
    coordinator.module_polling.start = MagicMock()
    result = await coordinator._async_update_data()
    assert result["live"]["power"]["pv"] == 42
    assert not coordinator.battery_controls and not coordinator.device_controls
    assert coordinator._start_battery_settings_refresh() is None
    assert coordinator.battery_telemetry.enabled is False
    coordinator.module_polling.start.assert_not_called()
    api._session.post.assert_not_called()
    await coordinator.async_shutdown()


async def test_setup_persists_installer_choice_without_changing_station_identity(hass, client):
    with patch("custom_components.hoymiles_home.config_flow.HoymilesHomeClient") as constructor:
        constructor.return_value = client
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {
            "username": "synthetic@example.invalid", "password": SECRET, "client_profile": "installer"})
        assert result["step_id"] == "select_station"
        assert constructor.call_args.kwargs == {"profile": "installer"}
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"station_id": "123"})
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["data"]["client_profile"] == "installer"
        assert result["result"].unique_id == "synthetic@example.invalid_123"


async def test_reauthentication_can_switch_profile_without_recreating_entry(hass, client):
    from homeassistant.config_entries import SOURCE_REAUTH
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    entry = MockConfigEntry(domain=DOMAIN, unique_id="synthetic_123", data={
        "username": "synthetic@example.invalid", "password": SECRET, "station_id": 123})
    entry.add_to_hass(hass)
    with patch("custom_components.hoymiles_home.config_flow.HoymilesHomeClient") as constructor, \
            patch.object(hass.config_entries, "async_reload", new=AsyncMock(return_value=True)):
        constructor.return_value = client
        result = await hass.config_entries.flow.async_init(DOMAIN, context={
            "source": SOURCE_REAUTH, "entry_id": entry.entry_id}, data=entry.data)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {
            "password": SECRET, "client_profile": "installer"})
        await hass.async_block_till_done()
    assert result["reason"] == "reauth_successful"
    assert entry.unique_id == "synthetic_123" and entry.data["station_id"] == 123
    assert entry.data["client_profile"] == "installer"
    assert constructor.call_args.kwargs == {"profile": "installer"}


async def test_installer_options_do_not_offer_unimplemented_controls(hass):
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    entry = MockConfigEntry(domain=DOMAIN, data={"username": "synthetic@example.invalid", "password": SECRET,
        "station_id": 123, "client_profile": "installer"})
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    fields = {key.schema for key in result["data_schema"].schema}
    assert "battery_controls" not in fields and "device_controls" not in fields
    assert "inverter_details" not in fields
    assert "station_timezone" in fields and "pv_power_source" in fields


def test_installer_metadata_cannot_impersonate_a_tree_device():
    from custom_components.hoymiles_home.api import microinverters
    tree = [{"id": 1, "type": 2, "extend_data": {"id": 999, "type": 3},
        "children": [{"id": 456, "type": 3, "model_no": "synthetic"}]}]
    assert [node["id"] for node in microinverters(tree, children_only=True)] == [456]


@pytest.mark.parametrize("status", [401, 429])
async def test_installer_auth_http_error_stops_without_other_profile(status, caplog):
    from aiohttp import ClientResponseError
    api = client()
    api._session.post.return_value.__aenter__.side_effect = ClientResponseError(
        MagicMock(), (), status=status, message=SECRET, headers={"Retry-After": "60"})
    with pytest.raises(HoymilesAuthError if status == 401 else HoymilesRateLimitError):
        await api.async_login()
    assert api._session.post.call_count == 1 and SECRET not in caplog.text


@pytest.mark.parametrize("flag", [1, 2, True, "private-flag"])
async def test_interactive_installer_account_state_stops_before_password_login(flag, caplog):
    api = client(ok({"v": 3, "dc": 0, "a": "0123456789abcdef", "n": SECRET, "f": flag}))
    with pytest.raises(HoymilesConnectionError, match="official app"):
        await api.async_login()
    assert api._session.post.call_count == 1
    assert "reason=account_action_required" in caplog.text
    assert SECRET not in caplog.text and "private-flag" not in caplog.text


async def test_installer_v1_password_uses_utf8_without_trimming():
    api = client(ok({"v": 1, "dc": 0}), ok({"token": SECRET}))
    api._password = " pässwörd🔋 "
    await api.async_login()
    assert api._session.post.call_args.kwargs["json"]["ch"] == "fd87faa579d0b4c1e62eabe310d57681"
