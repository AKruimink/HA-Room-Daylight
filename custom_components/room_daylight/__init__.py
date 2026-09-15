"""Room Daylight integration setup."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import RoomDaylightCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]

type RoomDaylightConfigEntry = ConfigEntry[RoomDaylightCoordinator]


async def _async_update_listener(
    hass: HomeAssistant,
    entry: RoomDaylightConfigEntry,
) -> None:
    """Reload after parent or subentry configuration changes."""

    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(
    hass: HomeAssistant, entry: RoomDaylightConfigEntry
) -> bool:
    """Set up Room Daylight from a config entry."""

    coordinator = RoomDaylightCoordinator(hass, entry)
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await coordinator.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: RoomDaylightConfigEntry
) -> bool:
    """Unload Room Daylight cleanly."""

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
