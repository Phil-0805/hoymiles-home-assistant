"""History copies reduce Recorder writes without slowing live entities."""

from datetime import UTC, datetime, timedelta
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from homeassistant.components.recorder.db_schema import States, StatesMeta, StatisticsShortTerm, StatisticsMeta
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.recorder import session_scope
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.setup import async_setup_component
from homeassistant.helpers.restore_state import RestoredExtraData
from homeassistant.helpers.dispatcher import async_dispatcher_send
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant_custom_component.components.recorder.common import async_wait_recording_done, do_adhoc_statistics

from custom_components.hoymiles_home.const import DOMAIN, HISTORY_FLUSH_SIGNAL
from custom_components.hoymiles_home.coordinator import HoymilesHomeCoordinator
from custom_components.hoymiles_home.sensor import (
    HISTORY_SENSOR_KEYS, HoymilesHistorySensor, HoymilesStationSensor, STATION_SENSORS,
    async_setup_entry,
)

ENTRY = SimpleNamespace(entry_id="history_test", data={"station_id": 123})


@pytest.fixture
def mock_recorder_before_hass(request):
    """Let the upstream fixture select its database before HA is created."""
    if "recorder_mock" in request.fixturenames:
        request.getfixturevalue("recorder_db_url")


def data(value, *, energy=100, day="2026-11-15", available=True):
    return {"live": {"con": 1, "power": {"pv": value, "load": value, "grid": -value, "bat": value}, "brs": 1},
            "live_available": available,
            "battery_energy": {"date": day, "consumption_wh": energy, "charge_wh": energy, "discharge_wh": energy}}


async def pair(hass, *, interval=30, key="load_power", zone="UTC"):
    client = MagicMock(profile="home", supports_home_features=True)
    coordinator = HoymilesHomeCoordinator(hass, client, 123, station_timezone=ZoneInfo(zone))
    coordinator.update_interval = None
    day = datetime.now(UTC).astimezone(ZoneInfo(zone)).date().isoformat()
    coordinator.async_set_updated_data(data(10, day=day))
    source = HoymilesStationSensor(coordinator, ENTRY, next(d for d in STATION_SENSORS if d.key == key))
    history = HoymilesHistorySensor(source, ENTRY, interval)
    for entity, name in [(source, "fast"), (history, "sampled")]:
        entity.entity_id = "sensor." + name
        entity._attr_name = name
        entity._attr_device_info = None
    component = EntityComponent(logging.getLogger(__name__), "sensor", hass)
    await component.async_add_entities([source, history])
    return coordinator, source, history


async def cleanup(coordinator, *entities):
    for entity in entities:
        if entity.hass is not None:
            await entity.async_remove()
    await coordinator.async_shutdown()


@pytest.mark.parametrize("interval", [10, 15, 30, 60])
async def test_live_updates_continue_between_history_samples(hass, freezer, interval):
    freezer.move_to("2026-11-15 12:00:00+00:00")
    coordinator, source, history = await pair(hass, interval=interval)
    try:
        initial = hass.states.get(history.entity_id)
        for second in range(1, interval):
            freezer.move_to(datetime(2026, 11, 15, 12, tzinfo=UTC) + timedelta(seconds=second))
            coordinator.async_set_updated_data(data(10 + second))
            assert float(hass.states.get(source.entity_id).state) == 10 + second
            assert hass.states.get(history.entity_id) == initial
        freezer.move_to(datetime(2026, 11, 15, 12, tzinfo=UTC) + timedelta(seconds=interval))
        coordinator.async_set_updated_data(data(99))
        assert float(hass.states.get(history.entity_id).state) == 99
        assert history.unique_id == "history_test_load_power_history"
        assert coordinator.client.mock_calls == []
    finally:
        await cleanup(coordinator, source, history)


async def test_availability_and_recovery_are_immediate_and_zero_is_real(hass, freezer):
    freezer.move_to("2026-11-15 12:00:00+00:00")
    coordinator, source, history = await pair(hass)
    try:
        freezer.tick(1)
        coordinator.async_set_updated_data(data(0, available=False))
        assert hass.states.get(history.entity_id).state == "unavailable"
        freezer.tick(1)
        coordinator.async_set_updated_data(data(0))
        assert float(hass.states.get(history.entity_id).state) == 0
        freezer.tick(1)
        coordinator.async_set_update_error(UpdateFailed("synthetic"))
        assert hass.states.get(history.entity_id).state == "unavailable"
        freezer.tick(1)
        coordinator.async_set_updated_data(data(42))
        assert float(hass.states.get(history.entity_id).state) == 42
    finally:
        await cleanup(coordinator, source, history)


