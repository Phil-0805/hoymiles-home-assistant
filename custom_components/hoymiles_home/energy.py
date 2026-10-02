"""Battery power and energy calculations for Hoymiles S-Miles Home."""

from __future__ import annotations

BATTERY_RELAY_IDLE = 0
BATTERY_RELAY_CHARGING = 1
BATTERY_RELAY_DISCHARGING = 2


def integrate_positive_energy(
    energy_wh: float,
    previous_power: float,
    current_power: float,
    elapsed_seconds: float,
) -> float:
    """Integrate a positive power measurement using the trapezoidal rule."""
    hours = elapsed_seconds / 3600
    return energy_wh + (
        max(previous_power, 0.0) + max(current_power, 0.0)
    ) / 2 * hours


def split_battery_power(
    power: float, relay_status: int | None = None
) -> tuple[float, float]:
    """Return positive charge and discharge power.

    WB inverters report ``power.bat`` as an unsigned magnitude. Their ``brs``
    field carries the direction: 1 = charging, 2 = discharging, 0 = idle.
    Keep the signed-value fallback for other devices that do not expose
    ``brs``.
    """
    magnitude = abs(power)
    if relay_status == BATTERY_RELAY_CHARGING:
        return magnitude, 0.0
    if relay_status == BATTERY_RELAY_DISCHARGING:
        return 0.0, magnitude
    if relay_status == BATTERY_RELAY_IDLE:
        return 0.0, 0.0
    return max(power, 0.0), max(-power, 0.0)


def integrate_battery_energy(
    charge_wh: float,
    discharge_wh: float,
    previous_power: float,
    current_power: float,
    elapsed_seconds: float,
    previous_relay_status: int | None = None,
    current_relay_status: int | None = None,
) -> tuple[float, float]:
    """Integrate directional power using the trapezoidal rule."""
    previous_charge, previous_discharge = split_battery_power(
        previous_power, previous_relay_status
    )
    current_charge, current_discharge = split_battery_power(
        current_power, current_relay_status
    )
    hours = elapsed_seconds / 3600
    return (
        charge_wh + (previous_charge + current_charge) / 2 * hours,
        discharge_wh + (previous_discharge + current_discharge) / 2 * hours,
    )
