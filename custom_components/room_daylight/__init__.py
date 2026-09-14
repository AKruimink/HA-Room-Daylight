"""Room Daylight integration lifecycle."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_SUN_ENTITY, DEFAULT_SUN_ENTITY

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate older Room Daylight config entries."""
    if entry.version == 1:
        data = dict(entry.data)
        data.setdefault(CONF_SUN_ENTITY, DEFAULT_SUN_ENTITY)
        hass.config_entries.async_update_entry(entry, data=data, version=2)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Room Daylight from a config entry."""
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Room Daylight config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
