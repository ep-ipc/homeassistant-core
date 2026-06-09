"""Fixtures for Savant Host tests."""

import asyncio
from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.components.savanthost.const import DOMAIN
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.util.json import json_loads

from tests.common import MockConfigEntry, load_fixture, load_json_object_fixture


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return the default mocked config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.10", CONF_PORT: 3060},
        unique_id="01C969E8-DE52-49D9-A63B-553B8A19503B",
        title="Lloyds Prototype",
    )


@pytest.fixture
def mock_savant_api() -> Generator[AsyncMock]:
    """Mock Savant API."""
    with (
        patch(
            "homeassistant.components.savanthost.coordinator.SavantApi",
            autospec=True,
        ) as coordinator_api,
        patch(
            "homeassistant.components.savanthost.config_flow.SavantApi",
            new=coordinator_api,
        ),
    ):
        api = coordinator_api.return_value
        api.async_get_active_configuration.return_value = load_json_object_fixture(
            "configuration_active.json", DOMAIN
        )
        api.async_get_lighting_config.return_value = load_json_object_fixture(
            "lighting.json", DOMAIN
        )
        api.async_get_loads.return_value = json_loads(
            load_fixture("loads.json", DOMAIN)
        )
        api.async_get_feedback_states.return_value = load_json_object_fixture(
            "feedback_states.json", DOMAIN
        )
        api.async_turn_on_load.return_value = None
        api.async_turn_off_load.return_value = None
        api.async_set_load_level.return_value = None
        yield api


@pytest.fixture(autouse=True)
def mock_websocket() -> Generator[AsyncMock]:
    """Mock Savant feedback WebSocket."""

    async def _block_forever(*_args, **_kwargs) -> None:
        await asyncio.Event().wait()

    with patch(
        "homeassistant.components.savanthost.coordinator.SavantFeedbackWebSocket",
        autospec=True,
    ) as ws_class:
        ws = ws_class.return_value
        ws.async_listen.side_effect = _block_forever
        ws.async_disconnect.return_value = None
        yield ws


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_savant_api: AsyncMock,
    mock_websocket: AsyncMock,
) -> MockConfigEntry:
    """Set up the Savant Host integration."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    return mock_config_entry