@pytest.mark.parametrize("value", ["off", None, True, 30, "3", "30.0", {}])
async def test_off_or_invalid_option_creates_no_history_entities(hass, value):
    coordinator = HoymilesHomeCoordinator(hass, MagicMock(profile="home"), 123)
    coordinator.battery_telemetry.enabled = False
    hass.data.setdefault(DOMAIN, {})[ENTRY.entry_id] = coordinator
    entry = SimpleNamespace(**vars(ENTRY), options={"history_interval": value})
    entities = []
    await async_setup_entry(hass, entry, entities.extend)
    assert not any(isinstance(entity, HoymilesHistorySensor) for entity in entities)
    await coordinator.async_shutdown()


@pytest.mark.parametrize("profile", ["home", "installer", "enduser"])
async def test_option_available_for_all_profiles_and_preserves_other_settings(hass, profile):
    entry = MockConfigEntry(domain=DOMAIN, data={"client_profile": profile},
                            options={"retained_setting": 7})
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert "history_interval" in {key.schema for key in result["data_schema"].schema}
    result = await hass.config_entries.options.async_configure(result["flow_id"], {
        "history_interval": "30", "station_timezone": "UTC", **({"pv_power_source": "auto"} if profile != "enduser" else {})})
    assert entry.options["history_interval"] == "30"
    assert entry.options["retained_setting"] == 7


@pytest.mark.parametrize("profile", ["home", "installer", "enduser"])
async def test_only_selected_station_measurements_get_history_copies(hass, profile):
    coordinator = HoymilesHomeCoordinator(hass, MagicMock(profile=profile, supports_home_features=profile == "home"), 123)
    coordinator.battery_telemetry.enabled = False
    hass.data.setdefault(DOMAIN, {})[ENTRY.entry_id] = coordinator
    entities = []
    await async_setup_entry(hass, SimpleNamespace(**vars(ENTRY), options={"history_interval": "15"}), entities.extend)
    histories = [entity for entity in entities if isinstance(entity, HoymilesHistorySensor)]
    assert {entity._source.entity_description.key for entity in histories} == HISTORY_SENSOR_KEYS
    assert len(histories) == 9
    await coordinator.async_shutdown()


@pytest.mark.parametrize("zone,utc", [("UTC", "2026-11-15 23:59:00+00:00"),
                                      ("Europe/Berlin", "2026-11-15 22:59:00+00:00")])
async def test_energy_publishes_final_minute_and_explicit_reset(hass, freezer, zone, utc):
    freezer.move_to(utc)
    coordinator, source, history = await pair(hass, interval=60, key="load_energy_today", zone=zone)
    try:
        for second, value in [(3, 101), (30, 105), (59, 109)]:
            freezer.move_to(datetime.fromisoformat(utc) + timedelta(seconds=second))
            coordinator.async_set_updated_data(data(10, energy=value))
            assert float(hass.states.get(history.entity_id).state) == value
        old_reset = history.last_reset
        freezer.move_to(datetime.fromisoformat(utc) + timedelta(seconds=61))
        coordinator.async_set_updated_data(data(10, energy=0, day="2026-11-16"))
        assert float(hass.states.get(history.entity_id).state) == 0
        assert history.last_reset > old_reset
        assert history.state_class == "total"
    finally:
        await cleanup(coordinator, source, history)


