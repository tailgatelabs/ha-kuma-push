"""Timestamp sensors for Uptime Kuma Push."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import KumaPushConfigEntry, PushState
from .entity import KumaPushEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class KumaPushSensorEntityDescription(SensorEntityDescription):
    """Describes a push sensor."""

    value_fn: Callable[[PushState], datetime | None]


SENSORS: tuple[KumaPushSensorEntityDescription, ...] = (
    KumaPushSensorEntityDescription(
        key="next_push",
        translation_key="next_push",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda state: state.next_push,
    ),
    KumaPushSensorEntityDescription(
        key="last_success",
        translation_key="last_success",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda state: state.last_success,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KumaPushConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors."""
    async_add_entities(
        KumaPushSensor(entry.runtime_data, description) for description in SENSORS
    )


class KumaPushSensor(KumaPushEntity, SensorEntity):
    """Timestamp sensor; the frontend renders it as a live relative time."""

    entity_description: KumaPushSensorEntityDescription

    @property
    def native_value(self) -> datetime | None:
        """Return the timestamp."""
        return self.entity_description.value_fn(self.coordinator.data)
