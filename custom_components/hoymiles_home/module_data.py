"""Read-only PlayModuleData decoder, independent of the Node-RED implementation.

Only expose known numeric telemetry. Never interpret fault codes or copy raw
payloads/identifiers into diagnostics. Schema cross-checked against the pinned
Node-RED module-data decoder; hardware validation remains separate.
"""

from __future__ import annotations

import gzip
import io
import re
import struct

from .protobuf import ProtobufDecodeError, iter_fields
from .telemetry import number

MAX_MODULE_BYTES = 8 * 1024 * 1024
DETAIL_FIELDS = {5: "frequency", 6: "temperature", 7: "voltage"}


def _floats(wire, value):
    if wire == 5:
        return [struct.unpack("<f", value)[0]]
    if wire == 2 and len(value) % 4 == 0:
        return list(struct.unpack(f"<{len(value) // 4}f", value))
    raise ProtobufDecodeError("Invalid module float data")


def _map_entry(raw):
    key, value = None, None
    for field, wire, item in iter_fields(raw):
        if field == 1 and wire == 0:
            key = item
        elif field == 2 and wire == 2:
            value = item
    if not isinstance(key, int) or key <= 0 or value is None:
        raise ProtobufDecodeError("Invalid module map entry")
    return key, value


def decode_module_snapshot(raw: bytes, station_id: int, date: str) -> dict:
    """Decode only a matching station/day and aligned latest inverter sample."""
    if len(raw) > MAX_MODULE_BYTES:
        raise ProtobufDecodeError("Module response exceeds size limit")
    if raw.startswith(b"\x1f\x8b"):
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
                raw = stream.read(MAX_MODULE_BYTES + 1)
        except (OSError, EOFError) as err:
            raise ProtobufDecodeError("Invalid compressed module response") from err
        if len(raw) > MAX_MODULE_BYTES:
            raise ProtobufDecodeError("Decoded module response exceeds size limit")

    sid, response_date = None, None
    micros = {}
    for field, wire, value in iter_fields(raw):
        if field == 1 and wire == 0:
            sid = value
        elif field == 2 and wire == 2:
            response_date = value.decode("utf-8")
        elif field == 3 and wire == 2:
            device_id, micro = _map_entry(value)
            if device_id in micros:
                raise ProtobufDecodeError("Duplicate inverter in module response")
            micros[device_id] = micro
    if sid != station_id or response_date != date:
        raise ProtobufDecodeError("Module station/date mismatch")

    inverters = {}
    for device_id, micro in micros.items():
        times, values = [], {key: [] for key in DETAIL_FIELDS.values()}
        for field, wire, value in iter_fields(micro):
            if field == 2 and wire == 2:
                times.append(value.decode("utf-8"))
            elif field in DETAIL_FIELDS:
                values[DETAIL_FIELDS[field]].extend(_floats(wire, value))
        if not times:
            continue
        last = len(times) - 1
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", times[last]):
            continue
        inverters[device_id] = {
            "time": times[last],
            **{key: number(items[last]) if last < len(items) else None
               for key, items in values.items()},
        }
    return {"date": date, "inverters": inverters}
