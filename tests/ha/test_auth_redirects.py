"""Manufacturer-style auth redirects stay bounded, private and strictly scoped."""

from datetime import UTC, datetime, timedelta
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import ClientResponseError

from custom_components.hoymiles_home.api import HoymilesHomeClient
from custom_components.hoymiles_home.errors import HoymilesConnectionError, HoymilesRateLimitError
from custom_components.hoymiles_home.security import trusted_auth_redirect

SECRET = "PRIVATE_EMAIL_PASSWORD_TOKEN_LOCATION"
PRE = "https://euapi.hoymiles.com/iam/pub/3/auth/pre-insp"
LOGIN = "https://euapi.hoymiles.com/iam/pub/3/auth/login"


def response(status=200, data=None, location=None):
    result = MagicMock(status=status, headers={} if location is None else {"Location": location})
    async def chunks(*args):
        yield json.dumps(data or {"status": "0", "data": {}}).encode()
    result.content.iter_chunked = chunks
    if status == 429:
        result.raise_for_status.side_effect = ClientResponseError(MagicMock(), (), status=429,
                                                                 headers={"Retry-After": "60"})
    return result


def client_with(*responses):
    api = HoymilesHomeClient(MagicMock(), SECRET, SECRET)
    api._token = SECRET
    api._token_expires = datetime.now(UTC) + timedelta(hours=1)
    # Avoid real delays while still asserting each request uses the shared budget.
    api.runtime.request = MagicMock()
    api.runtime.request.return_value.__aenter__ = AsyncMock()
    api.runtime.request.return_value.__aexit__ = AsyncMock(return_value=False)
    api._session.post.return_value.__aenter__.side_effect = responses
    return api


@pytest.mark.parametrize("source", [PRE, LOGIN])
@pytest.mark.parametrize("status", [302, 307])
@pytest.mark.parametrize("host", ["neapi.hoymiles.com", "indapi.hoymiles.com"])
async def test_auth_redirect_keeps_post_and_body_and_never_forwards_old_token(source, status, host, caplog):
    target = source.replace("euapi.hoymiles.com", host)
    final = {"status": "0", "data": {"token": SECRET}}
    api = client_with(response(status, location=target), response(data=final))
    payload = {"u": SECRET, "ch": SECRET, "n": SECRET}
    assert await api._json(source, payload) == final
    calls = api._session.post.call_args_list
    assert len(calls) == 2
    assert calls[0].args == (source,)
    assert calls[1].args == (target,)
    for call in calls:
        assert call.kwargs["json"] == payload
        assert call.kwargs["allow_redirects"] is False
        assert "Authorization" not in call.kwargs["headers"]
    assert api.runtime.request.call_count == 2
    assert SECRET not in caplog.text


@pytest.mark.parametrize("target", [
    None, "", "/iam/pub/3/auth/pre-insp", "http://neapi.hoymiles.com/iam/pub/3/auth/pre-insp",
    "https://evil.example/iam/pub/3/auth/pre-insp",
    "https://euapi.hoymiles.com.evil.example/iam/pub/3/auth/pre-insp",
    "https://static.hoymiles.com/iam/pub/3/auth/pre-insp",
    "https://neapi-test.hoymiles.com/iam/pub/3/auth/pre-insp",
    "https://neapi.hoymiles.com/iam/pub/3/auth/login",
    "https://neapi.hoymiles.com/iam/pub/3/auth/pre-insp?token=" + SECRET,
    "https://neapi.hoymiles.com/iam/pub/3/auth/pre-insp#" + SECRET,
    "https://" + SECRET + "@neapi.hoymiles.com/iam/pub/3/auth/pre-insp",
    "https://neapi.hoymiles.com:444/iam/pub/3/auth/pre-insp",
    "https://neapi.hoymiles.com/iam/pub/3/auth/pre-insp\n",
    "https://evil.example/iam/pub/3/auth/pre-insp?times=1",
    "https://static.hoymiles.com/iam/pub/3/auth/pre-insp?times=1",
    "http://neapi.hoymiles.com/iam/pub/3/auth/pre-insp?times=1",
    "https://neapi.hoymiles.com:444/iam/pub/3/auth/pre-insp?times=1",
    "https://neapi.hoymiles.com/iam/pub/3/auth/login?times=1",
    "https://" + SECRET + "@neapi.hoymiles.com/iam/pub/3/auth/pre-insp?times=1",
    PRE,
])
async def test_untrusted_auth_target_is_never_contacted_or_logged(target, caplog):
    assert not trusted_auth_redirect(PRE, target)
    api = client_with(response(302, location=target))
    with pytest.raises(HoymilesConnectionError):
        await api._json(PRE, {"u": SECRET})
    assert api._session.post.call_count == 1
    assert "stage=login_challenge reason=redirect_rejected" in caplog.text
    assert "redirect_policy=blocked_target" in caplog.text
    assert "http_status=302" in caplog.text
    assert SECRET not in caplog.text
    assert "https://" not in caplog.text


