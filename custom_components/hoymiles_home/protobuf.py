"""Minimal decoder for Hoymiles LineChart protobuf responses."""

from __future__ import annotations

import re
import struct
from math import isfinite
from typing import Any


class ProtobufDecodeError(ValueError):
    """Raised for malformed protobuf data."""


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


def chart_labels(chart):
    """Validate the Home day-chart axis before associating values with times."""
    labels = chart["labels"]
    if (not labels or len(labels) > 10000
            or any(not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", label) for label in labels)
            or labels != sorted(set(labels))):
        raise ProtobufDecodeError("Invalid chart time axis")
    return labels


def latest_series_sample(series, labels, latest_time=None):
    """Return an aligned finite sample; never assign missing tails a later time."""
    values = series["data"]
    if len(values) > len(labels):
        raise ProtobufDecodeError("Misaligned chart series")
    if latest_time is not None and (not isinstance(latest_time, str)
            or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", latest_time)):
        raise ProtobufDecodeError("Invalid chart cutoff time")
    for index in range(len(values) - 1, -1, -1):
        if isfinite(values[index]) and (latest_time is None or labels[index] <= latest_time):
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
            raise ProtobufDecodeError("Ambiguous module chart series")
        seen.add(key)
        sample = latest_series_sample(series, labels, latest_time)
        if sample is not None:
            result[key], result["_sample_times"][key] = round(sample[0], 3), sample[1]
    return result
