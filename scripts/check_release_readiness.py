"""Validate private, version- and commit-bound stable release approval."""

import argparse
import json
import os
from pathlib import Path
import re


def validate(data, version, commit):
    """Reject missing/stale decisions without printing private record contents."""
    if not isinstance(data, dict):
        return ["Approval must be a JSON object"]
    errors = []
    if data.get("schema_version") != 1:
        errors.append("Unsupported approval schema")
    if data.get("target_version") != version:
        errors.append("Approval does not match the release version")
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or data.get("candidate_commit") != commit:
        errors.append("Approval does not match the exact release commit")
    if data.get("maintainer_approved") is not True:
        errors.append("Maintainer approval is pending")
    # A release decision acknowledges limitations; it never certifies hardware.
    if data.get("limitations_reviewed") is not True:
        errors.append("Review of documented limitations is pending")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--record", type=Path, help="Private approval file for local checks")
    args = parser.parse_args()
    if not re.fullmatch(r"\d+\.\d+\.\d+", args.version):
        raise SystemExit("Invalid stable release version")
    try:
        raw = args.record.read_text() if args.record else os.environ.get("RELEASE_READINESS_JSON", "")
        data = json.loads(raw)
    except (OSError, ValueError):
        raise SystemExit("Stable release blocked: private approval is missing or invalid") from None
    errors = validate(data, args.version, args.commit)
    if errors:
        raise SystemExit("Stable release blocked:\n- " + "\n- ".join(errors))
    print("Stable publication approved for this version and commit; no hardware certification is implied.")


if __name__ == "__main__":
    main()
