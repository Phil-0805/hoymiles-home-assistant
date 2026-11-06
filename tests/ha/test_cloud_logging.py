"""Setup diagnostics must identify stages without logging account/cloud content."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
import logging

import pytest
from aiohttp import ClientConnectionError, ClientResponseError

from custom_components.hoymiles_home.api import HoymilesHomeClient
from custom_components.hoymiles_home.cloud_logging import log_failure, response_summary
from custom_components.hoymiles_home.errors import HoymilesAuthError, HoymilesConnectionError, HoymilesRateLimitError

SECRET = "PRIVATE_ACCOUNT_TOKEN_SERIAL_PASSWORD_URL"
MOBILE = "https://neapi.hoymiles.com/pvmc/api/0/station/get_sd_uri_c"
WEB = "https://neapi.hoymiles.com/pvm/api/0/station/get_sd_uri"
LIVE = "https://neapi.hoymiles.com/live?signature=" + SECRET


def client(*responses):
    api = HoymilesHomeClient(MagicMock(), SECRET, SECRET)
    api._token = SECRET
    api._token_expires = datetime.now(UTC) + timedelta(hours=1)
    api._json = AsyncMock(side_effect=responses)
    return api


def ok(data):
    return {"status": "0", "data": data, "message": SECRET}


@pytest.mark.parametrize("data", [None, {}, {"uri": None}, {"uri": ""}])
async def test_missing_mobile_uri_recovers_with_verified_web_route(data, caplog):
    caplog.set_level(logging.INFO)
    api = client(ok(data), ok({"uri": LIVE}), ok({"con": 1, "power": {"pv": 42}}))
    assert (await api.async_live(123))["power"]["pv"] == 42
    assert api._json.call_args_list[0].args == (MOBILE, {"sid": 123})
    assert api._json.call_args_list[1].args == (WEB, {"sid": 123})
    assert api._json.call_args_list[2].args == (LIVE, {"sid": 123, "m": 0})
    assert "stage=live_uri_mobile reason=missing_uri" in caplog.text
    assert "recovered" in caplog.text
    assert SECRET not in caplog.text


async def test_mobile_success_never_probes_web():
    api = client(ok({"uri": LIVE}))
    assert await api._get_live_uri(123) == LIVE
    assert api._json.await_count == 1


@pytest.mark.parametrize("data,reason", [({"uri": False}, "invalid_uri_type"),
    ({"uri": "https://evil.example/" + SECRET}, "untrusted_uri"),
    ({"uri": "http://neapi.hoymiles.com/" + SECRET}, "untrusted_uri")])
async def test_invalid_uri_never_uses_fallback_or_exposes_value(data, reason, caplog):
    api = client(ok(data))
    with pytest.raises(HoymilesConnectionError):
        await api._get_live_uri(123)
    assert api._json.await_count == 1
    assert f"reason={reason}" in caplog.text
    assert SECRET not in caplog.text


@pytest.mark.parametrize("failure", [HoymilesAuthError(SECRET), HoymilesRateLimitError(SECRET),
                                      HoymilesConnectionError(SECRET)])
async def test_mobile_transport_auth_or_rate_failure_never_probes_web(failure):
    api = client(failure)
    with pytest.raises(type(failure)):
        await api._get_live_uri(123)
    assert api._json.await_count == 1


async def test_both_routes_missing_remain_bounded_and_warnings_deduplicated(caplog):
    api = client(*[ok(None)] * 4)
    with pytest.raises(HoymilesConnectionError, match="mobile and web"):
        await api.async_live(123)
    assert api._json.await_count == 4
    assert caplog.text.count("stage=live_uri_mobile") == 1
    assert caplog.text.count("stage=live_uri_web") == 1
    assert SECRET not in caplog.text


@pytest.mark.parametrize("code", [SECRET, True, {}, "9" * 100, -1])
def test_summary_never_exposes_arbitrary_server_fields_or_status(code):
    summary = response_summary({"status": code, "data": {"uri": LIVE, SECRET: SECRET}, "message": SECRET})
    assert SECRET not in summary
    assert "cloud_status=unavailable" in summary
    assert "data_type=object uri=string" in summary


@pytest.mark.parametrize("error,reason", [(HoymilesAuthError(SECRET), "authentication"),
    (HoymilesConnectionError(SECRET), "connection"), (RuntimeError(SECRET), "unexpected_error")])
def test_setup_error_never_logs_exception_text_or_traceback(error, reason, caplog):
    log_failure("login", error)
    assert f"stage=login reason={reason}" in caplog.text
    assert SECRET not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.parametrize("failure,reason", [(ClientConnectionError(SECRET), "transport_error"),
                                           (TimeoutError(SECRET), "timeout")])
async def test_real_http_wrapper_logs_fixed_transport_reason(failure, reason, caplog):
    api = HoymilesHomeClient(MagicMock(), SECRET, SECRET)
    api._session.post.return_value.__aenter__.side_effect = failure
    with pytest.raises(HoymilesConnectionError):
        await api._json(MOBILE, {"sid": 123})
    assert f"stage=live_uri_mobile reason={reason}" in caplog.text
    assert SECRET not in caplog.text


async def test_real_http_wrapper_logs_numeric_http_status_only(caplog):
    api = HoymilesHomeClient(MagicMock(), SECRET, SECRET)
    failure = ClientResponseError(MagicMock(), (), status=403, message=SECRET, headers={SECRET: SECRET})
    api._session.post.return_value.__aenter__.side_effect = failure
    with pytest.raises(HoymilesConnectionError):
        await api._json(MOBILE, {"sid": 123})
    assert "stage=live_uri_mobile reason=http_error http_status=403" in caplog.text
    assert SECRET not in caplog.text


@pytest.mark.parametrize("data", [[], "PRIVATE_ACCOUNT_TOKEN_SERIAL_PASSWORD_URL", 123, True])
async def test_wrong_uri_response_shape_does_not_trigger_web_fallback(data, caplog):
    api = client(ok(data))
    with pytest.raises(HoymilesConnectionError, match="Unexpected live URI"):
        await api._get_live_uri(123)
    assert api._json.await_count == 1
    assert "reason=unexpected_response" in caplog.text
    assert SECRET not in caplog.text


async def test_actual_cloud_rejection_logs_numeric_code_and_shape_not_message(caplog):
    import json
    api = HoymilesHomeClient(MagicMock(), SECRET, SECRET)
    response = MagicMock(status=200)
    async def chunks(*args):
        yield json.dumps({"status": 1234, "message": SECRET, "data": {SECRET: SECRET}}).encode()
    response.content.iter_chunked = chunks
    api._session.post.return_value.__aenter__.return_value = response
    raw = await api._json(MOBILE, {"sid": 123})
    with pytest.raises((HoymilesConnectionError, HoymilesAuthError)):
        api._unwrap(raw)
    assert "stage=live_uri_mobile reason=cloud_rejected cloud_status=1234" in caplog.text
    assert SECRET not in caplog.text


async def test_login_challenge_invalid_is_identified_without_values(caplog):
    api = client(ok({"v": 3, "dc": 1, "a": SECRET, "n": SECRET}))
    with pytest.raises(HoymilesAuthError):
        await api.async_login()
    assert "stage=login_challenge reason=invalid_challenge" in caplog.text
    assert SECRET not in caplog.text


async def test_login_missing_token_is_identified_without_values(caplog):
    api = client(ok({"v": 3, "dc": 1, "a": "0123456789abcdef", "n": SECRET}), ok({SECRET: SECRET}))
    with pytest.raises(HoymilesAuthError):
        await api.async_login()
    assert "stage=login reason=missing_token" in caplog.text
    assert SECRET not in caplog.text


async def test_config_flow_logs_failure_even_if_no_entry_exists(hass, client, caplog):
    from homeassistant.config_entries import SOURCE_USER
    from custom_components.hoymiles_home.const import DOMAIN
    client.async_login.side_effect = HoymilesConnectionError(SECRET)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"username": SECRET, "password": SECRET})
    assert result["errors"] == {"base": "cannot_connect"}
    assert "stage=login reason=connection" in caplog.text
    assert SECRET not in caplog.text


@pytest.mark.parametrize("body,reason", [(b"PRIVATE_ACCOUNT_TOKEN_SERIAL_PASSWORD_URL", "invalid_json"),
                                         (b"[]", "unexpected_response")])
async def test_invalid_json_and_wrong_root_are_distinguished(body, reason, caplog):
    api = HoymilesHomeClient(MagicMock(), SECRET, SECRET)
    response = MagicMock(status=200)
    async def chunks(*args):
        yield body
    response.content.iter_chunked = chunks
    api._session.post.return_value.__aenter__.return_value = response
    with pytest.raises(HoymilesConnectionError):
        await api._json(MOBILE, {"sid": 123})
    assert f"stage=live_uri_mobile reason={reason}" in caplog.text
    assert SECRET not in caplog.text


@pytest.mark.parametrize("payload,expected", [
    ({"power": {SECRET: SECRET}, SECRET: SECRET}, "data_type=object flow_type=missing con_type=missing con_state=missing power_type=object"),
    ({"flow": SECRET, "con": SECRET}, "data_type=object flow_type=string con_type=string con_state=invalid power_type=missing"),
    ({"con": True}, "data_type=object flow_type=missing con_type=boolean con_state=invalid power_type=missing"),
    ({"con": None, "flow": None}, "data_type=object flow_type=null con_type=null con_state=invalid power_type=missing"),
    ([SECRET], "data_type=array flow_type=missing con_type=missing con_state=missing power_type=missing"),
])
def test_invalid_live_summary_reports_only_relevant_types(payload, expected, caplog):
    api = client()
    api._cloud_report("live_data", "invalid_live_data", {"data": payload})
    assert expected in caplog.text
    assert "cloud_status" not in caplog.text
    assert "uri=" not in caplog.text
    assert SECRET not in caplog.text


async def test_recovery_after_retry_is_visible_once_without_info_logging(caplog):
    api = client(ok({"power": {SECRET: SECRET}}), ok({"uri": LIVE}), ok({"con": 1}), ok({"con": 1}))
    api._live_uri = LIVE
    assert await api.async_live(123) == {"con": 1}
    assert await api.async_live(123) == {"con": 1}
    assert "flow_type=missing con_type=missing" in caplog.text
    assert caplog.text.count("Cloud request recovered: stage=live_data") == 1
    assert "uri=missing" not in caplog.text
    assert SECRET not in caplog.text


async def test_persistent_live_failure_has_no_false_recovery_and_new_episode_is_logged(caplog):
    api = client(ok({}), ok({"uri": LIVE}), ok({}),
                 ok({"uri": LIVE}), ok({"con": 0}),
                 ok({}), ok({"uri": LIVE}), ok({"flow": []}))
    api._live_uri = LIVE
    with pytest.raises(HoymilesConnectionError):
        await api.async_live(123)
    assert caplog.text.count("reason=invalid_live_data") == 1
    assert "Cloud request recovered" not in caplog.text
    # A valid offline response is accepted by the existing contract too.
    assert await api.async_live(123) == {"con": 0}
    assert caplog.text.count("Cloud request recovered") == 1
    assert await api.async_live(123) == {"flow": []}
    assert caplog.text.count("Cloud request failed: stage=live_data reason=invalid_live_data") == 2
    assert caplog.text.count("Cloud request recovered") == 2
    assert SECRET not in caplog.text


async def test_healthy_live_samples_do_not_log_recovery(caplog):
    api = client(ok({"con": 1}))
    api._live_uri = LIVE
    await api.async_live(123)
    assert "Cloud request recovered" not in caplog.text
