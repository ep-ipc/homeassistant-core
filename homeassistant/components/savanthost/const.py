"""Constants for the Savant Host integration."""

from datetime import timedelta
import logging

from homeassistant.const import Platform

DOMAIN = "savanthost"

DEFAULT_PORT = 3060

PLATFORMS = [Platform.LIGHT]

SCAN_INTERVAL = timedelta(seconds=60)
WS_RECONNECT_INTERVAL = timedelta(minutes=5)

LOGGER = logging.getLogger(__package__)
