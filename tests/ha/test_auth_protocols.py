"""Use the explicit manufacturer challenge version without guessing or retries."""

from unittest.mock import AsyncMock, MagicMock, patch

from argon2.low_level import Type, hash_secret_raw
import pytest

from custom_components.hoymiles_home.api import HoymilesHomeClient
from custom_components.hoymiles_home.cloud_logging import CloudDiagnosticError
from custom_components.hoymiles_home.errors import HoymilesAuthError

ACCOUNT = "synthetic@example.invalid"
NONCE = "PRIVATE_NONCE_NEVER_LOG"
TOKEN = "PRIVATE_TOKEN_NEVER_LOG"
SALT = "0123456789abcdef"


def client(challenge, password="password", result=None):
    api = HoymilesHomeClient(MagicMock(), ACCOUNT, password)
    if isinstance(challenge, dict):
        challenge = {"dc": 1, **challenge}
    api._json = AsyncMock(side_effect=[
        {"status": 0, "data": {"dc": 1, "login_url": "https://euapi.hoymiles.com"}},
        {"status": 0, "data": challenge},
        result or {"status": 0, "data": {"token": TOKEN}},
    ])
    return api


@pytest.mark.parametrize("version", [1, 2, "1", "2"])
@pytest.mark.parametrize("password,expected", [
    ("password", "5f4dcc3b5aa765d61d8327deb882cf99.XohImNooBHFR0OVvjcYpJ3NgPQ1qq73WKhHvch0VQtg="),
    (" pässwörd🔋 ", "fd87faa579d0b4c1e62eabe310d57681.XGow/uOl5i/Ia6uNBOUjxEXqDyOwxkqOS0UStMQ6Y1g="),
])
async def test_legacy_matches_independent_node_crypto_vectors(version, password, expected):
    api = client({"v": version, "a": SALT, "n": NONCE}, password)
    with patch("custom_components.hoymiles_home.api.asyncio.to_thread", new=AsyncMock()) as worker:
        await api.async_login()
    worker.assert_not_awaited()
    assert api._json.await_count == 3
    assert api._json.await_args.args[1] == {"u": ACCOUNT, "ch": expected, "n": NONCE}
    assert api._token == TOKEN


@pytest.mark.parametrize("version", [3, "3"])
async def test_v3_keeps_app_argon2_parameters_and_utf8(version):
    api = client({"v": version, "a": SALT, "n": NONCE}, " pässwörd🔋 ")
    with patch("custom_components.hoymiles_home.api.asyncio.to_thread", new=AsyncMock(return_value=b"hash")) as worker:
        await api.async_login()
    worker.assert_awaited_once_with(
        hash_secret_raw, " pässwörd🔋 ".encode(), bytes.fromhex(SALT), 3, 32768, 1, 32, Type.ID,
    )
    assert api._json.await_args.args[1] == {"u": ACCOUNT, "ch": b"hash".hex(), "n": NONCE}


@pytest.mark.parametrize("challenge", [None, [], "private"])
async def test_invalid_challenge_shape_stops_before_login(challenge, caplog):
    api = client(challenge)
    with pytest.raises(HoymilesAuthError):
        await api.async_login()
    assert api._json.await_count == 2
    assert "private" not in caplog.text


@pytest.mark.parametrize("version", [None, 0, -1, 4, True, 3.0, "03", "3.0", "PRIVATE_VERSION"])
async def test_unknown_or_missing_version_never_guesses_an_algorithm(version, caplog):
    api = client({"v": version, "a": SALT, "n": NONCE})
    with pytest.raises(CloudDiagnosticError, match="Unsupported"):
        await api.async_login()
    assert api._json.await_count == 2
    assert "reason=unsupported_auth_version" in caplog.text
    assert "PRIVATE_VERSION" not in caplog.text
    assert NONCE not in caplog.text


