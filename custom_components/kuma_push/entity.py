"""Base entity for Uptime Kuma Push."""

from __future__ import annotations

from yarl import URL

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_PUSH_URL, DOMAIN
from .coordinator import KumaPushCoordinator


class KumaPushEntity(CoordinatorEntity[KumaPushCoordinator]):
    """Entity bound to a push monitor."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: KumaPushCoordinator, description: EntityDescription
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entity_description = description
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Uptime Kuma",
            model="Push monitor",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=str(URL(entry.data[CONF_PUSH_URL]).origin()),
        )
