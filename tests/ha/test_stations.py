"""Station discovery contract and pagination, with mocked network responses."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.hoymiles_home.api import (
    HoymilesAuthError, HoymilesConnectionError, HoymilesHomeClient,
)


def make_client(*payloads):
    client = HoymilesHomeClient(MagicMock(), "user@example.com", "unused")
    client.async_ensure_login = AsyncMock()
    client._json = AsyncMock(side_effect=payloads)
    return client


def page(rows):
    return {"status": "0", "data": {"list": rows}}


async def test_only_station_ids_are_returned_not_nested_device_ids():
    client = make_client(page([
        {"sid": "123", "id": 999, "name": " Home ", "devices": [{"id": 888}]},
        {"id": 456, "name": "Other"},
        {"sid": True, "id": 777}, {"sid": 1.5}, {"sid": 0}, {"sid": "serial-123"},
    ]))
    assert await client.async_list_stations() == [
        {"sid": 123, "name": "Home"}, {"sid": 456, "name": "Other"},
    ]
    args = client._json.await_args
    assert args.args == (
        "https://neapi.hoymiles.com/pvmc/api/0/station/select_by_page_c",
        {"page": 1, "page_size": 100},
    )


async def test_fetches_second_page_and_deduplicates():
    client = make_client(
        page([{"sid": n, "name": "Plant"} for n in range(1, 101)]),
        page([{"sid": 100}, {"sid": 101}]),
    )
    stations = await client.async_list_stations()
    assert [s["sid"] for s in stations] == list(range(1, 102))
    assert client._json.await_args.args[1]["page"] == 2


async def test_exact_page_boundary_requests_empty_terminal_page():
    client = make_client(page([{"sid": n} for n in range(1, 101)]), page([]))
    assert len(await client.async_list_stations()) == 100
    assert client._json.await_count == 2


async def test_repeating_page_fails_without_looping():
    rows = [{"sid": n} for n in range(1, 101)]
    client = make_client(page(rows), page(rows))
    with pytest.raises(HoymilesConnectionError):
        await client.async_list_stations()
    assert client._json.await_count == 2


@pytest.mark.parametrize("payload", [
    {"status": "0", "data": None},
    {"status": "0", "data": {"devices": [{"id": 42}]}},
    page([{"sid": False}, {"sid": "not-a-number"}]),
])
async def test_malformed_response_is_not_mistaken_for_empty_account(payload):
    with pytest.raises(HoymilesConnectionError):
        await make_client(payload).async_list_stations()


async def test_empty_account():
    assert await make_client(page([])).async_list_stations() == []


async def test_mid_pagination_failure_never_returns_partial_list():
    client = make_client(
        page([{"sid": n} for n in range(1, 101)]),
        {"status": "1", "message": "Service unavailable"},
    )
    with pytest.raises(HoymilesConnectionError):
        await client.async_list_stations()


async def test_expired_token_is_preserved_as_auth_error():
    with pytest.raises(HoymilesAuthError):
        await make_client({"status": "1", "message": "Token expired"}).async_list_stations()
