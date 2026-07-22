"""Tests for battery energy calculations."""

import importlib.util
from pathlib import Path
import unittest

MODULE = Path(__file__).parents[1] / "custom_components/hoymiles_home/energy.py"
SPEC = importlib.util.spec_from_file_location("hoymiles_energy", MODULE)
energy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(energy)


class TestBatteryEnergy(unittest.TestCase):
    def test_charge_energy(self):
        charge, discharge = energy.integrate_battery_energy(
            0, 0, 100, 100, 3600
        )
        self.assertEqual(charge, 100)
        self.assertEqual(discharge, 0)

    def test_discharge_energy(self):
        charge, discharge = energy.integrate_battery_energy(
            0, 0, -200, -200, 1800
        )
        self.assertEqual(charge, 0)
        self.assertEqual(discharge, 100)

    def test_direction_change(self):
        charge, discharge = energy.integrate_battery_energy(
            0, 0, 100, -100, 3600
        )
        self.assertEqual(charge, 50)
        self.assertEqual(discharge, 50)


if __name__ == "__main__":
    unittest.main()
