"""WebSocket client for Savant feedback state updates."""

import asyncio
from collections.abc import Awaitable, Callable
import json
import logging
from typing import Any

from aiohttp import ClientSession, ClientWebSocketResponse, WSMsgType
import yarl

WS_URI_REGISTER = "feedback/state/register"
WS_URI_UPDATE = "feedback/state/update"

_LOGGER = logging.getLogger(__name__)


def parse_ws_update(message: dict[str, Any]) -> dict[str, str]:
    """Parse a feedback/state/update WebSocket message."""
    if message.get("uri") != WS_URI_UPDATE:
        return {}
    updates: dict[str, str] = {}
    for item in message.get("messages", []):
        if isinstance(item, dict):
            for key, value in item.items():
                updates[key] = str(value)
    return updates


class SavantFeedbackWebSocket:
    """Read-only Savant feedback WebSocket listener."""

    def __init__(
        self,
        host: str,
        port: int,
        session: ClientSession,
    ) -> None:
        """Initialize the WebSocket client."""
        self._host = host
        self._port = port
        self._session = session
        self._ws_url = yarl.URL.build(
            scheme="ws",
            host=host,
            port=port,
            path="/feedback/v1/register",
        )
        self._ws: ClientWebSocketResponse | None = None
        self._registered_states: list[str] = []
        _LOGGER.debug(
            "Initialized SavantFeedbackWebSocket with host: %s, port: %s, ws_url: %s",
            host,
            port,
            self._ws_url,
        )

    async def async_listen(
        self,
        state_keys: list[str],
        on_update: Callable[[dict[str, str]], Awaitable[None] | None],
        reconnect_interval: float,
    ) -> None:
        """Connect, register states, and process updates until cancelled."""
        self._registered_states = state_keys
        _LOGGER.debug("Listening for states: %s", self._registered_states)
        while True:
            try:
                await self._async_connect_and_listen(on_update)
            except asyncio.CancelledError:
                await self.async_disconnect()
                raise
            except Exception:
                _LOGGER.exception("Savant feedback WebSocket error")
            finally:
                await self.async_disconnect()

            _LOGGER.debug(
                "Savant feedback WebSocket reconnecting in %s seconds",
                reconnect_interval,
            )
            await asyncio.sleep(reconnect_interval)

    async def _async_connect_and_listen(
        self,
        on_update: Callable[[dict[str, str]], Awaitable[None] | None],
    ) -> None:
        """Connect and process messages until the connection closes."""
        _LOGGER.debug("Connecting to WebSocket _async_connect_and_listen")
        async with self._session.ws_connect(self._ws_url, heartbeat=30) as ws:
            self._ws = ws
            _LOGGER.debug("Connected to WebSocket")
            if self._registered_states:
                _LOGGER.debug("Registering states: %s", self._registered_states)
                await ws.send_json(
                    {
                        "URI": WS_URI_REGISTER,
                        "messages": [{"states": self._registered_states}],
                    }
                )

            async for msg in ws:
                if msg.type in (WSMsgType.CLOSED, WSMsgType.CLOSING):
                    break
                if msg.type == WSMsgType.ERROR:
                    _LOGGER.warning(
                        "Savant feedback WebSocket error: %s", ws.exception()
                    )
                    break
                if msg.type != WSMsgType.TEXT:
                    continue
                try:
                    payload = json.loads(msg.data)
                    _LOGGER.debug("Received message: %s", payload)
                except json.JSONDecodeError, TypeError:
                    _LOGGER.debug("Ignoring non-JSON WebSocket message")
                    continue
                if updates := parse_ws_update(payload):
                    _LOGGER.debug("Updates: %s", updates)
                    result = on_update(updates)
                    if asyncio.iscoroutine(result):
                        await result

    async def async_disconnect(self) -> None:
        """Disconnect the WebSocket."""
        if self._ws is not None and not self._ws.closed:
            _LOGGER.debug("Disconnecting WebSocket")
            await self._ws.close()
        self._ws = None
