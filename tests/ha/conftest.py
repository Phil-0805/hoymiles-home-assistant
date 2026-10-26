"""Home Assistant fixtures for the setup-flow beta."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def custom_integration(enable_custom_integrations):
    """Load this repository's integration without starting live cloud polling."""
    with patch(
        "custom_components.hoymiles_home.async_setup_entry",
        new=AsyncMock(return_value=True),
    ):
        yield


@pytest.fixture
def client():
    """Mock only the cloud boundary; retain Home Assistant's real flow engine."""
    with patch(
        "custom_components.hoymiles_home.config_flow.HoymilesHomeClient"
    ) as constructor:
        api = constructor.return_value
        api.async_login = AsyncMock()
        api.async_list_stations = AsyncMock(
            return_value=[{"sid": 123, "name": "Home"}, {"sid": 456, "name": "Home"}]
        )
        api.async_device_tree = AsyncMock(return_value=[{"id": 999, "type": 3}])
        yield api
