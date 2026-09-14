"""Room Daylight integration lifecycle."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import (
    CONF_CALIBRATION,
    CONF_DAYLIGHT_GAIN,
    CONF_DIFFUSE_BASE,
    CONF_SENSOR_BLEND,
    CONF_SENSOR_MAX_RATIO,
    CONF_SENSOR_MIN_RATIO,
    CONF_SUN_ENTITY,
    CONF_TRANSMISSION,
    CONF_WINDOWS,
    DEFAULT_CALIBRATION,
    DEFAULT_DAYLIGHT_GAIN,
    DEFAULT_DIFFUSE_BASE,
    DEFAULT_SENSOR_BLEND,
    DEFAULT_SENSOR_MAX_RATIO,
    DEFAULT_SENSOR_MIN_RATIO,
    DEFAULT_SUN_ENTITY,
    DEFAULT_WINDOW_TRANSMISSION,
)

PLATFORMS: list[Platform] = [Platform.SENSOR]


def _add_model_defaults(data: dict) -> bool:
    """Add explicitly stored model defaults to legacy entry data."""
    changed = False
    defaults = {
        CONF_CALIBRATION: DEFAULT_CALIBRATION,
        CONF_DAYLIGHT_GAIN: DEFAULT_DAYLIGHT_GAIN,
        CONF_DIFFUSE_BASE: DEFAULT_DIFFUSE_BASE,
        CONF_SENSOR_BLEND: DEFAULT_SENSOR_BLEND,
        CONF_SENSOR_MIN_RATIO: DEFAULT_SENSOR_MIN_RATIO,
        CONF_SENSOR_MAX_RATIO: DEFAULT_SENSOR_MAX_RATIO,
    }
    for key, value in defaults.items():
        if key not in data:
            data[key] = value
            changed = True

    windows = []
    for configured_window in data.get(CONF_WINDOWS, []):
        window = dict(configured_window)
        if CONF_TRANSMISSION not in window:
            window[CONF_TRANSMISSION] = DEFAULT_WINDOW_TRANSMISSION
            changed = True
        windows.append(window)
    if windows:
        data[CONF_WINDOWS] = windows

    return changed


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate older Room Daylight config entries."""
    data = dict(entry.data)
    version = entry.version
    changed = False

    if version == 1:
        if CONF_SUN_ENTITY not in data:
            data[CONF_SUN_ENTITY] = DEFAULT_SUN_ENTITY
            changed = True
        version = 2

    if version == 2:
        changed = _add_model_defaults(data) or changed
        version = 3

    if changed or version != entry.version:
        hass.config_entries.async_update_entry(entry, data=data, version=version)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Room Daylight from a config entry."""
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Room Daylight config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
