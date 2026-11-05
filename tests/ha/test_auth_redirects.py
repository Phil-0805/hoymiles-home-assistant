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


async def test_redirected_rate_limit_preserves_backoff_and_original_stage(caplog):
    api = client_with(response(302, location=PRE.replace("euapi", "neapi")), response(429))
    with pytest.raises(HoymilesRateLimitError):
        await api._json(PRE, {"u": SECRET})
    assert api._session.post.call_count == 2
    assert "stage=login_challenge reason=http_error http_status=429" in caplog.text
    assert SECRET not in caplog.text


async def test_full_login_with_both_requests_redirected(caplog):
    api = client_with(
        response(302, location=PRE.replace("euapi", "neapi")),
        response(data={"status": "0", "data": {"a": "0123456789abcdef", "n": SECRET}}),
        response(307, location=LOGIN.replace("euapi", "neapi")),
        response(data={"status": "0", "data": {"token": SECRET}}),
    )
    await api.async_login()
    assert api._token == SECRET
    assert api._session.post.call_count == 4
    assert SECRET not in caplog.text
