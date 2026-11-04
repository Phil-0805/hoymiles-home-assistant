"""Run HA tests while the upstream fixture package catches up with Core 2026.11."""

from importlib.metadata import version
from pathlib import Path
import sys

# Core 2026.11 must establish its httpx alias before pytest loads HTTP plugins.
import homeassistant  # noqa: F401

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if version("homeassistant") == "2026.11.0" and version("pytest-homeassistant-custom-component") == "0.13.375":
    from homeassistant.components import logger

    if not hasattr(logger, "_clear_logger_overwrites"):
        def unsupported_logger_fixture(*args, **kwargs):
            """Fail explicitly if an outdated logger fixture is actually used."""
            raise RuntimeError("The logger fixture needs an upstream update for Core 2026.11")

        # The old fixture module imports this removed private function. None of
        # our tests calls its logger context manager; do not emulate Core logic.
        logger._clear_logger_overwrites = unsupported_logger_fixture

import pytest  # noqa: E402

raise SystemExit(pytest.main(sys.argv[1:] or ["tests/ha", "-q"]))
