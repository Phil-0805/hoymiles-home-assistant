"""Tests for battery settings parsing."""

import importlib.util
from pathlib import Path
import unittest

MODULE = Path(__file__).parents[1] / "custom_components/hoymiles_home/battery.py"
SPEC = importlib.util.spec_from_file_location("hoymiles_battery", MODULE)
battery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(battery)


class TestBatterySettings(unittest.TestCase):
    def test_parses_modes_and_active_settings(self):
        parsed = battery.parse_battery_settings(
            {
                "code": 0,
                "data": {
                    "mode": 1,
                    "data": {
                        "k_1": {"reserve_soc": 10},
                        "k_5": {"reserve_soc": 20, "max_power": 50},
                    },
                },
            }
        )
        self.assertEqual(parsed["mode_name"], "Self-Consumption")
        self.assertEqual(parsed["available_modes"], [1, 5])
        self.assertEqual(parsed["active_settings"], {"reserve_soc": 10})

    def test_rejects_incomplete_payload(self):
        with self.assertRaises(battery.BatterySettingsError):
            battery.parse_battery_settings({"code": 0})

    def test_parses_current_app_work_mode_reserve_soc(self):
        parsed = battery.parse_work_mode_settings(
            {
                "code": 0,
                "data": {
                    "mode": 2,
                    "k_2": {"soc_l": 12, "soc_h": 100},
                    "k_3": {"mode": 1},
                },
            }
        )
        self.assertEqual(parsed["mode_name"], "Self-Consumption")
        self.assertEqual(parsed["active_settings"]["reserve_soc"], 12)
        self.assertEqual(parsed["reserve_soc_source"], "station_action_83_k_2_soc_l")
        self.assertTrue(parsed["writable"])

    def test_rejects_non_self_consumption_work_mode(self):
        with self.assertRaises(battery.BatterySettingsError):
            battery.parse_work_mode_settings(
                {"code": 0, "data": {"mode": 3, "k_3": {"soc_l": 12}}}
            )

    def test_confirms_delayed_work_mode_write(self):
        settings = battery.parse_work_mode_settings(
            {"code": 0, "data": {"mode": 2, "k_2": {"soc_l": 12}}}
        )
        self.assertTrue(
            battery.battery_settings_confirmed(
                settings,
                1,
                {"reserve_soc": 12, "soc_l": 12, "soc_h": 100},
            )
        )
        self.assertFalse(
            battery.battery_settings_confirmed(
                settings,
                1,
                {"reserve_soc": 15, "soc_l": 15, "soc_h": 100},
            )
        )

    def test_finds_and_confirms_user_setting_reserve_soc(self):
        candidates = battery.reserve_soc_candidates(
            {"battery": {"mode": 1, "data": {"k_1": {"reserve_soc": 12}}}}
        )
        self.assertEqual(
            candidates,
            [{"path": "battery.data.k_1.reserve_soc", "value": 12}],
        )
        self.assertEqual(battery.confirmed_reserve_soc(candidates, 1), 12)

    def test_does_not_guess_between_conflicting_reserve_soc_values(self):
        candidates = battery.reserve_soc_candidates(
            {"first": {"reserve_soc": 12}, "second": {"reserve_soc": 30}}
        )
        self.assertIsNone(battery.confirmed_reserve_soc(candidates, 1))

    def test_does_not_trust_bare_bms_reserve_soc(self):
        candidates = battery.reserve_soc_candidates(
            {"bms_data": {"reserve_soc": 30}}
        )
        self.assertIsNone(battery.confirmed_reserve_soc(candidates, 1))

    def test_reports_all_soc_named_settings_for_diagnostics(self):
        self.assertEqual(
            battery.soc_setting_candidates(
                {"bms_data": {"reserve_soc": 30, "minimum_soc": 12}}
            ),
            [
                {"path": "bms_data.reserve_soc", "value": 30},
                {"path": "bms_data.minimum_soc", "value": 12},
            ],
        )

    def test_finds_hibattery_device_addressed_targets(self):
        tree = [
            {
                "type": 1,
                "sn": "DTU-A",
                "dtu_sn": "DTU-A",
                "devices": [
                    {
                        "type": 3,
                        "sn": "INV-A",
                        "dtu_sn": "DTU-A",
                    },
                    {
                        "type": 12,
                        "sn": "BAT-A",
                        "dtu_sn": "BAT-A",
                    }
                ],
            }
        ]
        self.assertEqual(
            battery.battery_setting_targets(tree),
            [{"dev_sn": "BAT-A", "dev_type": 12, "dtu_sn": "BAT-A"}],
        )

    def test_does_not_use_microinverter_as_battery_target(self):
        tree = [
            {
                "type": 3,
                "sn": "INV-A",
                "dtu_sn": "DTU-A",
            }
        ]
        self.assertEqual(battery.battery_setting_targets(tree), [])

    def test_builds_complete_write_data(self):
        self.assertEqual(
            battery.battery_setting_command_data(
                14586310,
                1,
                {"reserve_soc": 10},
            ),
            {
                "sid": 14586310,
                "data": {
                    "mode": 1,
                    "data": {"reserve_soc": 10},
                },
            },
        )

    def test_mode_without_settings_has_no_empty_data_block(self):
        self.assertEqual(
            battery.battery_setting_command_data(14586310, 4, {}),
            {
                "sid": 14586310,
                "data": {"mode": 4},
            },
        )


if __name__ == "__main__":
    unittest.main()
