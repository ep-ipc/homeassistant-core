"""Data models for the Savant Host integration."""

from dataclasses import dataclass, field
from typing import Any

STATE_LEVEL_SUFFIXES = ("level", "brightness", "dimmer")


@dataclass(slots=True)
class SavantConfiguration:
    """Active Savant configuration."""

    configuration_id: str
    name: str


@dataclass(slots=True)
class SavantRoom:
    """Savant room metadata."""

    room_id: str
    name: str


@dataclass(slots=True)
class SavantLightingDevice:
    """Savant lighting hardware device."""

    device_id: str
    room_id: str
    name: str
    dimmer_is_switch: bool


@dataclass(slots=True)
class SavantLoad:
    """Savant lighting load."""

    load_id: str
    device_id: str
    room_id: str
    name: str
    state_keys: list[str] = field(default_factory=list)
    supports_brightness: bool = True


@dataclass(slots=True)
class SavantHostData:
    """Coordinator data for a Savant host."""

    configuration: SavantConfiguration
    rooms: dict[str, SavantRoom]
    loads: dict[str, SavantLoad]
    states: dict[str, str] = field(default_factory=dict)

    def get_load_level(self, load_id: str) -> int | None:
        """Return the Savant load level (0-100) for a load."""
        load = self.loads.get(load_id)
        if load is None:
            return None
        boolean_level: int | None = None
        for state_key in load.state_keys:
            if (value := self.states.get(state_key)) is None:
                continue
            key_lower = state_key.lower()
            if any(suffix in key_lower for suffix in STATE_LEVEL_SUFFIXES):
                try:
                    return int(value)
                except ValueError:
                    continue
            if "lightsareon" in key_lower.replace("_", ""):
                boolean_level = _parse_boolean_level(value)
        return boolean_level


def parse_configuration(data: dict[str, Any]) -> SavantConfiguration:
    """Parse active configuration response."""
    return SavantConfiguration(
        configuration_id=data["configurationID"],
        name=data["name"],
    )


def parse_lighting_devices(
    lighting_data: dict[str, Any],
) -> dict[str, SavantLightingDevice]:
    """Build a device_id to lighting device map from lighting config."""
    devices: dict[str, SavantLightingDevice] = {}
    for room in lighting_data.get("rooms", []):
        room_id = room["roomID"]
        for device in room.get("lightingDevices", []):
            devices[device["deviceID"]] = SavantLightingDevice(
                device_id=device["deviceID"],
                room_id=room_id,
                name=device["name"],
                dimmer_is_switch=bool(device.get("dimmerIsSwitch")),
            )
    return devices


def parse_rooms(lighting_data: dict[str, Any]) -> dict[str, SavantRoom]:
    """Build a room_id to room map from lighting config."""
    return {
        room["roomID"]: SavantRoom(room_id=room["roomID"], name=room["name"])
        for room in lighting_data.get("rooms", [])
    }


def parse_loads(
    loads_data: list[dict[str, Any]],
    devices: dict[str, SavantLightingDevice],
) -> dict[str, SavantLoad]:
    """Parse and filter lighting loads."""
    loads: dict[str, SavantLoad] = {}
    for load_data in loads_data:
        load_id = load_data["loadID"]
        if load_id in loads:
            continue
        device_id = load_data["deviceID"]
        device = devices.get(device_id)
        if device is None or device.dimmer_is_switch:
            continue
        loads[load_id] = SavantLoad(
            load_id=load_id,
            device_id=device_id,
            room_id=load_data["roomID"],
            name=load_data["name"],
            supports_brightness=load_data.get("max", 100) != load_data.get("min", 0),
        )
    return loads


def flatten_feedback_state_keys(feedback_data: dict[str, Any]) -> list[str]:
    """Extract feedback state key names from a feedback states response."""
    keys: list[str] = []
    for category in ("GlobalStates", "ServiceStates", "ZoneStates"):
        for item in feedback_data.get(category, []):
            if not isinstance(item, dict):
                continue
            state_name = item.get("stateName")
            if isinstance(state_name, str) and state_name not in keys:
                keys.append(state_name)
                continue
            for key, value in item.items():
                if key in ("stateName", "stateType"):
                    continue
                if isinstance(key, str) and "." in key and key not in keys:
                    keys.append(key)
                if isinstance(value, str) and "." in value and value not in keys:
                    keys.append(value)
    return keys


def match_load_state_keys(
    load: SavantLoad, room_name: str, state_keys: list[str]
) -> list[str]:
    """Match feedback state keys to a lighting load."""
    load_name_lower = load.name.lower()
    load_name_compact = load_name_lower.replace(" ", "")
    room_name_lower = room_name.lower()
    matched: list[str] = []

    for key in state_keys:
        key_lower = key.lower()
        key_compact = key_lower.replace(" ", "")
        name_in_key = load_name_lower in key_lower or load_name_compact in key_compact
        if not name_in_key:
            continue
        if any(suffix in key_lower for suffix in STATE_LEVEL_SUFFIXES):
            matched.append(key)

    if matched:
        return matched

    for key in state_keys:
        key_lower = key.lower()
        if load_name_lower in key_lower or load_name_compact in key_lower.replace(
            " ", ""
        ):
            matched.append(key)

    if matched:
        return matched

    room_compact = room_name_lower.replace(" ", "")
    matched = [
        pattern
        for pattern in (
            f"{room_name}.{load.name}LoadLevel",
            f"{room_name}.{load.name}Level",
            f"{room_compact}.{load_name_compact}LoadLevel",
        )
        if pattern in state_keys
    ]

    if matched:
        return matched

    return [
        candidate
        for candidate in (
            f"{room_name}.BrightnessLevel",
            f"{room_name}.LightsAreOn",
            f"{room_name}.RoomLightsAreOn",
        )
        if candidate in state_keys
    ]


def _parse_boolean_level(value: str) -> int:
    """Convert a Savant boolean state value to a load level."""
    normalized = value.strip().lower()
    if normalized in {"1", "true", "on", "yes"}:
        return 100
    return 0


def apply_state_updates(
    data: SavantHostData, updates: dict[str, str]
) -> SavantHostData:
    """Return coordinator data with merged state updates."""
    if not updates:
        return data
    new_states = {**data.states, **updates}
    return SavantHostData(
        configuration=data.configuration,
        rooms=data.rooms,
        loads=data.loads,
        states=new_states,
    )
