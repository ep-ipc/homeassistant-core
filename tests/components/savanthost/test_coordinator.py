"""Test Savant Host coordinator."""

from homeassistant.components.savanthost.models import (
    SavantConfiguration,
    SavantHostData,
    SavantLoad,
    apply_state_updates,
    flatten_feedback_state_keys,
    match_load_state_keys,
    parse_lighting_devices,
    parse_loads,
    parse_rooms,
)
from homeassistant.components.savanthost.websocket import parse_ws_update
from homeassistant.core import HomeAssistant
from homeassistant.util.json import json_loads

from tests.common import MockConfigEntry, load_fixture, load_json_object_fixture


async def test_coordinator_filters_switch_loads(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_savant_api,
    mock_websocket,
) -> None:
    """Test coordinator excludes switch device loads."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    coordinator = mock_config_entry.runtime_data
    assert len(coordinator.data.loads) == 1
    load = next(iter(coordinator.data.loads.values()))
    assert load.name == "Guest 1st FL Bathroom Lights"
    assert load.state_keys == [
        "Guest Room Downstairs.Guest 1st FL Bathroom LightsLoadLevel"
    ]


def test_parse_ws_update() -> None:
    """Test WebSocket update parsing."""
    message = load_json_object_fixture("ws_update.json", "savanthost")
    updates = parse_ws_update(message)
    assert updates == {
        "Guest Room Downstairs.Guest 1st FL Bathroom LightsLoadLevel": "75"
    }


def test_flatten_feedback_state_keys_state_name_format() -> None:
    """Test parsing feedback states with stateName entries."""
    keys = flatten_feedback_state_keys(
        {
            "ZoneStates": [
                {"stateName": "Kitchen.BrightnessLevel", "stateType": "int"},
                {"stateName": "Kitchen.LightsAreOn", "stateType": "boolean"},
            ]
        }
    )
    assert keys == ["Kitchen.BrightnessLevel", "Kitchen.LightsAreOn"]


def test_flatten_feedback_state_keys_legacy_format() -> None:
    """Test parsing legacy feedback states with state keys as dict keys."""
    keys = flatten_feedback_state_keys(
        {
            "ZoneStates": [
                {"Guest Room Downstairs.Guest 1st FL Bathroom LightsLoadLevel": "0"}
            ]
        }
    )
    assert keys == ["Guest Room Downstairs.Guest 1st FL Bathroom LightsLoadLevel"]


def test_match_load_state_keys_room_level_fallback() -> None:
    """Test room-level fallback when per-load states are unavailable."""
    load = SavantLoad(
        load_id="load-1",
        device_id="device-1",
        room_id="room-1",
        name="Kitchen Downlights",
    )
    state_keys = [
        "Kitchen.BrightnessLevel",
        "Kitchen.LightsAreOn",
        "Kitchen.ZoneIsActive",
    ]
    matched = match_load_state_keys(load, "Kitchen", state_keys)
    assert matched == [
        "Kitchen.BrightnessLevel",
        "Kitchen.LightsAreOn",
    ]


def test_apply_state_updates() -> None:
    """Test merging state updates into coordinator data."""
    lighting = load_json_object_fixture("lighting.json", "savanthost")
    loads_data = json_loads(load_fixture("loads.json", "savanthost"))
    loads = parse_loads(loads_data, parse_lighting_devices(lighting))
    data = SavantHostData(
        configuration=SavantConfiguration(
            configuration_id="01C969E8-DE52-49D9-A63B-553B8A19503B",
            name="Lloyds Prototype",
        ),
        rooms=parse_rooms(lighting),
        loads=loads,
        states={},
    )
    load = next(iter(loads.values()))
    load.state_keys = ["Guest Room Downstairs.Guest 1st FL Bathroom LightsLoadLevel"]

    updated = apply_state_updates(
        data,
        {"Guest Room Downstairs.Guest 1st FL Bathroom LightsLoadLevel": "50"},
    )
    assert updated.get_load_level(load.load_id) == 50


def test_get_load_level_from_boolean_state() -> None:
    """Test load level derived from room-level LightsAreOn state."""
    load = SavantLoad(
        load_id="load-1",
        device_id="device-1",
        room_id="room-1",
        name="Kitchen Downlights",
        state_keys=["Kitchen.LightsAreOn"],
    )
    data = SavantHostData(
        configuration=SavantConfiguration(
            configuration_id="config-1",
            name="Test Host",
        ),
        rooms={},
        loads={"load-1": load},
        states={"Kitchen.LightsAreOn": "1"},
    )
    assert data.get_load_level("load-1") == 100
