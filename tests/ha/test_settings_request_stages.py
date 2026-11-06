"""Settings stages use fixed endpoint/action labels and keep app poll timing."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import ClientResponseError

from custom_components.hoymiles_home.api import HoymilesHomeClient
from custom_components.hoymiles_home.cloud_logging import CloudDiagnosticError, STAGES
from custom_components.hoymiles_home.const import DATA_BASE_URL, STATION_SETTING_READ_URL, STATION_SETTING_STATUS_URL
from custom_components.hoymiles_home.device_settings import read_retry_delay
from custom_components.hoymiles_home.errors import HoymilesConnectionError

SECRET = "PRIVATE_ACCOUNT_TOKEN_URL_SERIAL"


@pytest.mark.parametrize("family,prefix", [("device", "/pvm-ctl/api/0/dev/setting"),
                                          ("station", "/pvmc/api/0/station_ctl")])
@pytest.mark.parametrize("operation", ["read", "write"])
@pytest.mark.parametrize("action,feature", [(1518, "heating"), (1529, "lighting"),
    (1537, "cutoffs"), (84, "output_power"), (1532, "output_power"), (83, "work_mode"), (1013, "battery_settings")])
def test_fixed_action_stages(family, prefix, operation, action, feature):
    api = HoymilesHomeClient(MagicMock(), SECRET, SECRET)
    suffix = operation + ("_c" if family == "station" else "")
    stage = api._cloud_stage(DATA_BASE_URL + prefix + "/" + suffix, {"action": action, SECRET: SECRET})
    assert stage == feature + "_" + operation
    assert stage in STAGES


@pytest.mark.parametrize("action", [None, True, 84.0, "84", SECRET, {}])
def test_arbitrary_action_data_never_becomes_a_log_label(action):
    api = HoymilesHomeClient(MagicMock(), SECRET, SECRET)
    assert api._cloud_stage(STATION_SETTING_READ_URL, {"action": action}) == "station_settings_read"
    assert api._cloud_stage("https://neapi.hoymiles.com/" + SECRET, {"action": 84}) == "other_api"


@pytest.mark.parametrize("url,stage", [
    (DATA_BASE_URL + "/pvm-ctl/api/0/dev/setting/status", "device_settings_status"),
    (STATION_SETTING_STATUS_URL, "station_settings_status"),
    (DATA_BASE_URL + "/pvmc/api/0/station/phase/type_s_c", "output_phase_lookup"),
])
def test_phase_and_status_queries_are_identified_without_job_ids(url, stage):
    api = HoymilesHomeClient(MagicMock(), SECRET, SECRET)
    assert api._cloud_stage(url, {"id": SECRET}) == stage
    assert stage in STAGES


async def test_cloud_rejection_identifies_the_settings_read_without_private_payload(caplog):
    api = HoymilesHomeClient(MagicMock(), SECRET, SECRET)
    reply = MagicMock(status=200)
    async def chunks(*args):
        yield json.dumps({"status": 1, "message": SECRET, "data": None}).encode()
    reply.content.iter_chunked = chunks
    api._session.post.return_value.__aenter__.return_value = reply
    result = await api._json(STATION_SETTING_READ_URL, {"action": 84, "data": {"sid": SECRET}})
    assert result["status"] == 1
    assert "stage=output_power_read reason=cloud_rejected cloud_status=1" in caplog.text
    assert SECRET not in caplog.text


@pytest.mark.parametrize("status,retryable", [(403, False), (404, False), (500, True), (503, True)])
async def test_http_rejection_does_not_trigger_read_retries_but_server_failure_can(status, retryable):
    api = HoymilesHomeClient(MagicMock(), SECRET, SECRET)
    reply = MagicMock(status=status)
    reply.raise_for_status.side_effect = ClientResponseError(MagicMock(), (), status=status)
    api._session.post.return_value.__aenter__.return_value = reply
    with pytest.raises(HoymilesConnectionError) as caught:
        await api._json(STATION_SETTING_READ_URL, {"action": 84})
    assert (read_retry_delay(caught.value, 0) is not None) is retryable


async def test_station_status_poll_keeps_one_second_interval_and_existing_cap():
    api = HoymilesHomeClient(MagicMock(), SECRET, SECRET)
    api._json = AsyncMock(return_value={"status": 0, "data": {"code": 2}})
    with patch("custom_components.hoymiles_home.api.asyncio.sleep", new=AsyncMock()) as sleep:
        with pytest.raises(HoymilesConnectionError, match="timed out"):
            await api._async_poll_station_setting_job(SECRET)
    assert sleep.await_count == 10
    assert all(call.args == (1,) for call in sleep.await_args_list)
    assert api._json.await_count == 10
    assert all(call.args[0] == STATION_SETTING_STATUS_URL for call in api._json.await_args_list)


async def test_device_status_poll_never_resubmits_the_original_write():
    api = HoymilesHomeClient(MagicMock(), SECRET, SECRET)
    api.async_ensure_login = AsyncMock()
    api._json = AsyncMock(side_effect=[{"status": 0, "data": SECRET}]
                          + [{"status": 0, "data": {"code": 2}}] * 10)
    with patch("custom_components.hoymiles_home.api.asyncio.sleep", new=AsyncMock()) as sleep:
        with pytest.raises(HoymilesConnectionError, match="timed out"):
            await api._async_device_settings_action({"action": 1518, "data": {"enable": 1}}, write=True)
    assert sleep.await_count == 10
    assert all(call.args == (1,) for call in sleep.await_args_list)
    calls = api._json.await_args_list
    assert len(calls) == 11
    assert sum(call.args[0].endswith("/write") for call in calls) == 1
    assert all(call.args[0].endswith("/status") for call in calls[1:])
