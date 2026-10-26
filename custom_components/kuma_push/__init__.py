"""The Uptime Kuma Push integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback

from .coordinator import KumaPushConfigEntry, KumaPushCoordinator

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: KumaPushConfigEntry) -> bool:
    """Set up Uptime Kuma Push from a config entry."""
    coordinator = KumaPushCoordinator(hass, entry)

    # The coordinator only schedules refreshes while it has listeners. Keep one
    # registered so pushes continue even if every entity is disabled.
    entry.async_on_unload(coordinator.async_add_listener(callback(lambda: None)))

    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: KumaPushConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
