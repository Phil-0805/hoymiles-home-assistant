"""Require device evidence or the explicit, scoped v0.5.0 maintainer exception.

This validates the maintainer's recorded evidence, not the truth of a hardware
test. Do not populate confirmations from automated/synthetic tests.
"""

import argparse
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

REQUIRED = {"hms1000_model", "battery_settings", "pv_display", "status_documentation",
            "power_setting", "day_night_recovery", "optional_telemetry",
            "mode_switch", "battery_temperature"}


def accepted_exception(data, version):
    """Recognize only the maintainer's explicit b6-to-0.5.0 decision.

    This accepts documented limitations for publication; it never turns missing
    device evidence into a confirmation or authorizes another release/candidate.
    """
    decision = data.get("maintainer_exception")
    if not isinstance(decision, dict):
        return set()
    if (version != "0.5.0" or decision.get("target_version") != version
            or data.get("candidate_version") != "0.5.0b6"
            or decision.get("candidate_version") != data.get("candidate_version")
            or decision.get("candidate_commit") != "1525a5231a600e9ea6bf592d7231691b7643d080"
            or decision.get("approved_by") != "Phil-0805"
            or decision.get("source") != "Explicit maintainer approval in project chat on 2026-11-02"
            or decision.get("limitations_document") != "docs/release-0.5.0.md"):
        return set()
    try:
        if date.fromisoformat(decision.get("approved_on", "")) != date(2026, 11, 2):
            return set()
    except (TypeError, ValueError):
        return set()
    reason = decision.get("reason")
    reports = decision.get("accepted_pending_reports")
    if (not isinstance(reason, str) or not reason.strip()
            or not isinstance(reports, list)
            or not all(isinstance(item, str) for item in reports)
            or len(reports) != len(REQUIRED) or set(reports) != REQUIRED):
        return set()
    return set(reports)


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
    accepted = accepted_exception(data, version)
    if "maintainer_exception" in data and not accepted:
        errors.append("Maintainer exception is invalid or outside its release/candidate scope")
    for row in rows:
        identifier = row.get("id")
        if identifier in accepted and row.get("confirmed") is False:
            # Keep incomplete reports visibly unconfirmed. A claimed successful
            # device test must still satisfy the normal evidence requirements.
            continue
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
    data = json.loads(record.read_text())
    errors = validate(data, args.version)
    if errors:
        raise SystemExit("Stable release blocked:\n- " + "\n- ".join(errors))
    if accepted_exception(data, args.version):
        print("Publication approved with the recorded v0.5.0 maintainer exception; device confirmations remain pending.")
    else:
        print("Recorded confirmations and maintainer approval are complete.")


if __name__ == "__main__":
    main()
