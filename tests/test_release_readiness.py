"""The stable publication gate must fail closed on incomplete evidence."""

import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("readiness", ROOT / "scripts/check_release_readiness.py")
readiness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(readiness)


class TestReleaseReadiness(unittest.TestCase):
    def complete_fixture(self):
        # Fictional test evidence only; never write it to the actual record.
        data = json.loads((ROOT / "docs/release-readiness.json").read_text())
        data["maintainer_approved"] = True
        for row in data["reports"]:
            row.update(confirmed=True, confirmed_by="example-tester",
                       tested_version=data["candidate_version"],
                       evidence_url="https://github.com/Phil-0805/hoymiles-home-assistant/issues/9#issuecomment-123")
        return data

    def test_complete_fixture_can_pass(self):
        self.assertEqual(readiness.validate(self.complete_fixture(), "0.5.0"), [])

    def test_pending_report_blocks_release(self):
        data = self.complete_fixture()
        data["reports"][0]["confirmed"] = False
        self.assertTrue(readiness.validate(data, "0.5.0"))

    def test_wrong_candidate_or_missing_author_cannot_pass(self):
        for key, value in [("tested_version", "old"), ("confirmed_by", "")]:
            data = self.complete_fixture()
            data["reports"][0][key] = value
            self.assertTrue(readiness.validate(data, "0.5.0"))

    def test_missing_duplicate_or_external_evidence_is_rejected(self):
        data = self.complete_fixture()
        data["reports"][0] = copy.deepcopy(data["reports"][1])
        self.assertTrue(readiness.validate(data, "0.5.0"))
        data = self.complete_fixture()
        data["reports"][0]["evidence_url"] = "https://example.com/confirmation"
        self.assertTrue(readiness.validate(data, "0.5.0"))

    def test_wrong_release_and_nonboolean_approval_are_rejected(self):
        data = self.complete_fixture()
        self.assertTrue(readiness.validate(data, "0.6.0"))
        data["maintainer_approved"] = "true"
        self.assertTrue(readiness.validate(data, "0.5.0"))
