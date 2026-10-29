"""Block accidental stable publication while user validation is outstanding.

This validates the maintainer's recorded evidence, not the truth of a hardware
test. Do not populate confirmations from automated/synthetic tests.
"""

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

REQUIRED = {"hms1000_model", "battery_settings", "pv_display", "status_documentation",
            "power_setting", "day_night_recovery", "optional_telemetry",
            "mode_switch", "battery_temperature"}


def validate(data, version):
    errors = []
    if data.get("schema_version") != 1 or data.get("target_version") != version:
        errors.append("Readiness record does not match the target stable release")
    if data.get("maintainer_approved") is not True:
        errors.append("Maintainer approval is pending")
    rows = data.get("reports", [])
    if not isinstance(rows, list) or {r.get("id") for r in rows if isinstance(r, dict)} != REQUIRED or len(rows) != len(REQUIRED):
        return errors + ["Required validation reports are missing or duplicated"]
    candidate = data.get("candidate_version")
    if not isinstance(candidate, str) or not candidate:
        errors.append("Candidate version is missing")
    for row in rows:
        identifier = row.get("id")
        if row.get("confirmed") is not True:
            errors.append(f"{identifier}: user/device confirmation is pending")
        if not isinstance(row.get("confirmed_by"), str) or not row["confirmed_by"].strip():
            errors.append(f"{identifier}: confirmation author is missing")
        if row.get("tested_version") != candidate:
            errors.append(f"{identifier}: confirmation is for a different candidate")
        try:
            url = urlsplit(row.get("evidence_url") or "")
            valid = (url.scheme == "https" and url.hostname == "github.com"
                     and url.username is None and url.password is None
                     and re.fullmatch(r"/Phil-0805/hoymiles-home-assistant/issues/\d+", url.path)
                     and re.fullmatch(r"issuecomment-\d+", url.fragment))
        except ValueError:
            valid = False
        if not valid:
            errors.append(f"{identifier}: link to a recorded issue confirmation is missing")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    record = Path(__file__).resolve().parents[1] / "docs/release-readiness.json"
    errors = validate(json.loads(record.read_text()), args.version)
    if errors:
        raise SystemExit("Stable release blocked:\n- " + "\n- ".join(errors))
    print("Recorded confirmations and maintainer approval are complete.")


if __name__ == "__main__":
    main()
