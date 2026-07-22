"""Battery energy calculations for Hoymiles S-Miles Home."""

from __future__ import annotations


def split_battery_power(power: float) -> tuple[float, float]:
    """Return positive charge and discharge power from signed battery power."""
    return max(power, 0.0), max(-power, 0.0)


def integrate_battery_energy(
    charge_wh: float,
    discharge_wh: float,
    previous_power: float,
    current_power: float,
    elapsed_seconds: float,
) -> tuple[float, float]:
    """Integrate signed power using the trapezoidal rule."""
    previous_charge, previous_discharge = split_battery_power(previous_power)
    current_charge, current_discharge = split_battery_power(current_power)
    hours = elapsed_seconds / 3600
    return (
        charge_wh + (previous_charge + current_charge) / 2 * hours,
        discharge_wh + (previous_discharge + current_discharge) / 2 * hours,
    )
