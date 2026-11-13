"""Slow cloud charts stay visible between polls; duplicate data still expires."""

from datetime import UTC, datetime
import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import UnitOfPower, UnitOfTemperature
from homeassistant.helpers.entity_component import EntityComponent

from custom_components.hoymiles_home.coordinator import HoymilesHomeCoordinator
from custom_components.hoymiles_home.errors import HoymilesConnectionError
from custom_components.hoymiles_home.module_polling import ModulePoller
from custom_components.hoymiles_home.sensor import HoymilesModuleSensor, HoymilesInverterDetailSensor


INVERTER = {"id": 99, "model_no": "HMS-2000-4WB"}
ENTRY = SimpleNamespace(entry_id="synthetic", data={"station_id": 123})
DAY = "2026-11-12"


def values(time, power=15):
    return {"MODULE_POWER": power, "MODULE_V": 36, "MODULE_I": 0.41,
            "_sample_times": {key: time for key in ("MODULE_POWER", "MODULE_V", "MODULE_I")}}


def snapshot(time, temperature=12.2):
    return {"inverters": {99: {"time": time, "temperature": temperature,
                               "frequency": 49.96, "voltage": 235.3}}}


async def test_reported_491_641_492_second_cycle_stays_available_in_real_ha(hass, freezer):
    freezer.move_to(f"{DAY} 10:03:11+00:00")
    api = AsyncMock()
    api.async_module_values.return_value = values("09:55")
    api.async_module_snapshot.return_value = snapshot("09:55")
    coordinator = HoymilesHomeCoordinator(hass, api, 123, inverter_details=True, station_timezone=ZoneInfo("UTC"))
    coordinator.update_interval = None
    coordinator.inverters = [INVERTER]
    poller = coordinator.module_polling
    entities = [HoymilesModuleSensor(coordinator, ENTRY, INVERTER, port, "power", "MODULE_POWER",
                                    UnitOfPower.WATT, SensorDeviceClass.POWER) for port in range(1, 5)]
    temperature = HoymilesInverterDetailSensor(coordinator, ENTRY, INVERTER, "temperature",
                                              UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE)
    entities.append(temperature)
    for index, entity in enumerate(entities):
        entity.entity_id = f"sensor.synthetic_progress_{index}"
        entity._attr_name = entity.entity_id
        entity._attr_device_info = None
    component = EntityComponent(logging.getLogger(__name__), "sensor", hass)
    try:
        await poller._async_poll([INVERTER])
        coordinator.async_set_updated_data({"live": {"con": 1}, "live_available": True,
            "modules": poller.modules, "inverter_details": poller.details})
        await component.async_add_entities(entities)
        assert poller.diagnostics(99, [1])["pv_inputs"][0]["fields"]["power"]["age_seconds"] == 491
        first_progress = poller.module_field_progress[(99, 1, "MODULE_POWER")]

        # No extra request at this intervening live tick: published b10 expired here.
        freezer.move_to(f"{DAY} 10:05:41+00:00")
        coordinator.async_set_updated_data(dict(coordinator.data))
        summary = poller.diagnostics(99, [1])
        assert summary["pv_inputs"][0]["fields"]["power"] == {
            "status": "fresh", "age_seconds": 641, "progress_age_seconds": 150}
        assert poller.module_field_progress[(99, 1, "MODULE_POWER")] == first_progress
        assert poller.details_status == "readable"
        for entity in entities:
            assert hass.states.get(entity.entity_id).state != "unavailable"
        assert api.async_module_values.await_count == 4

        # A later ordinary five-minute batch advances the actual cloud point.
        freezer.move_to(f"{DAY} 10:08:12+00:00")
        api.async_module_values.return_value = values("10:00", power=17)
        api.async_module_snapshot.return_value = snapshot("10:00", temperature=12.4)
        await poller._async_poll([INVERTER])
        assert poller.diagnostics(99, [1])["pv_inputs"][0]["fields"]["power"]["age_seconds"] == 492
        assert hass.states.get(entities[0].entity_id).state == "17"
        assert hass.states.get(temperature.entity_id).state == "12.4"
        assert temperature.extra_state_attributes["sample_time"] == f"{DAY}T10:00:00+00:00"
        assert api.async_module_values.await_count == 8
        assert api.async_module_snapshot.await_count == 2
        api.async_micro_details.assert_not_awaited()
        freezer.move_to(f"{DAY} 10:10:42+00:00")
        coordinator.async_set_updated_data(dict(coordinator.data))
        assert all(hass.states.get(entity.entity_id).state != "unavailable" for entity in entities)
    finally:
        for entity in entities:
            if entity.hass is not None:
                await entity.async_remove()
        await coordinator.async_shutdown()


