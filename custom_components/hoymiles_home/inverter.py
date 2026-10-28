"""Conservative microinverter metadata from the cloud device tree."""

from __future__ import annotations

import re
from typing import Any

from .const import DEFAULT_PORT_COUNT

# Only an explicit model number is evidence of a model/physical input count.
# Serial numbers, numeric model IDs and installed PV modules are not equivalent.
_HMS_MODEL = re.compile(r"\bHMS-\d+(?:DW|W)?-([124])(?:WB|T)\b", re.IGNORECASE)


def inverter_model(inverter: dict[str, Any]) -> str:
    """Use an explicit HMS model, otherwise avoid claiming a specific device."""
    for key in ("model", "model_name", "name"):
        value = inverter.get(key)
        if isinstance(value, str) and (match := _HMS_MODEL.search(value)):
            return match.group(0).upper()
    return "Hoymiles microinverter"


def inverter_ports(inverter: dict[str, Any]) -> range:
    """Derive physical inputs from a known model; retain legacy probes if unknown."""
    match = _HMS_MODEL.fullmatch(inverter_model(inverter))
    count = int(match.group(1)) if match else DEFAULT_PORT_COUNT
    return range(1, count + 1)
