"""Tests for the dependency-free chart decoder."""

import importlib.util
from pathlib import Path
import struct
import unittest

MODULE = Path(__file__).parents[1] / "custom_components/hoymiles_home/protobuf.py"
SPEC = importlib.util.spec_from_file_location("hoymiles_protobuf", MODULE)
protobuf = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(protobuf)


def varint(value: int) -> bytes:
    result = bytearray()
    while value > 0x7F:
        result.append((value & 0x7F) | 0x80)
        value >>= 7
    result.append(value)
    return bytes(result)


def length_field(number: int, value: bytes) -> bytes:
    return varint((number << 3) | 2) + varint(len(value)) + value


class TestChartDecoder(unittest.TestCase):
    def test_latest_values(self):
        series = b"".join(
            (
                length_field(1, b"MODULE_POWER"),
                length_field(2, struct.pack("<fff", 31.4, 41.3, 42.2)),
                varint(3 << 3) + varint(34000100),
                varint(4 << 3) + varint(1),
            )
        )
        chart = length_field(1, b"09:05") + length_field(2, series)
        values = protobuf.latest_values(chart)
        self.assertAlmostEqual(values["MODULE_POWER"], 42.2, places=2)

    def test_rejects_truncated_data(self):
        with self.assertRaises(protobuf.ProtobufDecodeError):
            protobuf.decode_line_chart(b"\x0a\x05x")


if __name__ == "__main__":
    unittest.main()
