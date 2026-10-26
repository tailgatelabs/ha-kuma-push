"""Binary sensor reporting push failures."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import KumaPushConfigEntry
from .entity import KumaPushEntity

PARALLEL_UPDATES = 0

STATUS = BinarySensorEntityDescription(
    key="status",
    translation_key="status",
    device_class=BinarySensorDeviceClass.PROBLEM,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KumaPushConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensor."""
    async_add_entities([KumaPushStatusSensor(entry.runtime_data, STATUS)])


class KumaPushStatusSensor(KumaPushEntity, BinarySensorEntity):
    """On when the most recent push failed."""

    @property
    def is_on(self) -> bool:
        """Return true if the last push failed."""
        return not self.coordinator.data.success

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the last error."""
        return {"last_error": self.coordinator.data.error}
