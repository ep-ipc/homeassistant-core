"""HTTP API client for Savant Host."""

from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout
import yarl

from .const import DEFAULT_PORT

REQUEST_TIMEOUT = ClientTimeout(total=15)


class SavantApiError(Exception):
    """Base Savant API error."""


class SavantConnectionError(SavantApiError):
    """Error connecting to Savant host."""


class SavantApi:
    """Thin HTTP client for the Savant Open API."""

    def __init__(
        self,
        host: str,
        session: ClientSession,
        port: int = DEFAULT_PORT,
    ) -> None:
        """Initialize the API client."""
        self._session = session
        self._base_url = yarl.URL.build(scheme="http", host=host, port=port)

    @property
    def base_url(self) -> yarl.URL:
        """Return the base URL."""
        return self._base_url

    async def async_get_active_configuration(self) -> dict[str, Any]:
        """Get the active configuration."""
        return await self._async_get_json("/config/v1/configuration/active")

    async def async_get_lighting_config(self) -> dict[str, Any]:
        """Get the lighting configuration."""
        return await self._async_get_json("/config/v1/lighting")

    async def async_get_loads(self) -> list[dict[str, Any]]:
        """Get all lighting loads."""
        result = await self._async_get_json("/config/v1/lighting/loads")
        if not isinstance(result, list):
            msg = "Unexpected loads response"
            raise SavantApiError(msg)
        return result

    async def async_get_feedback_states(self, room_id: str) -> dict[str, Any]:
        """Get feedback state keys for a room."""
        return await self._async_get_json(
            "/feedback/v1/states", params={"RoomID": room_id}
        )

    async def async_turn_on_load(self, load_id: str) -> None:
        """Turn on a lighting load."""
        await self._async_post_json(
            f"/control/v1/lighting/loads/{load_id}/command",
            {"command": "SwitchOn", "arguments": {}},
        )

    async def async_turn_off_load(self, load_id: str) -> None:
        """Turn off a lighting load."""
        await self._async_post_json(
            f"/control/v1/lighting/loads/{load_id}/command",
            {"command": "SwitchOff", "arguments": {}},
        )

    async def async_set_load_level(self, load_id: str, load_level: int) -> None:
        """Set a lighting load level (0-100)."""
        await self._async_post_json(
            f"/control/v1/lighting/loads/{load_id}/level",
            {"loadLevel": load_level},
        )

    async def _async_get_json(
        self, path: str, params: dict[str, str] | None = None
    ) -> Any:
        """Perform a GET request and return JSON."""
        url = self._base_url.with_path(path)
        try:
            async with self._session.get(
                url, params=params, timeout=REQUEST_TIMEOUT
            ) as response:
                response.raise_for_status()
                return await response.json()
        except (ClientError, TimeoutError) as err:
            raise SavantConnectionError(str(err)) from err

    async def _async_post_json(self, path: str, body: dict[str, Any]) -> None:
        """Perform a POST request."""
        url = self._base_url.with_path(path)
        try:
            async with self._session.post(
                url, json=body, timeout=REQUEST_TIMEOUT
            ) as response:
                response.raise_for_status()
        except (ClientError, TimeoutError) as err:
            raise SavantConnectionError(str(err)) from err
