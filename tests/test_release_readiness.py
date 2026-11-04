"""Private release approval must fail closed and never appear in logs."""

import copy
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts/check_release_readiness.py"
SPEC = importlib.util.spec_from_file_location("readiness", SCRIPT)
readiness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(readiness)
COMMIT = "a" * 40


class TestReleaseReadiness(unittest.TestCase):
    def fixture(self):
        return dict(schema_version=1, target_version="1.2.3", candidate_commit=COMMIT,
                    maintainer_approved=True, limitations_reviewed=True)

    def test_version_and_commit_bound_decision(self):
        data = self.fixture()
        before = copy.deepcopy(data)
        self.assertEqual(readiness.validate(data, "1.2.3", COMMIT), [])
        self.assertEqual(data, before)
        self.assertTrue(readiness.validate(data, "1.2.4", COMMIT))
        self.assertTrue(readiness.validate(data, "1.2.3", "b" * 40))
        self.assertTrue(readiness.validate(data, "1.2.3", "main"))

    def test_required_fields_fail_closed(self):
        for key in self.fixture():
            data = self.fixture()
            del data[key]
            self.assertTrue(readiness.validate(data, "1.2.3", COMMIT), key)
        for key in ("maintainer_approved", "limitations_reviewed"):
            for value in (False, "true", 1, None):
                data = self.fixture()
                data[key] = value
                self.assertTrue(readiness.validate(data, "1.2.3", COMMIT))
        for value in (None, [], "private"):
            self.assertTrue(readiness.validate(value, "1.2.3", COMMIT))

    def test_cli_never_prints_private_payload(self):
        for payload in ("", '{"private-note": "DO-NOT-LOG"}', 'DO-NOT-LOG'):
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--version", "1.2.3", "--commit", COMMIT],
                env={**os.environ, "RELEASE_READINESS_JSON": payload},
                capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("DO-NOT-LOG", result.stdout + result.stderr)
