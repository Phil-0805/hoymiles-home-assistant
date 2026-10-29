"""No token leaves the trusted TLS transport or follows redirects."""

import ssl
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.hoymiles_home.api import HoymilesHomeClient
from custom_components.hoymiles_home.errors import HoymilesConnectionError


async def test_ha_session_verifies_certificates_and_hostname(hass):
    session = async_get_clientsession(hass, verify_ssl=True)
    context = session.connector._ssl
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname


@pytest.mark.parametrize("method", ["_json", "_async_binary_data"])
@pytest.mark.parametrize("url", ["http://neapi.hoymiles.com/live", "https://evil.example/live", "https://neapi.hoymiles.com/\nlive"])
async def test_untrusted_requests_never_reach_session(method, url):
    session = MagicMock()
    client = HoymilesHomeClient(session, "test@example.com", "secret")
    client._token = "PRIVATE"
    with pytest.raises(HoymilesConnectionError, match="Untrusted"):
        await getattr(client, method)(url, {})
    session.post.assert_not_called()


@pytest.mark.parametrize("method", ["_json", "_async_binary_data"])
async def test_redirect_response_is_rejected_without_following(method):
    response = MagicMock(status=302)
    response.json = AsyncMock()
    session = MagicMock()
    session.post.return_value.__aenter__ = AsyncMock(return_value=response)
    client = HoymilesHomeClient(session, "test@example.com", "secret")
    with pytest.raises(HoymilesConnectionError, match="redirected"):
        await getattr(client, method)("https://neapi.hoymiles.com/live", {})
    assert session.post.call_args.kwargs["allow_redirects"] is False
    assert session.post.call_count == 1
    response.json.assert_not_awaited()
