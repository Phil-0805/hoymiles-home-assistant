"""Issue #34: distinguish action-83 parsing from subsequent read failures."""

from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.hoymiles_home.api import HoymilesHomeClient
from custom_components.hoymiles_home.cloud_logging import work_mode_response_summary
from custom_components.hoymiles_home.errors import HoymilesConnectionError

SECRET = "PRIVATE_ACCOUNT_PLAN_ID_SCHEDULE_TOKEN"


@pytest.mark.parametrize("tou", [None, {}, {"mode": 2}, {"mode": 3}, {"mode": 4}, {"mode": 5},
    {"mode": SECRET}, {"mode": True}, {"mode": 2, "k_2": {"id": SECRET, "week": [SECRET]}}])
async def test_invalid_top_level_mode_logs_shape_without_schedule_and_keeps_rejection(tou, caplog):
    raw = {"code": 0, "data": {"mode": SECRET, "k_3": tou, SECRET: SECRET}}
    before = deepcopy(raw)
    api = HoymilesHomeClient(MagicMock(), SECRET, SECRET)
    api._json = AsyncMock(return_value={"status": 0, "data": "synthetic-job"})
    api._async_poll_station_setting_job = AsyncMock(return_value=raw)
    for _ in range(2):
        with pytest.raises(HoymilesConnectionError):
            await api._async_work_mode_settings(123)
    assert raw == before
    assert caplog.text.count("reason=invalid_work_mode_settings") == 1
    assert "stage=work_mode_read" in caplog.text
    assert "app_mode=unavailable" in caplog.text
    assert "command_code=0" in caplog.text
    assert "cloud_status=" not in caplog.text and "uri=" not in caplog.text
    assert SECRET not in caplog.text and "synthetic-job" not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)
    assert all(call.args[1]["action"] == 83 for call in api._json.await_args_list)


@pytest.mark.parametrize("mode", [1, 2, 3, 4, 5, 1000000, SECRET, True, 3.0, "3"])
def test_only_known_mode_numbers_are_exported(mode):
    summary = work_mode_response_summary({"code": SECRET, "data": {
        "mode": mode, "k_3": {"mode": mode, "id": SECRET, "week": [SECRET]},
        "soc_l": SECRET, "soc_h": SECRET, SECRET: SECRET,
    }})
    assert SECRET not in summary
    assert f"app_mode={mode}" in summary if type(mode) is int and mode in (2, 3) else "app_mode=unavailable" in summary
    assert "1000000" not in summary


async def test_valid_tou_keeps_normal_read_result_without_warning(caplog):
    api = HoymilesHomeClient(MagicMock(), SECRET, SECRET)
    api._json = AsyncMock(return_value={"status": 0, "data": "synthetic-job"})
    api._async_poll_station_setting_job = AsyncMock(return_value={"code": 0, "data": {
        "mode": 3, "k_3": {"mode": 1},
    }})
    result = await api._async_work_mode_settings(123)
    assert result["mode"] == 8
    assert result["reserve_soc_verified"] is False
    assert caplog.text == ""