@pytest.mark.parametrize("recorder_config", [{}, {"exclude": {"entities": ["sensor.fast"]}}])
async def test_actual_recorder_excludes_fast_but_live_states_keep_up(recorder_mock, hass, freezer):
    freezer.move_to("2026-11-15 12:00:00+00:00")
    coordinator, source, history = await pair(hass)
    try:
        for second in range(3, 64, 3):
            freezer.move_to(datetime(2026, 11, 15, 12, tzinfo=UTC) + timedelta(seconds=second))
            coordinator.async_set_updated_data(data(second))
        assert float(hass.states.get(source.entity_id).state) == 63
        await async_wait_recording_done(hass)
        def rows():
            with session_scope(session=recorder_mock.get_session(), read_only=True) as session:
                return session.execute(select(StatesMeta.entity_id, States.state).join(
                    States, States.metadata_id == StatesMeta.metadata_id).order_by(States.state_id)).all()
        stored = await hass.async_add_executor_job(rows)
        fast = [value for entity, value in stored if entity == source.entity_id]
        assert len(fast) == (0 if recorder_mock.entity_filter and not recorder_mock.entity_filter(source.entity_id) else 22)
        assert [float(value) for entity, value in stored if entity == history.entity_id] == [10, 30, 60]
    finally:
        await cleanup(coordinator, source, history)


async def test_reload_guard_never_restores_old_energy_as_fresh_or_publishes_a_decrease(hass, freezer):
    freezer.move_to("2026-11-15 12:00:00+00:00")
    with patch.object(HoymilesHistorySensor, "async_get_last_extra_data", AsyncMock(
            return_value=RestoredExtraData({"cycle": "2026-11-15", "value": 125}))):
        coordinator, source, history = await pair(hass, key="load_energy_today")
    try:
        assert hass.states.get(history.entity_id).state == "unavailable"
        coordinator.async_set_updated_data(data(10, energy=130))
        assert float(hass.states.get(history.entity_id).state) == 130
        coordinator.async_set_updated_data(data(10, energy=129))
        assert hass.states.get(history.entity_id).state == "unavailable"
        coordinator.async_set_updated_data(data(10, energy=130))
        assert float(hass.states.get(history.entity_id).state) == 130
    finally:
        await cleanup(coordinator, source, history)


async def test_energy_flush_on_reload_and_listeners_removed(hass, freezer):
    freezer.move_to("2026-11-15 12:00:00+00:00")
    coordinator, source, history = await pair(hass, key="load_energy_today")
    events = []
    cancel = hass.bus.async_listen("state_changed", lambda event: events.append(event.data))
    try:
        freezer.tick(3)
        coordinator.async_set_updated_data(data(10, energy=105))
        assert float(hass.states.get(history.entity_id).state) == 100
        async_dispatcher_send(hass, HISTORY_FLUSH_SIGNAL.format(ENTRY.entry_id))
        await history.async_remove(force_remove=True)
        await hass.async_block_till_done()
        numeric = [e["new_state"].state for e in events if e["entity_id"] == history.entity_id and e["new_state"] is not None]
        assert "105" in numeric
        assert history.extra_restore_state_data.as_dict() == {"value": 105, "cycle": "2026-11-15"}
        replacement = HoymilesHistorySensor(source, ENTRY, 60)
        replacement.entity_id = "sensor.sampled"
        replacement._attr_name = "sampled"
        replacement._attr_device_info = None
        component = EntityComponent(logging.getLogger(__name__), "sensor", hass)
        await component.async_add_entities([replacement])
        # A real remove/re-add retains the guard and stable registry identity.
        assert float(hass.states.get(replacement.entity_id).state) == 105
        coordinator.async_set_updated_data(data(10, energy=104))
        assert hass.states.get(replacement.entity_id).state == "unavailable"
        await replacement.async_remove(force_remove=True)
        coordinator.async_set_updated_data(data(10, energy=110))
        assert hass.states.get(history.entity_id) is None
    finally:
        cancel()
        await cleanup(coordinator, source)


async def test_settings_notifications_do_not_sample_and_signed_power_is_preserved(hass, freezer):
    freezer.move_to("2026-11-15 12:00:00+00:00")
    coordinator, source, history = await pair(hass, key="grid_power")
    try:
        initial = hass.states.get(history.entity_id)
        freezer.tick(3)
        coordinator.async_set_updated_data(data(12))
        coordinator.async_update_listeners()
        assert hass.states.get(history.entity_id) == initial
        freezer.tick(30)
        coordinator.async_set_updated_data(data(20))
        assert float(hass.states.get(history.entity_id).state) == -20
        assert history.extra_state_attributes == {"sampling_interval_seconds": 30}
    finally:
        await cleanup(coordinator, source, history)


