"""Timestamped Home microinverter charts; distinct from Installer float64."""

from .protobuf import ProtobufDecodeError, decode_line_chart, chart_labels, latest_series_sample

MICRO_QUOTAS = {"MI_TEMPERATURE": "temperature", "MI_NET_RATE": "frequency", "MI_NET_V": "voltage"}


def decode_micro_details(raw, device_ids, *, latest_time=None):
    """Keep exact device identities and each metric's own aligned sample time."""
    chart = decode_line_chart(raw)
    labels = chart_labels(chart)
    result, seen = {}, set()
    for series in chart["series"]:
        identity, key = series["device_id"], MICRO_QUOTAS.get(series["type"])
        if identity not in device_ids or key is None or series["port"] != 0:
            continue
        if (identity, key) in seen:
            raise ProtobufDecodeError("Ambiguous microinverter chart series", reason="duplicate_series")
        seen.add((identity, key))
        sample = latest_series_sample(series, labels, latest_time)
        if sample is not None:
            result.setdefault(identity, {}).update({key: sample[0], f"{key}_time": sample[1]})
    return {"inverters": result}
