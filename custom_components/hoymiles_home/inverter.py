"""Conservative microinverter metadata from the cloud device tree."""

from __future__ import annotations

import re
from typing import Any

from .const import DEFAULT_PORT_COUNT

# Only an explicit model number is evidence of a model/physical input count.
# Serial numbers, numeric model IDs and installed PV modules are not equivalent.
_HMS_MODEL = re.compile(r"\bHMS-\d+(?:DW|W)?-([124])(?:WB|T)\b", re.IGNORECASE)
# HMT-1800/2250-6T: six physical PV inputs (three MPPTs, two inputs each).
# Model/port recognition does not extend the HMS-only control target below.
_HMT_MODEL = re.compile(r"\bHMT-(?:1800|2250)-(6)T\b", re.IGNORECASE)

MODEL_DISCOVERY_REASONS = frozenset({
    "empty_data", "unexpected_data_type", "candidate_missing", "ambiguous_candidate",
    "invalid_identity_type", "identity_mismatch", "serial_mismatch", "model_missing",
    "invalid_model_type", "unsupported_model", "authentication", "rate_limited",
    "connection", "timeout", "transport_error", "http_error", "cloud_rejected",
    "redirect_rejected", "invalid_json", "unexpected_response", "session_expired",
    "client_update_required", "home_app_required", "unexpected_error",
})


def model_metadata_reason(candidate: Any, original: dict[str, Any]) -> str | None:
    """Explain rejected metadata without returning private values or field names."""
    if candidate is None or candidate == {}:
        return "empty_data"
    if not isinstance(candidate, dict):
        return "unexpected_data_type"
    if "id" in candidate:
        if type(candidate["id"]) is not int:
            return "invalid_identity_type"
        if candidate["id"] != original["id"]:
            return "identity_mismatch"
    if original.get("sn") and candidate.get("sn") and original["sn"] != candidate["sn"]:
        return "serial_mismatch"
    if inverter_model(candidate) != "Hoymiles microinverter":
        return None
    fields = [candidate[key] for key in ("model_no", "model", "model_name", "name")
              if key in candidate and candidate[key] not in (None, "")]
    if not fields:
        return "model_missing"
    return "unsupported_model" if any(isinstance(value, str) for value in fields) else "invalid_model_type"


def inverter_model(inverter: dict[str, Any]) -> str:
    """Use an explicit supported model, otherwise avoid a specific device claim."""
    for key in ("model_no", "model", "model_name", "name"):
        value = inverter.get(key)
        if isinstance(value, str):
            for pattern in (_HMS_MODEL, _HMT_MODEL):
                if match := pattern.search(value):
                    return match.group(0).upper()
    return "Hoymiles microinverter"


def inverter_ports(inverter: dict[str, Any]) -> range:
    """Derive physical inputs from a known model; retain legacy probes if unknown."""
    model = inverter_model(inverter)
    match = _HMS_MODEL.fullmatch(model) or _HMT_MODEL.fullmatch(model)
    count = int(match.group(1)) if match else DEFAULT_PORT_COUNT
    return range(1, count + 1)


def standalone_hms_target(tree: Any, enriched: Any = None) -> dict[str, Any] | None:
    """Return a verified target; diagnostics use exactly the same assessment."""
    return standalone_hms_assessment(tree, enriched)[0]


def standalone_hms_assessment(tree: Any, enriched: Any = None) -> tuple[dict | None, str]:
    """Recognize one explicit HMS with optional DTU/repeater nodes.

    Unknown, empty, malformed and mixed trees retain the existing battery path.
    This is a narrow station-level capability, not a guessed battery address.
    """
    inverters = []
    identities = set()
    reason = "no_inverter"

    def model_for(node):
        nonlocal reason
        model = inverter_model(node)
        if _HMS_MODEL.fullmatch(model):
            return model
        # Supplemental metadata may supply a model, never a device identity or
        # topology. It must still describe this exact original Home-tree node.
        if not isinstance(enriched, list):
            reason = "missing_model_metadata"
            return None
        candidates = [item for item in enriched if isinstance(item, dict)
                      and type(item.get("id")) is int and item["id"] == node["id"]]
        if len(candidates) != 1:
            reason = "missing_model_metadata" if not candidates else "ambiguous_model_metadata"
            return None
        candidate = candidates[0]
        discovery = candidate.get("_model_discovery")
        if (type(candidate.get("type")) is not int or candidate["type"] != 3
                or candidate.get("sn") != node.get("sn")
                or not isinstance(discovery, dict) or discovery.get("result") != "identified"
                or discovery.get("source") not in {"web_tree", "micro_detail"}):
            reason = "unverified_model_metadata"
            return None
        model = inverter_model(candidate)
        reason = "unsupported_model"
        return model if _HMS_MODEL.fullmatch(model) else None

    def has_storage(value):
        if isinstance(value, dict):
            return value.get("type") == 12 or any(has_storage(child) for child in value.values())
        return isinstance(value, list) and any(has_storage(child) for child in value)

    def visit(nodes):
        nonlocal reason
        if not isinstance(nodes, list) or not nodes:
            reason = "invalid_children"
            return False
        for node in nodes:
            if not isinstance(node, dict):
                reason = "invalid_node"
                return False
            kind, identity = node.get("type"), node.get("id")
            if type(kind) is not int or kind not in (1, 2, 3):
                reason = "unsupported_device_type"
                return False
            if type(identity) is not int or identity <= 0:
                reason = "invalid_device_id"
                return False
            if (kind, identity) in identities:
                reason = "duplicate_device"
                return False
            identities.add((kind, identity))
            if kind == 3:
                model = model_for(node)
                if model is None:
                    return False
                inverters.append({"id": identity, "model": model})
            # Home DevicesDTO nests physical nodes in `devices`; the web
            # tree uses `children`. Both must be checked, including conflicts.
            for key in ("children", "devices"):
                children = node.get(key)
                if children is not None and children != [] and not visit(children):
                    return False
        return True

    if has_storage(tree):
        return None, "storage_present"
    if not isinstance(tree, list):
        return None, "unsupported_tree_shape"
    if not tree:
        return None, "empty_tree"
    if not visit(tree):
        return None, reason
    if len(inverters) != 1:
        return None, "no_inverter" if not inverters else "multiple_inverters"
    return {"inverter": inverters[0], "devices": tuple(sorted(identities))}, "recognized"