@pytest.mark.parametrize("version", [1, 2, 3])
@pytest.mark.parametrize("dc", [0, 1, 4])
async def test_cloud_rejection_does_not_retry_with_another_protocol_or_host(version, dc):
    api = client({"v": version, "dc": dc, "a": SALT, "n": NONCE}, result={
        "status": 1, "message": "login failed", "data": "PRIVATE_RESPONSE",
    })
    with pytest.raises(HoymilesAuthError):
        await api.async_login()
    assert api._json.await_count == 3
    assert api._token is None


@pytest.mark.parametrize("version", [1, 2])
async def test_legacy_missing_nonce_matches_app_json_omission(version):
    api = client({"v": version})
    await api.async_login()
    assert "n" not in api._json.await_args.args[1]


@pytest.mark.parametrize("updates", [{"a": None}, {"a": "not hex"}, {"n": None}, {"n": True}, {"n": ""}])
async def test_invalid_v3_challenge_is_not_downgraded(updates):
    api = client({"v": 3, "a": SALT, "n": NONCE, **updates})
    with pytest.raises(HoymilesAuthError):
        await api.async_login()
    assert api._json.await_count == 2


def test_auth_failure_diagnostics_only_add_a_known_version(caplog):
    api = client({"v": 1})
    api._auth_version = 1
    api._cloud_report("login", "cloud_rejected", {"status": 1, "data": NONCE, "message": TOKEN})
    assert "auth_version=1" in caplog.text
    assert NONCE not in caplog.text and TOKEN not in caplog.text and ACCOUNT not in caplog.text


@pytest.mark.parametrize("dc,host", [("0", "neapi"), ("1", "euapi"), ("4", "indapi")])
async def test_app_integer_dc_strings_select_only_explicit_known_hosts(dc, host):
    api = client({"v": 3, "dc": dc, "a": SALT, "n": NONCE})
    await api.async_login()
    assert api._json.await_args.args[0] == f"https://{host}.hoymiles.com/iam/pub/3/auth/login"


@pytest.mark.parametrize("dc", [None, True, False, 0.0, 1.0, 2, 3, 41, -1, "00", "0.0", "PRIVATE_REGION", {}])
async def test_missing_invalid_or_unknown_dc_stops_before_login(dc, caplog):
    api = client({"v": 3, "dc": dc, "a": SALT, "n": NONCE})
    with pytest.raises(CloudDiagnosticError, match="authentication region"):
        await api.async_login()
    assert api._json.await_count == 2
    assert "reason=unsupported_auth_region" in caplog.text
    assert NONCE not in caplog.text and "PRIVATE_REGION" not in caplog.text


async def test_each_login_uses_its_fresh_challenge_region():
    api = client({"v": 1})
    api._json.side_effect = [
        {"status": 0, "data": {"dc": 1, "login_url": "https://euapi.hoymiles.com"}},
        {"status": 0, "data": {"v": 1, "dc": 0, "n": NONCE}},
        {"status": 0, "data": {"token": TOKEN}},
        {"status": 0, "data": {"dc": 1, "login_url": "https://euapi.hoymiles.com"}},
        {"status": 0, "data": {"v": 1, "dc": 1, "n": NONCE}},
        {"status": 0, "data": {"token": TOKEN}},
    ]
    await api.async_login()
    await api.async_login()
    assert [call.args[0] for call in api._json.await_args_list][2::3] == [
        "https://neapi.hoymiles.com/iam/pub/3/auth/login",
        "https://euapi.hoymiles.com/iam/pub/3/auth/login",
    ]


async def test_unsupported_dc_is_not_reused_after_previous_login(caplog):
    api = client({"v": 1, "dc": 0})
    await api.async_login()
    api._json.side_effect = [{"status": 0, "data": {"dc": 1, "login_url": "https://euapi.hoymiles.com"}}, {"status": 0, "data": {"v": 1}}]
    with pytest.raises(CloudDiagnosticError):
        await api.async_login()
    assert api._auth_dc is None


def test_auth_dc_diagnostics_use_known_codes_only(caplog):
    api = client({"v": 3})
    api._auth_version = 3
    api._auth_dc = 0
    api._cloud_report("login", "cloud_rejected", {"status": 1, "data": NONCE})
    assert "auth_version=3 auth_dc=0" in caplog.text
    assert NONCE not in caplog.text
