"""Test Savant Host light platform."""

from unittest.mock import AsyncMock

from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.const import STATE_ON, STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from tests.common import MockConfigEntry

LIGHT_ENTITY_ID = "light.guest_room_downstairs_guest_1st_fl_bathroom_lights"


async def test_light_entities_created(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Test light entities are created for dimmer loads only."""
    state = hass.states.get(LIGHT_ENTITY_ID)
    assert state is not None
    assert state.state == STATE_UNKNOWN

    assert hass.states.get("light.switch_load") is None


async def test_turn_on_with_brightness(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_savant_api: AsyncMock,
) -> None:
    """Test turning on a light with brightness."""
    await hass.services.async_call(
        LIGHT_DOMAIN,
        "turn_on",
        {
            "entity_id": LIGHT_ENTITY_ID,
            "brightness": 128,
        },
        blocking=True,
    )

    mock_savant_api.async_set_load_level.assert_awaited_once_with(
        "d79e5812-ce90-421f-a4c0-fa21a4b9f70c",
        50,
    )


async def test_turn_off(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_savant_api: AsyncMock,
) -> None:
    """Test turning off a light."""
    await hass.services.async_call(
        LIGHT_DOMAIN,
        "turn_off",
        {"entity_id": LIGHT_ENTITY_ID},
        blocking=True,
    )

    mock_savant_api.async_turn_off_load.assert_awaited_once_with(
        "d79e5812-ce90-421f-a4c0-fa21a4b9f70c"
    )


async def test_state_update_from_coordinator(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Test light state reflects coordinator updates."""
    coordinator = init_integration.runtime_data
    coordinator._handle_state_update(
        {"Guest Room Downstairs.Guest 1st FL Bathroom LightsLoadLevel": "100"}
    )
    await hass.async_block_till_done()

    state = hass.states.get(LIGHT_ENTITY_ID)
    assert state is not None
    assert state.state == STATE_ON
    assert state.attributes["brightness"] == 255
