"""Test Savant Host config flow."""

from unittest.mock import patch

from homeassistant.components.savanthost.api import SavantConnectionError
from homeassistant.components.savanthost.const import DOMAIN
from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from tests.common import MockConfigEntry


@patch("homeassistant.components.savanthost.async_setup_entry", return_value=True)
async def test_user_flow_success(
    mock_setup_entry,
    hass: HomeAssistant,
    mock_savant_api,
) -> None:
    """Test successful user flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_HOST: "192.168.1.10", CONF_PORT: 3060},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Lloyds Prototype"
    assert result["data"] == {CONF_HOST: "192.168.1.10", CONF_PORT: 3060}
    assert result["result"].unique_id == "01C969E8-DE52-49D9-A63B-553B8A19503B"


async def test_user_flow_cannot_connect(
    hass: HomeAssistant,
    mock_savant_api,
) -> None:
    """Test user flow connection error."""
    mock_savant_api.async_get_active_configuration.side_effect = SavantConnectionError(
        "timeout"
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
        data={CONF_HOST: "192.168.1.10", CONF_PORT: 3060},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_HOST: "192.168.1.10", CONF_PORT: 3060},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_already_configured(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_savant_api,
) -> None:
    """Test abort when host is already configured."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_HOST: "192.168.1.10", CONF_PORT: 3060},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_flow(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_savant_api,
    mock_websocket,
) -> None:
    """Test reconfiguration updates host and port."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": SOURCE_RECONFIGURE,
            "entry_id": mock_config_entry.entry_id,
        },
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_HOST: "192.168.1.20", CONF_PORT: 3060},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data[CONF_HOST] == "192.168.1.20"