@pytest.mark.parametrize("power", [0, 15])
async def test_duplicate_successes_do_not_renew_progress_and_summary_expires_without_a_poll(hass, freezer, power):
    freezer.move_to(f"{DAY} 10:03:11+00:00")
    api = AsyncMock()
    api.async_module_values.return_value = values("09:55", power)
    api.async_module_snapshot.return_value = snapshot("09:55")
    api.async_micro_details.return_value = {"inverters": {}}
    poller = ModulePoller(hass, api, 123, ZoneInfo("UTC"), True, MagicMock())
    try:
        await poller._async_poll([INVERTER])
        first = dict(poller.module_field_progress)
        detail_first = dict(poller.detail_field_progress)
        freezer.move_to(f"{DAY} 10:08:12+00:00")
        await poller._async_poll([INVERTER])
        assert poller.module_field_progress == first
        assert poller.detail_field_progress == detail_first
        assert poller.is_fresh(99, 1, "MODULE_POWER")
        freezer.move_to(f"{DAY} 10:13:12+00:00")
        assert not poller.is_fresh(99, 1, "MODULE_POWER")
        assert not poller.detail_is_fresh(99, "temperature")
        assert poller.details_status == "no_data"
        assert poller.diagnostics(99, [1])["pv_inputs"][0]["fields"]["power"] == {
            "status": "stale", "age_seconds": 1092, "progress_age_seconds": 601}
        assert api.async_module_snapshot.await_count == 2
        assert api.async_module_values.await_count == 8
        assert poller.modules[99][1]["MODULE_POWER"] == power
    finally:
        await poller.async_shutdown()


async def test_failed_reads_do_not_renew_progress(hass, freezer):
    freezer.move_to(f"{DAY} 10:03:11+00:00")
    api = AsyncMock()
    api.async_module_values.return_value = values("09:55")
    api.async_module_snapshot.return_value = snapshot("09:55")
    poller = ModulePoller(hass, api, 123, ZoneInfo("UTC"), True, MagicMock())
    try:
        await poller._async_poll([INVERTER])
        first = dict(poller.module_field_progress)
        detail_first = dict(poller.detail_field_progress)
        freezer.move_to(f"{DAY} 10:08:12+00:00")
        api.async_module_values.side_effect = HoymilesConnectionError("synthetic")
        api.async_module_snapshot.side_effect = HoymilesConnectionError("synthetic")
        await poller._async_poll([INVERTER])
        assert poller.module_field_progress == first
        assert poller.detail_field_progress == detail_first
        assert poller.is_fresh(99, 1, "MODULE_POWER")
        assert poller.details_status == "unavailable"
        freezer.move_to(f"{DAY} 10:13:12+00:00")
        assert not poller.is_fresh(99, 1, "MODULE_POWER")
        assert not poller.detail_is_fresh(99, "temperature")
    finally:
        await poller.async_shutdown()


async def test_changed_bucket_value_is_progress_but_retains_source_time_and_absolute_age_cap(hass, freezer):
    freezer.move_to(f"{DAY} 10:03:11+00:00")
    poller = ModulePoller(hass, AsyncMock(), 123, ZoneInfo("UTC"), True, MagicMock())
    try:
        poller._merge_module(poller.modules, 99, 1, values("09:55"), DAY)
        poller._merge_details(snapshot("09:55"), {99}, DAY)
        freezer.move_to(f"{DAY} 10:08:12+00:00")
        poller._merge_module(poller.modules, 99, 1, values("09:55", 16), DAY)
        poller._merge_details(snapshot("09:55", 12.4), {99}, DAY)
        assert poller.module_field_updated[(99, 1, "MODULE_POWER")] == datetime(2026, 11, 12, 9, 55, tzinfo=UTC)
        assert poller.module_field_progress[(99, 1, "MODULE_POWER")] == datetime(2026, 11, 12, 10, 8, 12, tzinfo=UTC)
        assert poller.detail_field_updated[(99, "temperature")] == datetime(2026, 11, 12, 9, 55, tzinfo=UTC)
        assert poller.is_fresh(99, 1, "MODULE_POWER")
        # Other unchanged fields keep their own progress clock.
        assert poller.module_field_progress[(99, 1, "MODULE_V")] == datetime(2026, 11, 12, 10, 3, 11, tzinfo=UTC)
        freezer.move_to(f"{DAY} 10:15:01+00:00")
        poller._merge_module(poller.modules, 99, 1, values("09:55", 17), DAY)
        assert not poller.is_fresh(99, 1, "MODULE_POWER")  # Old bucket cannot be renewed forever.
        assert not poller.detail_is_fresh(99, "temperature")
    finally:
        await poller.async_shutdown()


