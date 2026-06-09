"""Data update coordinator for Savant Host."""

import asyncio
import contextlib

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SavantApi, SavantConnectionError
from .const import DEFAULT_PORT, DOMAIN, LOGGER, SCAN_INTERVAL, WS_RECONNECT_INTERVAL
from .models import (
    SavantHostData,
    apply_state_updates,
    flatten_feedback_state_keys,
    match_load_state_keys,
    parse_configuration,
    parse_lighting_devices,
    parse_loads,
    parse_rooms,
)
from .websocket import SavantFeedbackWebSocket

type SavantConfigEntry = ConfigEntry[SavantCoordinator]


class SavantCoordinator(DataUpdateCoordinator[SavantHostData]):
    """Coordinator for Savant Host data."""

    config_entry: SavantConfigEntry

    def __init__(self, hass: HomeAssistant, entry: SavantConfigEntry) -> None:
        """Initialize the coordinator."""
        self._api = SavantApi(
            entry.data[CONF_HOST],
            async_get_clientsession(hass),
            entry.data.get(CONF_PORT, DEFAULT_PORT),
        )
        self._websocket = SavantFeedbackWebSocket(
            entry.data[CONF_HOST],
            entry.data.get(CONF_PORT, DEFAULT_PORT),
            async_get_clientsession(hass),
        )
        self._ws_task: asyncio.Task[None] | None = None
        self._stop_listeners: CALLBACK_TYPE | None = None
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )

    async def async_shutdown(self) -> None:
        """Disconnect resources."""
        if self._ws_task is not None:
            self._ws_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._ws_task
            self._ws_task = None
        await self._websocket.async_disconnect()
        if self._stop_listeners is not None:
            self._stop_listeners()
            self._stop_listeners = None

    async def _async_update_data(self) -> SavantHostData:
        """Fetch Savant host data."""
        try:
            configuration_data = await self._api.async_get_active_configuration()
            lighting_data = await self._api.async_get_lighting_config()
            loads_data = await self._api.async_get_loads()
        except SavantConnectionError as err:
            raise UpdateFailed("Error communicating with Savant host") from err

        configuration = parse_configuration(configuration_data)
        self._async_register_hub_device(
            configuration.configuration_id, configuration.name
        )
        rooms = parse_rooms(lighting_data)
        devices = parse_lighting_devices(lighting_data)
        loads = parse_loads(loads_data, devices)

        room_state_keys: dict[str, list[str]] = {}
        for room_id in {load.room_id for load in loads.values()}:
            try:
                feedback = await self._api.async_get_feedback_states(room_id)
            except SavantConnectionError:
                LOGGER.debug("Failed to fetch feedback states for room %s", room_id)
                continue
            room_state_keys[room_id] = flatten_feedback_state_keys(feedback)

        for load in loads.values():
            room = rooms.get(load.room_id)
            room_name = room.name if room is not None else ""
            state_keys = room_state_keys.get(load.room_id, [])
            load.state_keys = match_load_state_keys(load, room_name, state_keys)

        previous_states = self.data.states if self.data is not None else {}
        data = SavantHostData(
            configuration=configuration,
            rooms=rooms,
            loads=loads,
            states=previous_states,
        )

        if self._ws_task is None:
            self._start_websocket(data)

        return data

    @callback
    def _handle_state_update(self, updates: dict[str, str]) -> None:
        """Handle WebSocket state updates."""
        if self.data is None:
            return
        self.async_set_updated_data(apply_state_updates(self.data, updates))

    def _start_websocket(self, data: SavantHostData) -> None:
        """Start the feedback WebSocket listener."""
        state_keys = sorted(
            {key for load in data.loads.values() for key in load.state_keys}
        )
        if not state_keys:
            unmatched = [
                load.name for load in data.loads.values() if not load.state_keys
            ]
            LOGGER.warning(
                "No feedback state keys matched for %d loads; WebSocket listener "
                "not started. Examples: %s",
                len(unmatched),
                ", ".join(unmatched[:5]),
            )
            return

        async def listen() -> None:
            """Listen for WebSocket updates."""
            try:
                self.update_interval = None
                await self._websocket.async_listen(
                    state_keys,
                    self._handle_state_update,
                    WS_RECONNECT_INTERVAL.total_seconds(),
                )
            finally:
                self.update_interval = SCAN_INTERVAL
                self.hass.async_create_task(self.async_request_refresh())

        @callback
        def stop_websocket(_: Event) -> None:
            """Stop WebSocket on shutdown."""
            if self._ws_task is not None:
                self._ws_task.cancel()

        if self._stop_listeners is not None:
            self._stop_listeners()
        self._stop_listeners = self.hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STOP, stop_websocket
        )
        self._ws_task = self.config_entry.async_create_background_task(
            self.hass, listen(), "savanthost-feedback-ws"
        )

    async def async_turn_on_load(self, load_id: str, brightness: int | None) -> None:
        """Turn on a load, optionally setting brightness."""
        if brightness is not None:
            load_level = round(brightness * 100 / 255)
            await self._api.async_set_load_level(load_id, load_level)
            return
        await self._api.async_turn_on_load(load_id)

    async def async_turn_off_load(self, load_id: str) -> None:
        """Turn off a load."""
        await self._api.async_turn_off_load(load_id)

    @callback
    def _async_register_hub_device(self, configuration_id: str, name: str) -> None:
        """Register the Savant host hub device."""
        device_registry = dr.async_get(self.hass)
        device_registry.async_get_or_create(
            config_entry_id=self.config_entry.entry_id,
            identifiers={(DOMAIN, configuration_id)},
            manufacturer="Savant",
            name=name,
            model="Host",
        )
