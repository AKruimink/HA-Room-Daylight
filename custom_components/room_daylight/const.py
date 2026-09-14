"""Constants for Room Daylight."""

DOMAIN = "room_daylight"

# Config-entry keys.
CONF_OUTSIDE_ILLUMINANCE = "outside_illuminance"
CONF_SUN_ENTITY = "sun_entity"
CONF_FLOOR_AREA = "floor_area"
CONF_WINDOW_COUNT = "window_count"
CONF_WINDOWS = "windows"
CONF_WIDTH = "width"
CONF_HEIGHT = "height"
CONF_AZIMUTH = "azimuth"
CONF_COVER_ENTITY = "cover_entity"
CONF_TRANSMISSION = "transmission"
CONF_INDOOR_ILLUMINANCE = "indoor_illuminance"
CONF_ARTIFICIAL_LIGHTS = "artificial_lights"

# Flow-only key. This value is never persisted to the config entry.
CONF_SHOW_ADVANCED = "show_advanced"

# Advanced model parameters persisted per room.
CONF_CALIBRATION = "calibration"
CONF_DAYLIGHT_GAIN = "daylight_gain"
CONF_DIFFUSE_BASE = "diffuse_base"
CONF_SENSOR_BLEND = "sensor_blend"
CONF_SENSOR_MIN_RATIO = "sensor_min_ratio"
CONF_SENSOR_MAX_RATIO = "sensor_max_ratio"

DEFAULT_SUN_ENTITY = "sun.sun"
DEFAULT_WINDOW_TRANSMISSION = 0.65
DEFAULT_CALIBRATION = 1.0
DEFAULT_DAYLIGHT_GAIN = 0.15
DEFAULT_DIFFUSE_BASE = 0.35
DEFAULT_SENSOR_BLEND = 0.25
DEFAULT_SENSOR_MIN_RATIO = 0.50
DEFAULT_SENSOR_MAX_RATIO = 2.00
