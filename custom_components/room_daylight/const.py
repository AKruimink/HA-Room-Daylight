"""Constants for the Room Daylight integration."""

DOMAIN = "room_daylight"

CONF_OUTSIDE_ILLUMINANCE = "outside_illuminance"
CONF_SUN_ENTITY = "sun_entity"
CONF_FLOOR_AREA = "floor_area"
CONF_WINDOW_COUNT = "window_count"
CONF_WINDOWS = "windows"
CONF_WIDTH = "width"
CONF_HEIGHT = "height"
CONF_AZIMUTH = "azimuth"
CONF_COVER_ENTITY = "cover_entity"
CONF_INDOOR_ILLUMINANCE = "indoor_illuminance"
CONF_ARTIFICIAL_LIGHTS = "artificial_lights"

DEFAULT_SUN_ENTITY = "sun.sun"

DEFAULT_WINDOW_TRANSMISSION = 0.65
DEFAULT_DAYLIGHT_GAIN = 0.15
DEFAULT_DIFFUSE_BASE = 0.35
DEFAULT_SENSOR_BLEND = 0.25
DEFAULT_SENSOR_MIN_RATIO = 0.50
DEFAULT_SENSOR_MAX_RATIO = 2.00
