"""Sensor platform for Room Daylight."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, PERCENTAGE, UnitOfIlluminance
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import RoomDaylightConfigEntry
from .const import DOMAIN, SUBENTRY_TYPE_ROOM
from .coordinator import RoomDaylightCoordinator
from .models import RoomSnapshot


# The coordinator serialises all inbound updates for this read-only platform.
PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class RoomDaylightSensorDescription(SensorEntityDescription):
    """Describe a Room Daylight sensor."""

    value_key: str


LUX_DESCRIPTIONS: tuple[RoomDaylightSensorDescription, ...] = (
    RoomDaylightSensorDescription(
        key="estimated_daylight",
        value_key="estimated_lux",
        translation_key="estimated_daylight",
        device_class=SensorDeviceClass.ILLUMINANCE,
        native_unit_of_measurement=UnitOfIlluminance.LUX,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    RoomDaylightSensorDescription(
        key="native_daylight",
        value_key="native_lux",
        translation_key="native_daylight",
        device_class=SensorDeviceClass.ILLUMINANCE,
        native_unit_of_measurement=UnitOfIlluminance.LUX,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    RoomDaylightSensorDescription(
        key="transferred_daylight",
        value_key="transferred_lux",
        translation_key="transferred_daylight",
        device_class=SensorDeviceClass.ILLUMINANCE,
        native_unit_of_measurement=UnitOfIlluminance.LUX,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    RoomDaylightSensorDescription(
        key="indoor_sensor_median",
        value_key="sensor_median_lux",
        translation_key="indoor_sensor_median",
        device_class=SensorDeviceClass.ILLUMINANCE,
        native_unit_of_measurement=UnitOfIlluminance.LUX,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    RoomDaylightSensorDescription(
        key="indoor_sensor_adjustment",
        value_key="sensor_adjustment_lux",
        translation_key="indoor_sensor_adjustment",
        native_unit_of_measurement=UnitOfIlluminance.LUX,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
)

RATIO_DESCRIPTION = RoomDaylightSensorDescription(
    key="effective_daylight_ratio",
    value_key="effective_daylight_ratio",
    translation_key="effective_daylight_ratio",
    native_unit_of_measurement=PERCENTAGE,
    state_class=SensorStateClass.MEASUREMENT,
    entity_category=EntityCategory.DIAGNOSTIC,
    entity_registry_enabled_default=False,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RoomDaylightConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Room Daylight sensors for all room subentries."""

    coordinator = entry.runtime_data
    area_registry = ar.async_get(hass)

    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_TYPE_ROOM:
            continue
        room = coordinator.rooms.get(subentry.subentry_id)
        if room is None:
            continue

        area = area_registry.async_get_area(room.area_id) if room.area_id else None
        suggested_area = area.name if area is not None else None
        entities: list[SensorEntity] = [
            RoomDaylightSensor(
                coordinator,
                room.room_id,
                description,
                suggested_area=suggested_area,
            )
            for description in (*LUX_DESCRIPTIONS, RATIO_DESCRIPTION)
        ]
        async_add_entities(entities, config_subentry_id=subentry.subentry_id)


class RoomDaylightSensor(CoordinatorEntity[RoomDaylightCoordinator], SensorEntity):
    """One sensor exposing a value from the room coordinator snapshot."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: RoomDaylightCoordinator,
        room_id: str,
        description: RoomDaylightSensorDescription,
        *,
        suggested_area: str | None,
    ) -> None:
        """Initialise the room sensor."""

        super().__init__(coordinator)
        self.entity_description = description
        self._room_id = room_id
        room = coordinator.rooms[room_id]
        self._attr_unique_id = f"{room_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, room_id)},
            manufacturer="Room Daylight",
            model="Whole-house daylight model",
            name=room.name,
            suggested_area=suggested_area,
        )

    @property
    def _snapshot(self) -> RoomSnapshot | None:
        """Return the latest room snapshot."""

        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._room_id)

    @property
    def native_value(self) -> float | None:
        """Return this sensor's current native value."""

        snapshot = self._snapshot
        if snapshot is None:
            return None

        value = getattr(snapshot, self.entity_description.value_key)
        if value is None:
            return None
        if self.entity_description.key == "effective_daylight_ratio":
            return round(float(value) * 100.0, 2)
        return round(float(value), 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose explainability diagnostics on the primary room sensor."""

        if self.entity_description.key != "estimated_daylight":
            return None
        snapshot = self._snapshot
        if snapshot is None:
            return None

        room_names = {
            room_id: room.name for room_id, room in self.coordinator.rooms.items()
        }
        return {
            "native_daylight_lux": round(snapshot.native_lux, 2),
            "modelled_daylight_lux": round(snapshot.modelled_lux, 2),
            "transferred_daylight_lux": round(snapshot.transferred_lux, 2),
            "indoor_sensor_median_lux": (
                round(snapshot.sensor_median_lux, 2)
                if snapshot.sensor_median_lux is not None
                else None
            ),
            "indoor_sensor_adjustment_lux": round(
                snapshot.sensor_adjustment_lux, 2
            ),
            "indoor_sensor_correction_applied": snapshot.sensor_correction_applied,
            "effective_daylight_ratio": round(
                snapshot.effective_daylight_ratio, 4
            ),
            "network_iterations": snapshot.network_iterations,
            "network_converged": snapshot.network_converged,
            "openings": [
                {
                    "name": item.name,
                    "opening_area_m2": round(item.area_m2, 3),
                    "incidence_factor": round(item.incidence_factor, 4),
                    "sky_view_factor": round(item.sky_view_factor, 4),
                    "orientation_factor": round(item.orientation_factor, 4),
                    "cover_openness": round(item.cover_openness, 4),
                    "effective_transmission": round(
                        item.effective_transmission, 4
                    ),
                    "contribution_lux": round(item.contribution_lux, 2),
                }
                for item in snapshot.opening_diagnostics
            ],
            "connections": [
                {
                    "name": item.name,
                    "other_room": room_names.get(
                        item.other_room_id, item.other_room_id
                    ),
                    "opening_area_m2": round(item.opening_area_m2, 3),
                    "state_entity": item.state_entity,
                    "state": item.state_description,
                    "transmission": round(item.transmission, 4),
                    "transfer_efficiency": round(item.transfer_efficiency, 4),
                    "transfer_weight": round(item.transfer_weight, 6),
                    "contribution_lux": round(item.contribution_lux, 2),
                }
                for item in snapshot.connection_diagnostics
            ],
            **snapshot.extra,
        }