@pytest.mark.parametrize("time", ["08:00", "10:05"])
async def test_old_or_future_first_samples_do_not_become_fresh_at_receipt(hass, freezer, time):
    freezer.move_to(f"{DAY} 10:03:11+00:00")
    poller = ModulePoller(hass, AsyncMock(), 123, ZoneInfo("UTC"), True, MagicMock())
    try:
        poller._merge_module(poller.modules, 99, 1, values(time, 0), DAY)
        poller._merge_details(snapshot(time, 0), {99}, DAY)
        assert not poller.is_fresh(99, 1, "MODULE_POWER")
        assert not poller.detail_is_fresh(99, "temperature")
    finally:
        await poller.async_shutdown()


async def test_older_replacement_and_diagnostic_reads_cannot_move_progress_clock(hass, freezer):
    freezer.move_to(f"{DAY} 10:03:11+00:00")
    poller = ModulePoller(hass, AsyncMock(), 123, ZoneInfo("UTC"), True, MagicMock())
    try:
        poller._merge_module(poller.modules, 99, 1, values("09:55"), DAY)
        poller._merge_details(snapshot("09:55"), {99}, DAY)
        first = dict(poller.module_field_progress)
        detail_first = dict(poller.detail_field_progress)
        freezer.move_to(f"{DAY} 10:08:12+00:00")
        poller._merge_module(poller.modules, 99, 1, values("09:50", 999), DAY)
        poller._merge_details(snapshot("09:50", 999), {99}, DAY)
        poller.diagnostics(99, [1])
        assert poller.module_field_progress == first
        assert poller.detail_field_progress == detail_first
        assert poller.modules[99][1]["MODULE_POWER"] == 15
        assert poller.details[99]["temperature"] == 12.2
    finally:
        await poller.async_shutdown()


async def test_removed_inverter_progress_is_pruned_and_shutdown_disables_cached_fields(hass, freezer):
    freezer.move_to(f"{DAY} 10:03:11+00:00")
    api = AsyncMock()
    api.async_module_values.return_value = values("09:55")
    api.async_module_snapshot.return_value = snapshot("09:55")
    api.async_micro_details.return_value = {"inverters": {}}
    poller = ModulePoller(hass, api, 123, ZoneInfo("UTC"), True, MagicMock())
    try:
        await poller._async_poll([INVERTER])
        assert poller.module_field_progress and poller.detail_field_progress
        await poller._async_poll([{**INVERTER, "id": 100}])
        assert not any(key[0] == 99 for key in poller.module_field_progress)
        assert not any(key[0] == 99 for key in poller.detail_field_progress)
        assert not poller.is_fresh(99, 1, "MODULE_POWER")
        assert not poller.detail_is_fresh(99, "temperature")
        assert poller.is_fresh(100, 1, "MODULE_POWER")
        await poller.async_shutdown()
        assert not poller.is_fresh(100, 1, "MODULE_POWER")
        assert poller.diagnostics(100, [1])["pv_inputs"][0]["fields"]["power"]["status"] == "stopped"
    finally:
        await poller.async_shutdown()


async def test_inflight_batch_does_not_attach_new_progress_to_old_published_values(hass, freezer):
    freezer.move_to(f"{DAY} 10:03:11+00:00")
    api = AsyncMock()
    updated = MagicMock()
    poller = ModulePoller(hass, api, 123, ZoneInfo("UTC"), False, updated)
    for port in (1, 2):
        poller._merge_module(poller.modules, 99, port, values("09:55", 15), DAY)
    previous_progress = dict(poller.module_field_progress)
    freezer.move_to(f"{DAY} 10:08:12+00:00")
    waiting, release = asyncio.Event(), asyncio.Event()

    async def fetch(station, identity, port, date, **kwargs):
        if port == 2:
            waiting.set()
            await release.wait()
        return values("10:00", 20)

    api.async_module_values.side_effect = fetch
    task = poller.start([{**INVERTER, "model_no": "HMS-800-2WB"}])
    try:
        await waiting.wait()
        assert poller.modules[99][1]["MODULE_POWER"] == 15
        assert poller.module_field_progress == previous_progress
        assert poller.module_field_updated[(99, 1, "MODULE_POWER")] == datetime(2026, 11, 12, 9, 55, tzinfo=UTC)
        updated.assert_not_called()
        release.set()
        await task
        assert poller.modules[99][1]["MODULE_POWER"] == 20
        assert poller.module_field_updated[(99, 1, "MODULE_POWER")] == datetime(2026, 11, 12, 10, 0, tzinfo=UTC)
        assert poller.module_field_progress[(99, 1, "MODULE_POWER")] == datetime(2026, 11, 12, 10, 8, 12, tzinfo=UTC)
        updated.assert_called_once()
    finally:
        release.set()
        await poller.async_shutdown()
