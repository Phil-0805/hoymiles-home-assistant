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
    for key in ("model_no", "model", "model_name", "name"):
        value = inverter.get(key)
        if isinstance(value, str) and (match := _HMS_MODEL.search(value)):
            return match.group(0).upper()
    return "Hoymiles microinverter"


def inverter_ports(inverter: dict[str, Any]) -> range:
    """Derive physical inputs from a known model; retain legacy probes if unknown."""
    match = _HMS_MODEL.fullmatch(inverter_model(inverter))
    count = int(match.group(1)) if match else DEFAULT_PORT_COUNT
    return range(1, count + 1)


def standalone_hms_target(tree: Any) -> dict[str, Any] | None:
    """Recognize only an explicit single HMS inverter with optional DTU nodes.

    Unknown, empty, malformed and mixed trees retain the existing battery path.
    This is a narrow station-level capability, not a guessed battery address.
    """
    inverters = []
    identities = set()

    def has_storage(value):
        if isinstance(value, dict):
            return value.get("type") == 12 or any(has_storage(child) for child in value.values())
        return isinstance(value, list) and any(has_storage(child) for child in value)

    def visit(nodes):
        if not isinstance(nodes, list) or not nodes:
            return False
        for node in nodes:
            if not isinstance(node, dict):
                return False
            kind, identity = node.get("type"), node.get("id")
            if (type(kind) is not int or kind not in (2, 3)
                    or type(identity) is not int or identity <= 0
                    or (kind, identity) in identities):
                return False
            identities.add((kind, identity))
            if kind == 3:
                model = inverter_model(node)
                if not _HMS_MODEL.fullmatch(model):
                    return False
                inverters.append({"id": identity, "model": model})
            children = node.get("children")
            if children is not None and children != [] and not visit(children):
                return False
        return True

    if has_storage(tree) or not visit(tree) or len(inverters) != 1:
        return None
    return {"inverter": inverters[0], "devices": tuple(sorted(identities))}