async def test_second_redirect_is_not_followed(caplog):
    target = PRE.replace("euapi", "neapi")
    api = client_with(response(302, location=target), response(307, location=PRE))
    with pytest.raises(HoymilesConnectionError):
        await api._json(PRE, {"u": SECRET})
    assert api._session.post.call_count == 2
    assert "redirect_policy=hop_limit" in caplog.text
    assert SECRET not in caplog.text


@pytest.mark.parametrize("status", [301, 303, 308])
async def test_unsupported_redirect_status_is_rejected(status, caplog):
    api = client_with(response(status, location=PRE.replace("euapi", "neapi")))
    with pytest.raises(HoymilesConnectionError):
        await api._json(PRE, {"u": SECRET})
    assert api._session.post.call_count == 1
    assert "redirect_policy=unsupported_status" in caplog.text


async def test_non_auth_redirect_remains_blocked(caplog):
    url = "https://neapi.hoymiles.com/pvmc/api/0/station/select_device_c"
    api = client_with(response(302, location=url.replace("neapi", "euapi")))
    with pytest.raises(HoymilesConnectionError):
        await api._json(url, {"sid": 123})
    assert api._session.post.call_count == 1
    assert api._session.post.call_args.kwargs["headers"]["Authorization"] == SECRET
    assert "redirect_policy=not_auth_request" in caplog.text
    assert SECRET not in caplog.text


@pytest.mark.parametrize("query", ["", "?times=1"])
async def test_redirected_rate_limit_preserves_backoff_and_original_stage(query, caplog):
    api = client_with(response(302, location=PRE.replace("euapi", "neapi") + query), response(429))
    with pytest.raises(HoymilesRateLimitError):
        await api._json(PRE, {"u": SECRET})
    assert api._session.post.call_count == 2
    assert "stage=login_challenge reason=http_error http_status=429" in caplog.text
    assert SECRET not in caplog.text


async def test_full_login_with_both_requests_redirected(caplog):
    api = client_with(
        response(data={"status": 0, "data": {"dc": 1, "login_url": "https://euapi.hoymiles.com"}}),
        response(302, location=PRE.replace("euapi", "neapi")),
        response(data={"status": "0", "data": {"v": 3, "dc": 1, "a": "0123456789abcdef", "n": SECRET}}),
        response(307, location=LOGIN.replace("euapi", "neapi")),
        response(data={"status": "0", "data": {"token": SECRET}}),
    )
    await api.async_login()
    assert api._token == SECRET
    assert api._session.post.call_count == 5
    assert SECRET not in caplog.text


@pytest.mark.parametrize("operation", ["pre-insp", "login"])
async def test_observed_times_marker_preserves_auth_request(operation, caplog):
    source = f"https://euapi.hoymiles.com/iam/pub/3/auth/{operation}"
    target = f"https://euapi.hoymiles.com/iam/pub/3/auth/{operation}?times=1"
    final = {"status": "0", "data": {"n": SECRET}}
    api = client_with(response(307, location=target), response(data=final))
    payload = {"u": SECRET, "ch": SECRET, "n": SECRET}

    assert await api._json(source, payload) == final
    calls = api._session.post.call_args_list
    assert [call.args[0] for call in calls] == [source, target]
    assert api.runtime.request.call_count == 2
    for call in calls:
        assert call.kwargs["json"] == payload
        assert call.kwargs["allow_redirects"] is False
        assert "Authorization" not in call.kwargs["headers"]
    assert SECRET not in caplog.text
    assert target not in caplog.text


def test_observed_browser_redirect_is_trusted():
    assert trusted_auth_redirect(PRE.replace("euapi", "neapi"), PRE + "?times=1")
    assert not trusted_auth_redirect(PRE + "?times=1", PRE.replace("euapi", "neapi"))


