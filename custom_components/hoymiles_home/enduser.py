"""Explicit, read-only S-Miles Enduser response adapters.

Power is in W, energy in Wh. No Home relay codes or default measurements are
invented. ES flow nodes: grid=1, battery=2, solar=4, load=10, charger=50.
"""

from .cloud_logging import CloudDiagnosticError
from .telemetry import number

ES_CLASSIFICATIONS = frozenset({4, 5, 100})
SUPPORTED_CLASSIFICATIONS = ES_CLASSIFICATIONS | {1}


def _direction(flows, node):
    """Return +1 for inflow, -1 for outflow; ambiguous/missing stays unknown."""
    if not isinstance(flows, list) or len(flows) > 100:
        return None
    incoming = outgoing = False
    for flow in flows:
        if not isinstance(flow, dict):
            return None
        source, destination = flow.get("o"), flow.get("i")
        if (type(source) is not int or type(destination) is not int
                or source not in {1, 2, 4, 10, 50}
                or destination not in {1, 2, 4, 10, 50}
                or source == destination):
            return None
        incoming |= destination == node
        outgoing |= source == node
    if incoming == outgoing:
        return None
    return 1 if incoming else -1


def _directed(value, direction):
    value = number(value)
    if value == 0:
        return 0
    if value is None or direction is None:
        return None
    return abs(value) * direction


def parse_live(payload, classification):
    """Normalize only the evidenced fields for the selected station schema."""
    if type(classification) is not int or classification not in SUPPORTED_CLASSIFICATIONS:
        raise CloudDiagnosticError("unsupported_profile_operation", "Unsupported Enduser station classification")
    if not isinstance(payload, dict) or number(payload.get("con")) not in (0, 1):
        raise CloudDiagnosticError("invalid_live_data", "Invalid Enduser connection state")
    es = classification in ES_CLASSIFICATIONS
    block = payload.get("es" if es else "power")
    connected = number(payload["con"]) == 1
    if connected and not isinstance(block, dict):
        raise CloudDiagnosticError("invalid_live_data", "Missing Enduser power block")
    block = block if isinstance(block, dict) else {}
    result = {"con": int(connected), "dly": number(payload.get("dly")),
              "power": {}, "_enduser_schema": "es" if es else "power"}
    pv = number(block.get("pp" if es else "pv"))
    # An explicit offline zero is valid; old nonzero offline values are not.
    if pv is not None and (connected or pv == 0):
        result["power"]["pv"] = abs(pv)
    if not connected:
        return result
    load = number(block.get("lp" if es else "load"))
    if load is not None:
        result["power"]["load"] = abs(load)
    flows = payload.get("flow")
    grid_direction = _direction(flows, 1)
    # Canonical grid power: import positive, export negative.
    grid = _directed(block.get("gp" if es else "grid"),
                     -grid_direction if grid_direction is not None else None)
    if grid is not None:
        result["power"]["grid"] = grid
    if es:
        battery = _directed(block.get("bp"), _direction(flows, 2))
        if battery is not None:
            # Canonical battery power: charge positive, discharge negative.
            result["power"]["bat"] = battery
            result["_enduser_activity"] = (
                "charging" if battery > 0 else "discharging" if battery < 0 else "idle")
        soc = number(payload.get("soc"))
        if soc is not None and 0 <= soc <= 100:
            result["soc"] = soc
    return result


def parse_totals(payload):
    """Keep explicit standard generation totals; never substitute ES counters."""
    if not isinstance(payload, dict):
        raise CloudDiagnosticError("unexpected_response", "Invalid Enduser totals")
    totals = {}
    for key in ("today_eq", "month_eq", "year_eq", "total_eq"):
        value = number(payload.get(key))
        if value is not None and value >= 0:
            totals[key] = value
    # pv_eq and storage/grid counters refer to other periods/quantities.
    return totals
