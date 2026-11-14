"""Regression coverage for model display and physical PV input discovery."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.hoymiles_home.const import DOMAIN
from custom_components.hoymiles_home.coordinator import HoymilesHomeCoordinator
from custom_components.hoymiles_home.inverter import inverter_model, inverter_ports, standalone_hms_target
from custom_components.hoymiles_home.sensor import (
    HoymilesModuleSensor,
    MODULE_SENSORS,
    async_setup_entry,
)


@pytest.mark.parametrize(
    ("metadata", "model", "ports"),
    [
        ({"model": "HMS-1000-2WB"}, "HMS-1000-2WB", [1, 2]),
        ({"model_name": "HMS-2000-4WB"}, "HMS-2000-4WB", [1, 2, 3, 4]),
        ({"name": "HiFlow Pro (hms-1000-2wb)"}, "HMS-1000-2WB", [1, 2]),
        ({"model": "HMS-400W-1T"}, "HMS-400W-1T", [1]),
        ({"model": "HMS-2000DW-4T"}, "HMS-2000DW-4T", [1, 2, 3, 4]),
        ({"model_no": "HMT-2250-6T"}, "HMT-2250-6T", [1, 2, 3, 4, 5, 6]),
        ({"model_name": "HMT-1800-6T"}, "HMT-1800-6T", [1, 2, 3, 4, 5, 6]),
        ({"name": "Inverter (hmt-2250-6t)"}, "HMT-2250-6T", [1, 2, 3, 4, 5, 6]),
        ({"sn": "HMT-2250-6T"}, "Hoymiles microinverter", [1, 2, 3, 4]),
        ({"model": "HMT-2250-6TX"}, "Hoymiles microinverter", [1, 2, 3, 4]),
        ({"model": "HMT-2250-4T"}, "Hoymiles microinverter", [1, 2, 3, 4]),
        ({"model": "HMT-9999-6T"}, "Hoymiles microinverter", [1, 2, 3, 4]),
        ({}, "Hoymiles microinverter", [1, 2, 3, 4]),
        ({"model": 2000, "name": "My plant"}, "Hoymiles microinverter", [1, 2, 3, 4]),
        ({"sn": "HMS-1000-2WB", "model": False}, "Hoymiles microinverter", [1, 2, 3, 4]),
        ({"model": "HMS-1000-2WB-extra"}, "HMS-1000-2WB", [1, 2]),
    ],
)
def test_explicit_model_or_neutral_fallback(metadata, model, ports):
    """Do not invent model metadata from a serial, number or plant name."""
    assert inverter_model(metadata) == model
    assert list(inverter_ports(metadata)) == ports


async def test_two_input_entities_preserve_identifiers(hass):
    """The two-input model must not create PV3/PV4; existing PV IDs stay stable."""
    coordinator = HoymilesHomeCoordinator(hass, AsyncMock(), 123)
    coordinator.inverters = [{"id": 99, "model": "HMS-1000-2WB", "sn": "INV"}]
    entry = SimpleNamespace(entry_id="existing_entry", data={"station_id": 123})
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    entities = []
    await async_setup_entry(hass, entry, entities.extend)
    modules = [entity for entity in entities if isinstance(entity, HoymilesModuleSensor)]
    assert len(modules) == 6
    assert {entity.unique_id for entity in modules} == {
        f"existing_entry_99_pv{port}_{key}"
        for port in (1, 2)
        for key, *_ in MODULE_SENSORS
    }
    assert all(entity.device_info["model"] == "HMS-1000-2WB" for entity in modules)
    assert all(entity.device_info["identifiers"] == {(DOMAIN, "inverter_99")} for entity in modules)
    coordinator.data = {"modules": {99: {1: {"MODULE_POWER": 123.4}}}}
    assert next(entity for entity in modules if entity.unique_id.endswith("pv1_power")).native_value == 123.4


async def test_unknown_model_does_not_claim_2000w(hass):
    coordinator = HoymilesHomeCoordinator(hass, AsyncMock(), 123)
    entry = SimpleNamespace(entry_id="existing_entry", data={"station_id": 123})
    key, quota, unit, device_class = MODULE_SENSORS[0]
    entity = HoymilesModuleSensor(coordinator, entry, {"id": 99}, 1, key, quota, unit, device_class)
    assert entity.device_info["model"] == "Hoymiles microinverter"


async def test_six_input_hmt_adds_ports_without_changing_existing_ids(hass):
    coordinator = HoymilesHomeCoordinator(hass, AsyncMock(), 123)
    coordinator.inverters = [{"id": 99, "type": 3, "model_no": "HMT-2250-6T"}]
    entry = SimpleNamespace(entry_id="existing_entry", data={"station_id": 123})
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    entities = []
    await async_setup_entry(hass, entry, entities.extend)
    modules = [entity for entity in entities if isinstance(entity, HoymilesModuleSensor)]
    assert len(modules) == 18
    assert {entity.unique_id for entity in modules} == {
        f"existing_entry_99_pv{port}_{key}"
        for port in range(1, 7) for key, *_ in MODULE_SENSORS
    }
    assert all(entity.device_info["model"] == "HMT-2250-6T" for entity in modules)
    assert all(entity.device_info["identifiers"] == {(DOMAIN, "inverter_99")} for entity in modules)
    coordinator.data = {"modules": {99: {5: {"MODULE_POWER": 55}, 6: {"MODULE_POWER": 66}}}}
    assert next(e for e in modules if e.unique_id.endswith("pv5_power")).native_value == 55
    assert next(e for e in modules if e.unique_id.endswith("pv6_power")).native_value == 66


@pytest.mark.parametrize("model", ["HMT-1800-6T", "HMT-2250-6T"])
def test_hmt_monitoring_does_not_enable_hms_standalone_controls(model):
    node = {"id": 99, "type": 3, "sn": "synthetic", "model_no": model}
    assert standalone_hms_target([node]) is None
    assert standalone_hms_target(
        [{"id": 99, "type": 3, "sn": "synthetic"}],
        [{**node, "_model_discovery": {"source": "web_tree", "result": "identified"}}],
    ) is None


async def test_chart_polling_uses_each_inverters_physical_inputs(hass):
    """Polling and entities must use the same layout, even in a mixed station."""
    client = AsyncMock()
    client.async_live.return_value = {"power": {}}
    client.async_station_realtime.return_value = {}
    client.async_module_values.return_value = {"MODULE_POWER": 42.0}
    coordinator = HoymilesHomeCoordinator(hass, client, 123)
    coordinator.device_tree = [{"id": 99, "type": 3}]
    coordinator.inverters = [
        {"id": 99, "model": "HMS-1000-2WB"},
        {"id": 100, "model": "HMS-2000-4WB"},
        {"id": 101, "model_no": "HMT-2250-6T"},
    ]
    with patch.object(coordinator, "_async_refresh_battery_settings", new=AsyncMock()):
        data = await coordinator._async_update_data()
        await hass.async_block_till_done()
    calls = client.async_module_values.await_args_list
    assert [(call.args[1], call.args[2]) for call in calls] == [
        (99, 1), (99, 2), (100, 1), (100, 2), (100, 3), (100, 4),
        (101, 1), (101, 2), (101, 3), (101, 4), (101, 5), (101, 6),
    ]
    assert set(data["modules"][99]) == {1, 2}
    assert set(data["modules"][101]) == {1, 2, 3, 4, 5, 6}
