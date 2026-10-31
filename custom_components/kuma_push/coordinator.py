"""Push scheduler for Uptime Kuma Push."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .api import KumaPushAuthError, KumaPushError, access_headers, async_push
from .const import (
    CONF_ACCESS_CLIENT_ID,
    CONF_ACCESS_CLIENT_SECRET,
    CONF_INTERVAL,
    CONF_PUSH_URL,
    DOMAIN,
    LOGGER,
)

type KumaPushConfigEntry = ConfigEntry[KumaPushCoordinator]


@dataclass(frozen=True, slots=True)
class PushState:
    """Outcome of the most recent push."""

    success: bool
    error: str | None
    last_success: datetime | None
    next_push: datetime


class KumaPushCoordinator(DataUpdateCoordinator[PushState]):
    """Push a heartbeat to Uptime Kuma on a fixed interval.

    A failed push is reported through ``PushState`` rather than ``UpdateFailed``
    so entities stay available and show the failure instead of going
    unavailable. An authentication failure raises ``ConfigEntryAuthFailed``
    instead so Home Assistant asks for new credentials.
    """

    config_entry: KumaPushConfigEntry

    def __init__(self, hass: HomeAssistant, entry: KumaPushConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=entry.options[CONF_INTERVAL]),
        )
        self._session = async_get_clientsession(hass)
        self._url: str = entry.data[CONF_PUSH_URL]
        self._headers = access_headers(
            entry.data.get(CONF_ACCESS_CLIENT_ID),
            entry.data.get(CONF_ACCESS_CLIENT_SECRET),
        )
        self._latency_ms: int | None = None

    async def _async_update_data(self) -> PushState:
        """Send one heartbeat."""
        previous = self.data
        try:
            self._latency_ms = await async_push(
                self._session, self._url, self._latency_ms, self._headers
            )
        except KumaPushAuthError as err:
            self._latency_ms = None
            raise ConfigEntryAuthFailed(str(err)) from err
        except KumaPushError as err:
            if previous is None or previous.success:
                LOGGER.warning("Push to Uptime Kuma failed: %s", err)
            self._latency_ms = None
            success, error = False, str(err)
            last_success = previous.last_success if previous else None
        else:
            if previous is not None and not previous.success:
                LOGGER.info("Push to Uptime Kuma recovered")
            success, error = True, None
            last_success = dt_util.utcnow()

        assert self.update_interval is not None
        # The next run is scheduled relative to the end of this one.
        return PushState(
            success=success,
            error=error,
            last_success=last_success,
            next_push=dt_util.utcnow() + self.update_interval,
        )
