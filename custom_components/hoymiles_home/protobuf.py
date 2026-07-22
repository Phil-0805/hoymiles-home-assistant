"""Minimal decoder for Hoymiles LineChart protobuf responses."""

from __future__ import annotations

import struct
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


def latest_values(data: bytes) -> dict[str, float | None]:
    """Return the latest sample per chart series."""
    chart = decode_line_chart(data)
    return {
        series["type"]: round(float(series["data"][-1]), 3)
        if series["data"]
        else None
        for series in chart["series"]
        if series["type"]
    }
