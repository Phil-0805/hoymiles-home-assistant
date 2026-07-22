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

    def test_finds_device_addressed_targets(self):
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
                    }
                ],
            }
        ]
        self.assertEqual(
            battery.battery_setting_targets(tree),
            [{"dev_sn": "INV-A", "dev_type": 3, "dtu_sn": "DTU-A"}],
        )


if __name__ == "__main__":
    unittest.main()
