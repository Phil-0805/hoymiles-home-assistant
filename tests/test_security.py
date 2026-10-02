"""Tests for outbound API host validation."""

import importlib.util
from pathlib import Path
import unittest

MODULE = Path(__file__).parents[1] / "custom_components/hoymiles_home/security.py"
SPEC = importlib.util.spec_from_file_location("hoymiles_security", MODULE)
security = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(security)


class TestTrustedHoymilesUrl(unittest.TestCase):
    def test_accepts_hoymiles_https_hosts(self):
        for url in (
            "https://neapi.hoymiles.com/pvmc/api/0/station",
            "https://euapi.hoymiles.com/live",
            "https://hoymiles.com/path",
        ):
            with self.subTest(url=url):
                self.assertTrue(security.trusted_hoymiles_url(url))

    def test_rejects_untrusted_destinations(self):
        for url in (
            "http://neapi.hoymiles.com/live",
            "https://hoymiles.com.evil.example/live",
            "https://evil.example/live",
            "https://user:pass@neapi.hoymiles.com/live",
            "https://neapi.hoymiles.com:444/live",
            "https://neapi.hoymiles.com:invalid/live",
            "//neapi.hoymiles.com/live",
        ):
            with self.subTest(url=url):
                self.assertFalse(security.trusted_hoymiles_url(url))
