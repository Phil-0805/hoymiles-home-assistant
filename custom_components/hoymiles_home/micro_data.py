"""Timestamped Home microinverter charts; distinct from Installer float64."""

import re

from .protobuf import ProtobufDecodeError, decode_line_chart
from .telemetry import number

MICRO_QUOTAS = {"MI_TEMPERATURE": "temperature", "MI_NET_RATE": "frequency", "MI_NET_V": "voltage"}


def decode_micro_details(raw, device_ids):
    """Keep exact device identities and each metric's own aligned sample time."""
    chart = decode_line_chart(raw)
    labels = chart["labels"]
    if (not labels or len(labels) > 10000
            or any(not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", label) for label in labels)
            or labels != sorted(set(labels))):
        raise ProtobufDecodeError("Invalid microinverter chart axis")
    result, seen = {}, set()
    for series in chart["series"]:
        identity, key = series["device_id"], MICRO_QUOTAS.get(series["type"])
        if identity not in device_ids or key is None or series["port"] != 0:
            continue
        if (identity, key) in seen:
            raise ProtobufDecodeError("Ambiguous microinverter chart series")
        seen.add((identity, key))
        values = series["data"]
        # Missing tails do not receive the last label's timestamp.
        if len(values) > len(labels):
            raise ProtobufDecodeError("Misaligned microinverter chart series")
        for index in range(len(values) - 1, -1, -1):
            value = number(values[index])
            if value is not None:
                result.setdefault(identity, {}).update({key: value, f"{key}_time": labels[index]})
                break
    return {"inverters": result}
