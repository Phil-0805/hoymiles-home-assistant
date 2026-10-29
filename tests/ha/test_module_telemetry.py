"""Optional telemetry parsing, sample freshness and independent polling."""

import asyncio
import base64
from datetime import UTC, datetime
import gzip
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.hoymiles_home.api import HoymilesHomeClient, HoymilesConnectionError
from custom_components.hoymiles_home.coordinator import HoymilesHomeCoordinator
from custom_components.hoymiles_home.module_data import decode_module_snapshot
from custom_components.hoymiles_home.module_polling import ModulePoller
from custom_components.hoymiles_home.sensor import HoymilesInverterDetailSensor, async_setup_entry
from custom_components.hoymiles_home.const import DOMAIN
from custom_components.hoymiles_home.protobuf import ProtobufDecodeError
from zoneinfo import ZoneInfo

FIXTURE = json.loads((Path(__file__).parents[1] / "fixtures/module_snapshot.json").read_text())
RAW = base64.b64decode(FIXTURE["raw_base64"])


@pytest.mark.parametrize("compressed", [False, True])
def test_same_fixture_used_for_independent_nodered_decoder(compressed):
    result = decode_module_snapshot(gzip.compress(RAW) if compressed else RAW, 123, "2026-10-29")
    sample = result["inverters"][99]
    assert sample["time"] == "10:00"
    assert sample["temperature"] == 21
    assert sample["frequency"] == pytest.approx(49.99, abs=0.001)
    assert sample["voltage"] == 231


@pytest.mark.parametrize("station,date", [(124, "2026-10-29"), (123, "2026-10-28")])
def test_wrong_station_or_day_is_rejected(station, date):
    with pytest.raises(ProtobufDecodeError):
        decode_module_snapshot(RAW, station, date)


def test_corrupt_gzip_and_decompression_limit():
    with pytest.raises(ProtobufDecodeError):
        decode_module_snapshot(b"\x1f\x8bBAD", 123, "2026-10-29")
    with patch("custom_components.hoymiles_home.module_data.MAX_MODULE_BYTES", 30):
        with pytest.raises(ProtobufDecodeError):
            decode_module_snapshot(gzip.compress(b"x" * 10000), 123, "2026-10-29")


async def test_optional_endpoint_is_read_only_and_scoped():
    api = HoymilesHomeClient(MagicMock(), "test@example.com", "secret")
    api.async_ensure_login = AsyncMock()
    api._async_binary_data = AsyncMock(return_value=RAW)
    result = await api.async_module_snapshot(123, "2026-10-29")
    assert result["inverters"][99]["temperature"] == 21
    api._async_binary_data.assert_awaited_once_with(
        "https://neapi.hoymiles.com/pvmc/api/0/module_data/dmdd_c",
        {"sid": 123, "date": "2026-10-29"},
    )


async def test_slow_module_read_does_not_delay_live_refresh(hass):
    started, release = asyncio.Event(), asyncio.Event()
    api = AsyncMock()
    api.async_live.return_value = {"con": 1, "power": {"pv": 123}}
    api.async_station_realtime.return_value = {}
    async def slow(*args):
        started.set()
        await release.wait()
        return {"MODULE_POWER": 42}
    api.async_module_values.side_effect = slow
    coordinator = HoymilesHomeCoordinator(hass, api, 123)
    coordinator.device_tree = [{"id": 99}]
    coordinator.inverters = [{"id": 99, "model_no": "HMS-800-2WB"}]
    with patch.object(coordinator, "_async_refresh_battery_settings", new=AsyncMock()):
        coordinator.data = await coordinator._async_update_data()
        await started.wait()
        second = await asyncio.wait_for(coordinator._async_update_data(), 0.5)
        assert second["live"]["power"]["pv"] == 123
        assert not release.is_set()
        release.set()
        await coordinator.module_polling.task
    assert coordinator.data["modules"][99][1]["MODULE_POWER"] == 42
    await coordinator.async_shutdown()


async def test_extra_endpoint_is_never_called_by_default(hass):
    api = AsyncMock()
    api.async_module_values.return_value = {}
    poller = ModulePoller(hass, api, 123, ZoneInfo("UTC"), False, MagicMock())
    await poller.start([{"id": 99, "model_no": "HMS-800-2WB"}])
    api.async_module_snapshot.assert_not_awaited()
    await poller.async_shutdown()


async def test_unsupported_extra_endpoint_keeps_regular_charts(hass):
    api = AsyncMock()
    api.async_module_snapshot.side_effect = HoymilesConnectionError("unavailable")
    api.async_module_values.return_value = {"MODULE_POWER": 42}
    poller = ModulePoller(hass, api, 123, ZoneInfo("UTC"), True, MagicMock())
    await poller.start([{"id": 99, "model_no": "HMS-800-2WB"}])
    assert poller.modules[99][1]["MODULE_POWER"] == 42
    assert poller.details_status == "unavailable"
    await poller.async_shutdown()


async def test_details_are_routed_only_to_known_inverter_and_expire(hass, freezer):
    freezer.move_to("2026-10-29 10:01:00+00:00")
    api = AsyncMock()
    api.async_module_values.return_value = {}
    api.async_module_snapshot.return_value = decode_module_snapshot(RAW, 123, "2026-10-29")
    api.async_module_snapshot.return_value["inverters"][100] = {"time": "10:00", "temperature": 99}
    coordinator = HoymilesHomeCoordinator(hass, api, 123, inverter_details=True, station_timezone="UTC")
    coordinator.inverters = [{"id": 99, "model_no": "HMS-800-2WB"}]
    coordinator.data = {"live": {"con": 1}}
    await coordinator.module_polling.start(coordinator.inverters)
    assert 100 not in coordinator.module_polling.details
    hass.data.setdefault(DOMAIN, {})["test"] = coordinator
    entities = []
    await async_setup_entry(hass, SimpleNamespace(entry_id="test", data={"station_id": 123}), entities.extend)
    extras = [entity for entity in entities if isinstance(entity, HoymilesInverterDetailSensor)]
    assert len(extras) == 3
    assert next(e for e in extras if e.unique_id.endswith("temperature")).native_value == 21
    assert all(e.available for e in extras)
    freezer.move_to("2026-10-29 10:11:00+00:00")
    assert all(not e.available for e in extras)
    await coordinator.async_shutdown()


def test_daily_energy_uses_station_timezone(hass):
    coordinator = HoymilesHomeCoordinator(hass, AsyncMock(), 123, station_timezone="Europe/Berlin")
    coordinator._energy_store.async_delay_save = MagicMock()
    coordinator._update_battery_energy({}, datetime(2026, 10, 29, 23, 30, tzinfo=UTC))
    assert coordinator._energy_date == "2026-10-30"