async def test_energy_tail_is_published_before_midnight_without_another_live_update(hass, freezer):
    freezer.move_to("2026-11-15 23:58:00+00:00")
    coordinator, source, history = await pair(hass, interval=60, key="load_energy_today")
    try:
        freezer.tick(45)
        coordinator.async_set_updated_data(data(10, energy=105))
        assert float(hass.states.get(history.entity_id).state) == 100
        freezer.move_to("2026-11-15 23:59:00+00:00")
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        assert float(hass.states.get(history.entity_id).state) == 105
        freezer.move_to("2026-11-16 00:00:03+00:00")
        coordinator.async_set_updated_data(data(10, energy=0, day="2026-11-16"))
        assert float(hass.states.get(history.entity_id).state) == 0
    finally:
        await cleanup(coordinator, source, history)
    assert history._cancel_boundary is None


@pytest.mark.parametrize("zone,utc,day", [
    ("Europe/Berlin", "2026-03-29 21:59:59+00:00", "2026-03-29"),
    ("Europe/Berlin", "2026-10-25 22:59:59+00:00", "2026-10-25"),
])
async def test_energy_reset_uses_station_date_across_dst_days(hass, freezer, zone, utc, day):
    freezer.move_to(utc)
    coordinator, source, history = await pair(hass, key="load_energy_today", zone=zone)
    try:
        assert history.last_reset.astimezone(ZoneInfo(zone)).date().isoformat() == day
        freezer.tick(2)
        next_day = datetime.now(UTC).astimezone(ZoneInfo(zone)).date().isoformat()
        coordinator.async_set_updated_data(data(10, energy=0, day=next_day))
        assert history.last_reset.astimezone(ZoneInfo(zone)).date().isoformat() == next_day
        assert float(hass.states.get(history.entity_id).state) == 0
    finally:
        await cleanup(coordinator, source, history)


@pytest.mark.parametrize("recorder_config", [{"exclude": {"entities": ["sensor.fast"]}}])
@pytest.mark.parametrize("final_live_updates", [True, False])
async def test_real_statistics_keep_old_day_tail_and_next_day_total(recorder_mock, hass, freezer, final_live_updates):
    assert await async_setup_component(hass, "sensor", {})
    await hass.async_block_till_done()
    freezer.move_to("2026-11-15 23:58:00+00:00")
    coordinator, source, history = await pair(hass, interval=60, key="load_energy_today")
    try:
        for stamp, value in [("23:58:03", 101), ("23:58:06", 102), ("23:59:03", 110), ("23:59:59", 120)]:
            if not final_live_updates and stamp.startswith("23:59"):
                continue
            freezer.move_to("2026-11-15 " + stamp + "+00:00")
            coordinator.async_set_updated_data(data(10, energy=value))
        if not final_live_updates:
            freezer.move_to("2026-11-15 23:59:00+00:00")
            async_fire_time_changed(hass)
            await hass.async_block_till_done()
        freezer.move_to("2026-11-16 00:00:02+00:00")
        coordinator.async_set_updated_data(data(10, energy=0, day="2026-11-16"))
        freezer.move_to("2026-11-16 00:01:03+00:00")
        coordinator.async_set_updated_data(data(10, energy=7, day="2026-11-16"))
        await async_wait_recording_done(hass)
        for start in [datetime(2026, 11, 15, 23, 55, tzinfo=UTC), datetime(2026, 11, 16, tzinfo=UTC)]:
            do_adhoc_statistics(hass, start=start)
            await async_wait_recording_done(hass)
        def stats():
            with session_scope(session=recorder_mock.get_session(), read_only=True) as session:
                return session.execute(select(StatisticsShortTerm.state, StatisticsShortTerm.sum).join(
                    StatisticsMeta, StatisticsShortTerm.metadata_id == StatisticsMeta.id).where(
                        StatisticsMeta.statistic_id == history.entity_id).order_by(StatisticsShortTerm.start_ts)).all()
        result = await hass.async_add_executor_job(stats)
        assert result == ([(120, 20), (7, 27)] if final_live_updates else [(102, 2), (7, 9)])
    finally:
        await cleanup(coordinator, source, history)