@pytest.mark.parametrize("query", [
    "times=0", "times=2", "times=-1", "times=01", "times=1.0", "times=",
    "times", "Times=1", "times=%31", "t%69mes=1", "times=1&times=1",
    "times=1&", "times=1;other=1", "times=1&token=" + SECRET,
    "token=" + SECRET, "times=1#" + SECRET,
])
async def test_times_marker_does_not_allow_other_queries(query, caplog):
    target = PRE + "?" + query
    api = client_with(response(307, location=target))
    assert not trusted_auth_redirect(PRE, target)
    with pytest.raises(HoymilesConnectionError):
        await api._json(PRE, {"u": SECRET})
    assert api._session.post.call_count == 1
    assert "redirect_policy=blocked_target" in caplog.text
    assert SECRET not in caplog.text
    assert target not in caplog.text


@pytest.mark.parametrize("version", [1, 2, 3])
async def test_full_login_with_times_marker(version, caplog):
    api = client_with(
        response(data={"status": 0, "data": {"dc": 1, "login_url": "https://euapi.hoymiles.com"}}),
        response(307, location=PRE + "?times=1"),
        response(data={"status": "0", "data": {"v": version, "dc": 1, "a": "0123456789abcdef", "n": SECRET}}),
        response(307, location=LOGIN + "?times=1"),
        response(data={"status": "0", "data": {"token": SECRET}}),
    )
    await api.async_login()
    assert api._token == SECRET
    assert [call.args[0] for call in api._session.post.call_args_list] == [
        "https://euapi.hoymiles.com/iam/pub/0/c/region_c", PRE, PRE + "?times=1", LOGIN, LOGIN + "?times=1",
    ]
    assert api.runtime.request.call_count == 5
    assert SECRET not in caplog.text


async def test_second_redirect_with_times_marker_is_still_blocked(caplog):
    blocked = client_with(
        response(307, location=PRE + "?times=1"),
        response(307, location=PRE.replace("euapi", "neapi") + "?times=1"),
    )
    with pytest.raises(HoymilesConnectionError):
        await blocked._json(PRE, {"u": SECRET})
    assert blocked._session.post.call_count == 2
    assert "redirect_policy=hop_limit" in caplog.text
    assert SECRET not in caplog.text


@pytest.mark.parametrize("dc,host", [(0, "neapi"), (1, "euapi"), (4, "indapi")])
@pytest.mark.parametrize("version", [1, 2, 3])
async def test_account_selected_login_host_keeps_auth_transport_guards(dc, host, version, caplog):
    api = client_with(
        response(data={"status": 0, "data": {"dc": 1, "login_url": "https://euapi.hoymiles.com"}}),
        response(data={"status": 0, "data": {"v": version, "dc": dc, "f": 0, "t": 159,
                                              "a": "0123456789abcdef", "n": SECRET}}),
        response(data={"status": 0, "data": {"token": SECRET}}),
    )
    await api.async_login()
    calls = api._session.post.call_args_list
    assert [call.args[0] for call in calls] == ["https://euapi.hoymiles.com/iam/pub/0/c/region_c", PRE, f"https://{host}.hoymiles.com/iam/pub/3/auth/login"]
    assert api._cloud_stage(calls[2].args[0]) == "login"
    assert api.runtime.request.call_count == 3
    for call in calls:
        assert "Authorization" not in call.kwargs["headers"]
        assert call.kwargs["allow_redirects"] is False
        assert call.kwargs["json"].get("u", call.kwargs["json"].get("email")) == SECRET
    assert calls[2].kwargs["json"]["n"] == SECRET
    assert api._token == SECRET
    assert SECRET not in caplog.text


async def test_dc0_login_remains_limited_to_one_known_auth_redirect(caplog):
    ne_login = LOGIN.replace("euapi", "neapi")
    api = client_with(
        response(data={"status": 0, "data": {"dc": 1, "login_url": "https://euapi.hoymiles.com"}}),
        response(data={"status": 0, "data": {"v": 3, "dc": 0, "a": "0123456789abcdef", "n": SECRET}}),
        response(307, location=ne_login + "?times=1"),
        response(data={"status": 0, "data": {"token": SECRET}}),
    )
    await api.async_login()
    assert [call.args[0] for call in api._session.post.call_args_list] == ["https://euapi.hoymiles.com/iam/pub/0/c/region_c", PRE, ne_login, ne_login + "?times=1"]
    assert api.runtime.request.call_count == 4
    for call in api._session.post.call_args_list:
        assert "Authorization" not in call.kwargs["headers"]
    assert SECRET not in caplog.text
