"""Account routing and expiry must not turn into repeated credential requests."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.hoymiles_home.api import HoymilesHomeClient
from custom_components.hoymiles_home.cloud_logging import CloudDiagnosticError, cloud_failure_reason
from custom_components.hoymiles_home.cloud_runtime import AccountRuntime
from custom_components.hoymiles_home.const import AUTH_BASE_URLS, DATA_BASE_URL
from custom_components.hoymiles_home.errors import HoymilesAuthError, HoymilesRateLimitError
from test_auth_redirects import SECRET, client_with, response

REGION = "https://euapi.hoymiles.com/iam/pub/0/c/region_c"


def ok(data):
    return response(data={"status": "0", "data": data})


def route(dc=1, base=None):
    return ok({"dc": dc, "login_url": base or AUTH_BASE_URLS[int(dc)]})


def pre(dc=1):
    return ok({"v": 3, "dc": dc, "a": "0123456789abcdef", "n": SECRET})


@pytest.mark.parametrize("dc", [0, 1, 4])
async def test_region_routes_challenge_and_login_with_consistent_identity(dc, caplog):
    api = client_with(route(dc), pre(dc), ok({"token": SECRET}), ok([]))
    with patch("custom_components.hoymiles_home.api.asyncio.to_thread", new=AsyncMock(return_value=b"hash")):
        await api.async_login()
    await api.async_device_tree(123)
    calls = api._session.post.call_args_list
    base = AUTH_BASE_URLS[dc]
    assert [c.args[0] for c in calls] == [REGION, base + "/iam/pub/3/auth/pre-insp",
        base + "/iam/pub/3/auth/login", DATA_BASE_URL + "/pvmc/api/0/station/select_device_c"]
    assert calls[0].kwargs["json"] == {"email": SECRET}
    for call in calls[:3]:
        assert "Authorization" not in call.kwargs["headers"]
        assert call.kwargs["allow_redirects"] is False
    for call in calls[1:]:
        assert call.kwargs["headers"]["User-Agent"].endswith(f"/159/{dc}")
    assert calls[-1].kwargs["headers"]["Authorization"] == SECRET
    assert api.runtime.request.call_count == 4
    assert SECRET not in caplog.text


@pytest.mark.parametrize("data", [None, [], {}, {"dc": 1}, {"dc": True, "login_url": AUTH_BASE_URLS[1]},
    {"dc": 2, "login_url": AUTH_BASE_URLS[1]}, {"dc": "01", "login_url": AUTH_BASE_URLS[1]},
    {"dc": 1, "login_url": AUTH_BASE_URLS[0]},
    *[{"dc": 1, "login_url": value} for value in [
        "https://evil.example/" + SECRET, "http://euapi.hoymiles.com",
        "https://euapi.hoymiles.com:443", "https://euapi.hoymiles.com?" + SECRET,
        "https://euapi.hoymiles.com/#" + SECRET, "https://euapi.hoymiles.com/iam/pub/3/auth/login",
        "https://euapi.hoymiles.com\n", "https://static.hoymiles.com", None, 1, {},
    ]],
])
async def test_invalid_region_stops_before_challenge_or_hash(data, caplog):
    api = client_with(ok(data))
    with patch("custom_components.hoymiles_home.api.asyncio.to_thread", new=AsyncMock()) as worker:
        with pytest.raises(CloudDiagnosticError, match="routing"):
            await api.async_login()
    worker.assert_not_awaited()
    assert api._session.post.call_count == 1
    assert "reason=invalid_auth_routing" in caplog.text
    assert SECRET not in caplog.text


@pytest.mark.parametrize("dc", ["0", "1", "4"])
async def test_short_dc_strings_and_trailing_root_are_accepted(dc):
    api = client_with(route(dc, AUTH_BASE_URLS[int(dc)] + "/"), pre(int(dc)), ok({"token": SECRET}))
    await api.async_login()
    assert api._session.post.call_args_list[1].args[0].startswith(AUTH_BASE_URLS[int(dc)])


@pytest.mark.parametrize("step", ["region", "pre", "login"])
@pytest.mark.parametrize("kind", ["reject", "rate", "expired"])
async def test_rejection_at_each_auth_stage_has_no_fallback_or_repeat(step, kind, caplog):
    status, message, error = {
        "reject": (1, "Synthetic rejection", CloudDiagnosticError),
        "rate": (1, "The number of logins exceeds the daily maximum limit", HoymilesRateLimitError),
        "expired": (100, SECRET, HoymilesAuthError),
    }[kind]
    preceding = [] if step == "region" else [route()] if step == "pre" else [route(), pre()]
    api = client_with(*preceding, response(data={"status": status, "message": message, "data": SECRET}))
    with pytest.raises(error):
        await api.async_login()
    assert api._session.post.call_count == len(preceding) + 1
    assert SECRET not in caplog.text
    if kind == "rate":
        with pytest.raises(HoymilesRateLimitError):
            async with AccountRuntime.request(api.runtime):
                pytest.fail("Account pause must apply to other requests")


async def test_login_success_does_not_mask_refused_station_or_choose_web_profile(caplog):
    api = client_with(route(), pre(), ok({"token": SECRET}),
        response(data={"status": 1, "data": SECRET, "message": "Synthetic rejection"}))
    await api.async_login()
    with pytest.raises(CloudDiagnosticError):
        await api.async_device_tree(123)
    assert api._session.post.call_count == 4
    assert "stage=station_validation reason=cloud_rejected" in caplog.text
    assert SECRET not in caplog.text


@pytest.mark.parametrize("path,payload", [
    ("/pvmc/api/0/station/select_device_c", {"sid": 123}),
    ("/pvmc/api/0/station_ctl/write_c", {"action": 1537, "data": {"sl": 20, "sh": 95}}),
])
@pytest.mark.parametrize("status", [100, "100"])
async def test_expiry_invalidates_shared_session_and_never_replays_write(path, payload, status, caplog):
    api = client_with(response(data={"status": status, "message": SECRET, "data": {"token": SECRET}}))
    other = HoymilesHomeClient(api._session, SECRET, SECRET, runtime=api.runtime)
    api._live_uri = "https://neapi.hoymiles.com/" + SECRET
    with pytest.raises(HoymilesAuthError):
        await api._json(DATA_BASE_URL + path, payload)
    assert other._token is None
    assert other._token_expires < datetime.now(UTC)
    assert api._live_uri is None
    assert api._session.post.call_count == 1
    assert "reason=session_expired" in caplog.text
    assert SECRET not in caplog.text


@pytest.mark.parametrize("message,reason", [
    ("Your app version is low. Please update to the latest version.", "client_update_required"),
    ("Can only login to the S-Miles Home.", "home_app_required"),
    ("The account can only be used for logging in to the S-Miles Home app.", "home_app_required"),
    (SECRET, "cloud_rejected"),
])
async def test_known_errors_log_fixed_categories_only(message, reason, caplog):
    api = client_with(response(data={"status": 1, "message": message, "data": SECRET}))
    raw = await api._json(REGION, {"email": SECRET})
    with pytest.raises((CloudDiagnosticError, HoymilesAuthError)):
        api._unwrap(raw)
    assert f"reason={reason}" in caplog.text
    assert SECRET not in caplog.text
    assert message not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


def test_success_boolean_is_not_a_success_status():
    assert cloud_failure_reason({"status": False}) == "cloud_rejected"
    assert cloud_failure_reason({"status": True}) == "cloud_rejected"


@pytest.mark.parametrize("status", [302, 307])
async def test_region_redirect_is_not_an_auth_challenge_redirect(status, caplog):
    api = client_with(response(status, location=REGION.replace("euapi", "neapi")))
    with pytest.raises(CloudDiagnosticError, match="redirected"):
        await api.async_login()
    assert api._session.post.call_count == 1
    assert "Authorization" not in api._session.post.call_args.kwargs["headers"]
    assert SECRET not in caplog.text


async def test_region_http_rate_limit_stops_all_followup_requests(caplog):
    api = client_with(response(429))
    with pytest.raises(HoymilesRateLimitError):
        await api.async_login()
    assert api._session.post.call_count == 1
    assert api._token is None
    assert "stage=login_region reason=http_error http_status=429" in caplog.text
    assert SECRET not in caplog.text


async def test_region_transport_failure_does_not_fall_back_to_old_entry():
    api = client_with()
    api._session.post.return_value.__aenter__.side_effect = TimeoutError(SECRET)
    from custom_components.hoymiles_home.errors import HoymilesConnectionError
    with pytest.raises(HoymilesConnectionError):
        await api.async_login()
    assert api._session.post.call_count == 1
    assert api._token is None


async def test_selected_identity_is_shared_with_other_station_clients():
    api = client_with(route(0), pre(0), ok({"token": SECRET}))
    other = HoymilesHomeClient(api._session, SECRET, SECRET, runtime=api.runtime)
    await api.async_login()
    assert other.headers["User-Agent"].endswith("/159/0")
    assert other._token == SECRET


@pytest.mark.parametrize("status", ["00", "0100", False, True, 0.0, 100.0, None])
def test_malformed_envelope_status_does_not_acquire_success_or_expiry_semantics(status):
    assert cloud_failure_reason({"status": status}) == "cloud_rejected"


async def test_expired_live_read_uses_existing_single_reauthentication_path():
    uri = "https://neapi.hoymiles.com/live"
    api = client_with(ok({"uri": uri}), response(data={"status": 100, "data": None}),
        route(0), pre(0), ok({"token": SECRET}), ok({"uri": uri}), ok({"con": 1, "power": {"pv": 42}}))
    assert (await api.async_live(123))["power"]["pv"] == 42
    assert [c.args[0] for c in api._session.post.call_args_list] == [
        DATA_BASE_URL + "/pvmc/api/0/station/get_sd_uri_c", uri, REGION,
        AUTH_BASE_URLS[0] + "/iam/pub/3/auth/pre-insp", AUTH_BASE_URLS[0] + "/iam/pub/3/auth/login",
        DATA_BASE_URL + "/pvmc/api/0/station/get_sd_uri_c", uri,
    ]


async def test_expired_command_status_does_not_resend_write_or_login():
    api = client_with(ok("synthetic-job"), response(data={"status": 100, "data": None}))
    with pytest.raises(HoymilesAuthError):
        await api.async_write_cutoff_settings(
            {"dev_sn": "ABCDEF000001", "dtu_sn": "ABCDEF000002"}, {"sl": 20, "sh": 95})
    calls = api._session.post.call_args_list
    assert len(calls) == 2
    assert calls[0].args[0].endswith("/station_ctl/write_c")
    assert calls[1].args[0].endswith("/station_ctl/setting_status_c")
    assert api._token is None
