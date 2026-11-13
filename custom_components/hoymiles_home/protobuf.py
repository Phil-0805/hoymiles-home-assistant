"""Minimal decoder for Hoymiles LineChart protobuf responses."""

from __future__ import annotations

import re
import struct
from math import isfinite
from typing import Any


class ProtobufDecodeError(ValueError):
    """Raised for malformed protobuf data, with a fixed diagnostic reason."""

    def __init__(self, message, *, reason="invalid_protobuf"):
        super().__init__(message)
        self.reason = reason


def _varint(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while offset < len(data) and shift < 70:
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, offset
        shift += 7
    raise ProtobufDecodeError("Invalid varint")


def _fields(data: bytes):
    offset = 0
    while offset < len(data):
        tag, offset = _varint(data, offset)
        number, wire = tag >> 3, tag & 7
        if number == 0:
            raise ProtobufDecodeError("Invalid field number")
        if wire == 0:
            value, offset = _varint(data, offset)
        elif wire == 2:
            length, offset = _varint(data, offset)
            end = offset + length
            if end > len(data):
                raise ProtobufDecodeError("Truncated length-delimited field")
            value, offset = data[offset:end], end
        elif wire == 5:
            if offset + 4 > len(data):
                raise ProtobufDecodeError("Truncated float field")
            value, offset = data[offset : offset + 4], offset + 4
        elif wire == 1:
            if offset + 8 > len(data):
                raise ProtobufDecodeError("Truncated fixed64 field")
            value, offset = data[offset : offset + 8], offset + 8
        else:
            raise ProtobufDecodeError(f"Unsupported wire type {wire}")
        yield number, wire, value


def iter_fields(data: bytes):
    """Iterate bounded wire fields for the chart and module-data decoders."""
    yield from _fields(data)


def _line_series(data: bytes) -> dict[str, Any]:
    result: dict[str, Any] = {"type": "", "data": [], "device_id": 0, "port": 0}
    for number, wire, value in _fields(data):
        if number == 1 and wire == 2:
            result["type"] = value.decode("utf-8")
        elif number == 2 and wire == 2:
            if len(value) % 4:
                raise ProtobufDecodeError("Invalid packed float data")
            result["data"].extend(struct.unpack(f"<{len(value) // 4}f", value))
        elif number == 2 and wire == 5:
            result["data"].append(struct.unpack("<f", value)[0])
        elif number == 3 and wire == 0:
            result["device_id"] = value
        elif number == 4 and wire == 0:
            result["port"] = value
    return result


def decode_line_chart(data: bytes) -> dict[str, Any]:
    """Decode the LineChart message used by count_by_day_c endpoints."""
    result: dict[str, Any] = {"labels": [], "series": [], "type": ""}
    for number, wire, value in _fields(data):
        if number == 1 and wire == 2:
            result["labels"].append(value.decode("utf-8"))
        elif number == 2 and wire == 2:
            result["series"].append(_line_series(value))
        elif number == 3 and wire == 2:
            result["type"] = value.decode("utf-8")
    return result


def latest_values(
    data: bytes, *, device_id: int | None = None, port: int | None = None
) -> dict[str, float | None]:
    """Return the latest sample per chart series."""
    chart = decode_line_chart(data)
    result = {}
    for series in chart["series"]:
        if not series["type"]:
            continue
        # Some responses omit identity fields (decoded as zero). Reject
        # explicit conflicts, never route another device/port into this one.
        if device_id is not None and series["device_id"] not in (0, device_id):
            continue
        if port is not None and series["port"] not in (0, port):
            continue
        value = series["data"][-1] if series["data"] else None
        result[series["type"]] = (
            round(float(value), 3) if value is not None and isfinite(value) else None
        )
    return result


def chart_time(label):
    """Normalize unambiguous minute labels, including a day-end axis boundary.

    The app treats hours/minutes numerically, without requiring a zero-padded
    hour. 24:00 is an end boundary, never midnight on the requested day.
    """
    if not isinstance(label, str):
        return None
    match = re.fullmatch(r"([0-9]{1,2}):([0-5][0-9])", label)
    if match is None:
        return None
    hour, minute = map(int, match.groups())
    if hour > 24 or (hour == 24 and minute != 0):
        return None
    return f"{hour:02d}:{minute:02d}"


def chart_labels(chart):
    """Validate the Home day-chart axis before associating values with times."""
    labels = chart["labels"]
    if not labels:
        raise ProtobufDecodeError("Missing chart time axis", reason="empty_axis")
    if len(labels) > 10000:
        raise ProtobufDecodeError("Oversized chart time axis", reason="oversized_axis")
    labels = [chart_time(label) for label in labels]
    if any(label is None for label in labels):
        raise ProtobufDecodeError("Unsupported chart time axis", reason="unsupported_axis_format")
    if labels != sorted(set(labels)):
        raise ProtobufDecodeError("Unordered chart time axis", reason="unordered_axis")
    return labels


def latest_series_sample(series, labels, latest_time=None):
    """Return an aligned finite sample; never assign missing tails a later time."""
    values = series["data"]
    if len(values) > len(labels):
        raise ProtobufDecodeError("Misaligned chart series", reason="misaligned_series")
    if latest_time is not None:
        latest_time = chart_time(latest_time)
        if latest_time is None or latest_time == "24:00":
            raise ProtobufDecodeError("Invalid chart cutoff time", reason="invalid_cutoff")
    for index in range(len(values) - 1, -1, -1):
        if (labels[index] != "24:00" and isfinite(values[index])
                and (latest_time is None or labels[index] <= latest_time)):
            return float(values[index]), labels[index]
    return None


def latest_module_samples(data, *, device_id, port, latest_time=None):
    """Keep per-metric sample labels for a single requested Home PV input."""
    chart = decode_line_chart(data)
    labels = chart_labels(chart)
    result = {"_sample_times": {}}
    seen = set()
    for series in chart["series"]:
        key = series["type"]
        if (key not in {"MODULE_POWER", "MODULE_V", "MODULE_I"}
                or series["device_id"] not in (0, device_id)
                or series["port"] not in (0, port)):
            continue
        if key in seen:
            raise ProtobufDecodeError("Ambiguous module chart series", reason="duplicate_series")
        seen.add(key)
        sample = latest_series_sample(series, labels, latest_time)
        if sample is not None:
            result[key], result["_sample_times"][key] = round(sample[0], 3), sample[1]
    return result
