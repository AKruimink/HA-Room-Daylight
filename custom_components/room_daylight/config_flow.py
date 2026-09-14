"""Configuration flows for Room Daylight."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
)
from homeassistant.util import slugify

from .const import (
    CONF_ARTIFICIAL_LIGHTS,
    CONF_AZIMUTH,
    CONF_CALIBRATION,
    CONF_COVER_ENTITY,
    CONF_DAYLIGHT_GAIN,
    CONF_DIFFUSE_BASE,
    CONF_FLOOR_AREA,
    CONF_HEIGHT,
    CONF_INDOOR_ILLUMINANCE,
    CONF_OUTSIDE_ILLUMINANCE,
    CONF_SENSOR_BLEND,
    CONF_SENSOR_MAX_RATIO,
    CONF_SENSOR_MIN_RATIO,
    CONF_SHOW_ADVANCED,
    CONF_SUN_ENTITY,
    CONF_TRANSMISSION,
    CONF_WIDTH,
    CONF_WINDOW_COUNT,
    CONF_WINDOWS,
    DEFAULT_CALIBRATION,
    DEFAULT_DAYLIGHT_GAIN,
    DEFAULT_DIFFUSE_BASE,
    DEFAULT_SENSOR_BLEND,
    DEFAULT_SENSOR_MAX_RATIO,
    DEFAULT_SENSOR_MIN_RATIO,
    DEFAULT_WINDOW_TRANSMISSION,
    DOMAIN,
)

MAX_WINDOWS = 20


def _number_selector(
    *,
    step: float,
    minimum: float | None = None,
    maximum: float | None = None,
    unit: str | None = None,
) -> NumberSelector:
    """Create a numeric box with matching frontend range validation."""
    return NumberSelector(
        NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=step,
            mode=NumberSelectorMode.BOX,
            unit_of_measurement=unit,
        )
    )


def _illuminance_selector(*, multiple: bool = False) -> EntitySelector:
    """Create an entity selector limited to illuminance sensors."""
    return EntitySelector(
        EntitySelectorConfig(
            multiple=multiple,
            filter={
                "domain": "sensor",
                "device_class": SensorDeviceClass.ILLUMINANCE.value,
            },
        )
    )


def _sun_selector() -> EntitySelector:
    """Create an entity selector limited to Sun entities."""
    return EntitySelector(EntitySelectorConfig(filter={"domain": "sun"}))


def _lights_selector() -> EntitySelector:
    """Create a multiple-entity selector limited to lights."""
    return EntitySelector(
        EntitySelectorConfig(multiple=True, filter={"domain": "light"})
    )


def _covering_selector() -> EntitySelector:
    """Create a selector for supported window-covering state entities."""
    return EntitySelector(
        EntitySelectorConfig(
            filter={"domain": ["cover", "binary_sensor", "input_boolean"]}
        )
    )


def _window_count_selector() -> NumberSelector:
    """Create the selector used for the number of exterior openings."""
    return _number_selector(step=1, minimum=1, maximum=MAX_WINDOWS)


def _room_schema(*, include_name: bool) -> vol.Schema:
    """Build the common room form schema."""
    fields: dict[Any, Any] = {}
    if include_name:
        fields[vol.Required(CONF_NAME)] = TextSelector()

    fields.update(
        {
            vol.Required(CONF_OUTSIDE_ILLUMINANCE): _illuminance_selector(),
            vol.Required(CONF_SUN_ENTITY): _sun_selector(),
            vol.Required(CONF_FLOOR_AREA): _number_selector(
                step=0.1,
                minimum=0.1,
                unit="m²",
            ),
            vol.Required(CONF_WINDOW_COUNT, default=1): _window_count_selector(),
            vol.Optional(CONF_SHOW_ADVANCED, default=False): BooleanSelector(),
        }
    )

    if include_name:
        fields[vol.Optional(CONF_INDOOR_ILLUMINANCE, default=[])] = (
            _illuminance_selector(multiple=True)
        )
        fields[vol.Optional(CONF_ARTIFICIAL_LIGHTS, default=[])] = _lights_selector()

    return vol.Schema(fields)


def _window_schema(*, advanced: bool) -> vol.Schema:
    """Build the form schema for one exterior opening."""
    fields: dict[Any, Any] = {
        vol.Required(CONF_WIDTH): _number_selector(
            step=0.01,
            minimum=0.01,
            unit="m",
        ),
        vol.Required(CONF_HEIGHT): _number_selector(
            step=0.01,
            minimum=0.01,
            unit="m",
        ),
        vol.Required(CONF_AZIMUTH): _number_selector(
            step=1,
            minimum=0,
            maximum=359,
            unit="°",
        ),
        vol.Optional(CONF_COVER_ENTITY): _covering_selector(),
    }
    if advanced:
        fields[
            vol.Required(
                CONF_TRANSMISSION,
                default=DEFAULT_WINDOW_TRANSMISSION,
            )
        ] = _number_selector(step=0.01, minimum=0, maximum=1)
    return vol.Schema(fields)


def _advanced_schema() -> vol.Schema:
    """Build the advanced model-settings form schema."""
    return vol.Schema(
        {
            vol.Required(
                CONF_CALIBRATION,
                default=DEFAULT_CALIBRATION,
            ): _number_selector(step=0.01, minimum=0.01, maximum=10),
            vol.Required(
                CONF_DAYLIGHT_GAIN,
                default=DEFAULT_DAYLIGHT_GAIN,
            ): _number_selector(step=0.001, minimum=0.001, maximum=2),
            vol.Required(
                CONF_DIFFUSE_BASE,
                default=DEFAULT_DIFFUSE_BASE,
            ): _number_selector(step=0.01, minimum=0, maximum=1),
            vol.Required(
                CONF_SENSOR_BLEND,
                default=DEFAULT_SENSOR_BLEND,
            ): _number_selector(step=0.01, minimum=0, maximum=1),
            vol.Required(
                CONF_SENSOR_MIN_RATIO,
                default=DEFAULT_SENSOR_MIN_RATIO,
            ): _number_selector(step=0.05, minimum=0, maximum=10),
            vol.Required(
                CONF_SENSOR_MAX_RATIO,
                default=DEFAULT_SENSOR_MAX_RATIO,
            ): _number_selector(step=0.05, minimum=0, maximum=10),
        }
    )


def _model_defaults() -> dict[str, float]:
    """Return explicit defaults stored with every room configuration."""
    return {
        CONF_CALIBRATION: DEFAULT_CALIBRATION,
        CONF_DAYLIGHT_GAIN: DEFAULT_DAYLIGHT_GAIN,
        CONF_DIFFUSE_BASE: DEFAULT_DIFFUSE_BASE,
        CONF_SENSOR_BLEND: DEFAULT_SENSOR_BLEND,
        CONF_SENSOR_MIN_RATIO: DEFAULT_SENSOR_MIN_RATIO,
        CONF_SENSOR_MAX_RATIO: DEFAULT_SENSOR_MAX_RATIO,
    }


def _validate_room_input(
    user_input: dict[str, Any],
    *,
    require_name: bool,
) -> dict[str, str]:
    """Validate values shared by setup and reconfigure flows."""
    errors: dict[str, str] = {}

    if require_name and not str(user_input.get(CONF_NAME, "")).strip():
        errors[CONF_NAME] = "required"

    if not user_input.get(CONF_OUTSIDE_ILLUMINANCE):
        errors[CONF_OUTSIDE_ILLUMINANCE] = "required"
    if not user_input.get(CONF_SUN_ENTITY):
        errors[CONF_SUN_ENTITY] = "required"

    try:
        floor_area = float(user_input[CONF_FLOOR_AREA])
    except (KeyError, TypeError, ValueError):
        errors[CONF_FLOOR_AREA] = "required"
    else:
        if floor_area <= 0:
            errors[CONF_FLOOR_AREA] = "positive_number"

    try:
        window_count = int(user_input[CONF_WINDOW_COUNT])
    except (KeyError, TypeError, ValueError):
        errors[CONF_WINDOW_COUNT] = "required"
    else:
        if not 1 <= window_count <= MAX_WINDOWS:
            errors[CONF_WINDOW_COUNT] = "window_count_range"

    return errors


def _validate_window_input(
    user_input: dict[str, Any],
    *,
    advanced: bool,
) -> dict[str, str]:
    """Validate one exterior opening."""
    errors: dict[str, str] = {}

    for key in (CONF_WIDTH, CONF_HEIGHT):
        try:
            value = float(user_input[key])
        except (KeyError, TypeError, ValueError):
            errors[key] = "required"
        else:
            if value <= 0:
                errors[key] = "positive_number"

    try:
        azimuth = float(user_input[CONF_AZIMUTH])
    except (KeyError, TypeError, ValueError):
        errors[CONF_AZIMUTH] = "required"
    else:
        if not 0 <= azimuth < 360:
            errors[CONF_AZIMUTH] = "azimuth_range"

    if advanced:
        try:
            transmission = float(user_input[CONF_TRANSMISSION])
        except (KeyError, TypeError, ValueError):
            errors[CONF_TRANSMISSION] = "required"
        else:
            if not 0 <= transmission <= 1:
                errors[CONF_TRANSMISSION] = "zero_to_one"

    return errors


def _validate_advanced_input(user_input: dict[str, Any]) -> dict[str, str]:
    """Validate advanced room-model parameters."""
    errors: dict[str, str] = {}

    ranges = {
        CONF_CALIBRATION: (0.01, 10.0),
        CONF_DAYLIGHT_GAIN: (0.001, 2.0),
        CONF_DIFFUSE_BASE: (0.0, 1.0),
        CONF_SENSOR_BLEND: (0.0, 1.0),
        CONF_SENSOR_MIN_RATIO: (0.0, 10.0),
        CONF_SENSOR_MAX_RATIO: (0.0, 10.0),
    }
    for key, (minimum, maximum) in ranges.items():
        try:
            value = float(user_input[key])
        except (KeyError, TypeError, ValueError):
            errors[key] = "required"
        else:
            if not minimum <= value <= maximum:
                errors[key] = "advanced_range"

    if CONF_SENSOR_MIN_RATIO not in errors and CONF_SENSOR_MAX_RATIO not in errors:
        if float(user_input[CONF_SENSOR_MAX_RATIO]) < float(
            user_input[CONF_SENSOR_MIN_RATIO]
        ):
            errors[CONF_SENSOR_MAX_RATIO] = "sensor_ratio_order"

    return errors


def _window_from_input(
    user_input: dict[str, Any],
    *,
    advanced: bool,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalise one valid window form submission for storage."""
    window: dict[str, Any] = {
        CONF_WIDTH: float(user_input[CONF_WIDTH]),
        CONF_HEIGHT: float(user_input[CONF_HEIGHT]),
        CONF_AZIMUTH: float(user_input[CONF_AZIMUTH]),
    }
    if cover_entity := user_input.get(CONF_COVER_ENTITY):
        window[CONF_COVER_ENTITY] = cover_entity

    if advanced:
        window[CONF_TRANSMISSION] = float(user_input[CONF_TRANSMISSION])
    else:
        window[CONF_TRANSMISSION] = float(
            (existing or {}).get(CONF_TRANSMISSION, DEFAULT_WINDOW_TRANSMISSION)
        )

    return window


class RoomDaylightConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle setup and reconfiguration for Room Daylight."""

    VERSION = 3

    def __init__(self) -> None:
        """Initialise temporary state used while walking multi-step forms."""
        self._room_data: dict[str, Any] = {}
        self._windows: list[dict[str, Any]] = []
        self._window_count = 1
        self._window_index = 0
        self._reconfigure = False
        self._show_advanced = False
        self._existing_windows: list[dict[str, Any]] = []

    def _start_window_steps(
        self,
        *,
        window_count: int,
        existing_windows: list[dict[str, Any]] | None = None,
    ) -> None:
        """Reset temporary state before collecting window details."""
        self._window_count = window_count
        self._window_index = 0
        self._windows = []
        self._existing_windows = existing_windows or []

    def _finish_flow(self) -> config_entries.ConfigFlowResult:
        """Create or update the room after all setup steps are complete."""
        data = {**self._room_data, CONF_WINDOWS: list(self._windows)}
        if self._reconfigure:
            return self.async_update_reload_and_abort(
                self._get_reconfigure_entry(),
                data_updates=data,
            )
        return self.async_create_entry(title=data[CONF_NAME], data=data)

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Collect initial room and source configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _validate_room_input(user_input, require_name=True)
            if not errors:
                room_data = dict(user_input)
                name = str(room_data[CONF_NAME]).strip()
                window_count = int(room_data.pop(CONF_WINDOW_COUNT))
                self._show_advanced = bool(room_data.pop(CONF_SHOW_ADVANCED, False))

                await self.async_set_unique_id(slugify(name))
                self._abort_if_unique_id_configured()

                room_data[CONF_NAME] = name
                for key, value in _model_defaults().items():
                    room_data.setdefault(key, value)

                self._room_data = room_data
                self._start_window_steps(window_count=window_count)
                return await self.async_step_window()

        schema = _room_schema(include_name=True)
        if user_input:
            schema = self.add_suggested_values_to_schema(schema, user_input)
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_window(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Collect one exterior window or glazed door."""
        errors: dict[str, str] = {}
        existing = (
            self._existing_windows[self._window_index]
            if self._window_index < len(self._existing_windows)
            else None
        )

        if user_input is not None:
            errors = _validate_window_input(
                user_input,
                advanced=self._show_advanced,
            )
            if not errors:
                self._windows.append(
                    _window_from_input(
                        user_input,
                        advanced=self._show_advanced,
                        existing=existing,
                    )
                )
                self._window_index += 1

                if self._window_index < self._window_count:
                    return await self.async_step_window()
                if self._show_advanced:
                    return await self.async_step_advanced()
                return self._finish_flow()

        schema = _window_schema(advanced=self._show_advanced)
        suggested = existing or {}
        if user_input:
            suggested = {**suggested, **user_input}
        if suggested:
            schema = self.add_suggested_values_to_schema(schema, suggested)

        return self.async_show_form(
            step_id="window",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "window_number": str(self._window_index + 1),
                "window_total": str(self._window_count),
            },
        )

    async def async_step_advanced(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Collect optional advanced model settings."""
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _validate_advanced_input(user_input)
            if not errors:
                for key in _model_defaults():
                    self._room_data[key] = float(user_input[key])
                return self._finish_flow()

        current = {
            key: self._room_data.get(key, default)
            for key, default in _model_defaults().items()
        }
        if user_input:
            current.update(user_input)

        return self.async_show_form(
            step_id="advanced",
            data_schema=self.add_suggested_values_to_schema(
                _advanced_schema(),
                current,
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Reconfigure structural room inputs, windows and model parameters."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _validate_room_input(user_input, require_name=False)
            if not errors:
                room_data = {**entry.data, **user_input}
                window_count = int(room_data.pop(CONF_WINDOW_COUNT))
                self._show_advanced = bool(room_data.pop(CONF_SHOW_ADVANCED, False))

                self._reconfigure = True
                self._room_data = room_data
                self._start_window_steps(
                    window_count=window_count,
                    existing_windows=list(entry.data.get(CONF_WINDOWS, [])),
                )
                return await self.async_step_window()

        suggested = {
            CONF_OUTSIDE_ILLUMINANCE: entry.data.get(CONF_OUTSIDE_ILLUMINANCE),
            CONF_SUN_ENTITY: entry.data.get(CONF_SUN_ENTITY),
            CONF_FLOOR_AREA: entry.data.get(CONF_FLOOR_AREA),
            CONF_WINDOW_COUNT: len(entry.data.get(CONF_WINDOWS, [])) or 1,
            CONF_SHOW_ADVANCED: False,
        }
        if user_input:
            suggested.update(user_input)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                _room_schema(include_name=False),
                suggested,
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow for optional sensor inputs."""
        return RoomDaylightOptionsFlow()


class RoomDaylightOptionsFlow(config_entries.OptionsFlowWithReload):
    """Manage optional indoor sensors and artificial-light exclusions."""

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Show and save optional room inputs."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = {
            CONF_INDOOR_ILLUMINANCE: self.config_entry.options.get(
                CONF_INDOOR_ILLUMINANCE,
                self.config_entry.data.get(CONF_INDOOR_ILLUMINANCE, []),
            ),
            CONF_ARTIFICIAL_LIGHTS: self.config_entry.options.get(
                CONF_ARTIFICIAL_LIGHTS,
                self.config_entry.data.get(CONF_ARTIFICIAL_LIGHTS, []),
            ),
        }
        schema = vol.Schema(
            {
                vol.Optional(CONF_INDOOR_ILLUMINANCE, default=[]): (
                    _illuminance_selector(multiple=True)
                ),
                vol.Optional(CONF_ARTIFICIAL_LIGHTS, default=[]): _lights_selector(),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, current),
        )
