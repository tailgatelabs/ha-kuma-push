"""Constants for the Uptime Kuma Push integration."""

from __future__ import annotations

import logging
from typing import Final

DOMAIN: Final = "kuma_push"
LOGGER = logging.getLogger(__package__)

CONF_PUSH_URL: Final = "push_url"
CONF_INTERVAL: Final = "interval"
CONF_ACCESS_CLIENT_ID: Final = "access_client_id"
CONF_ACCESS_CLIENT_SECRET: Final = "access_client_secret"

DEFAULT_INTERVAL: Final = 60
# Uptime Kuma's minimum heartbeat interval is 20 seconds.
MIN_INTERVAL: Final = 20
MAX_INTERVAL: Final = 86400

PUSH_PATH: Final = "/api/push/"
REQUEST_TIMEOUT: Final = 10
