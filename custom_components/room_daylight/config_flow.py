"""Configuration flows for Room Daylight."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
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
    CONF_COVER_ENTITY,
    CONF_FLOOR_AREA,
    CONF_HEIGHT,
    CONF_INDOOR_ILLUMINANCE,
    CONF_OUTSIDE_ILLUMINANCE,
    CONF_SUN_ENTITY,
    CONF_WIDTH,
    CONF_WINDOW_COUNT,
    CONF_WINDOWS,
    DOMAIN,
)

MAX_WINDOWS = 20


def _number_selector(*, step: float, unit: str | None = None) -> NumberSelector:
    """Create a number input; explicit range validation is handled by the flow."""
    return NumberSelector(
        NumberSelectorConfig(
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
    return NumberSelector(
        NumberSelectorConfig(
            min=1,
            max=MAX_WINDOWS,
            step=1,
            mode=NumberSelectorMode.BOX,
        )
    )


def _room_schema(*, include_name: bool) -> vol.Schema:
    """Build the common room form schema."""
    fields: dict[Any, Any] = {}
    if include_name:
        fields[vol.Required(CONF_NAME)] = TextSelector()

    fields.update(
        {
            vol.Required(CONF_OUTSIDE_ILLUMINANCE): _illuminance_selector(),
            vol.Required(CONF_SUN_ENTITY): _sun_selector(),
            vol.Required(CONF_FLOOR_AREA): _number_selector(step=0.1, unit="m²"),
            vol.Required(CONF_WINDOW_COUNT, default=1): _window_count_selector(),
        }
    )

    if include_name:
        fields[vol.Optional(CONF_INDOOR_ILLUMINANCE, default=[])] = (
            _illuminance_selector(multiple=True)
        )
        fields[vol.Optional(CONF_ARTIFICIAL_LIGHTS, default=[])] = _lights_selector()

    return vol.Schema(fields)


def _window_schema() -> vol.Schema:
    """Build the form schema for one exterior opening."""
    return vol.Schema(
        {
            vol.Required(CONF_WIDTH): _number_selector(step=0.01, unit="m"),
            vol.Required(CONF_HEIGHT): _number_selector(step=0.01, unit="m"),
            vol.Required(CONF_AZIMUTH): _number_selector(step=1, unit="°"),
            vol.Optional(CONF_COVER_ENTITY): _covering_selector(),
        }
    )


def _validate_room_input(user_input: dict[str, Any]) -> dict[str, str]:
    """Validate values shared by setup and reconfigure flows."""
    errors: dict[str, str] = {}

    if CONF_NAME in user_input and not str(user_input[CONF_NAME]).strip():
        errors[CONF_NAME] = "required"

    try:
        if float(user_input[CONF_FLOOR_AREA]) <= 0:
            errors[CONF_FLOOR_AREA] = "positive_number"
    except (KeyError, TypeError, ValueError):
        errors[CONF_FLOOR_AREA] = "required"

    if not user_input.get(CONF_OUTSIDE_ILLUMINANCE):
        errors[CONF_OUTSIDE_ILLUMINANCE] = "required"
    if not user_input.get(CONF_SUN_ENTITY):
        errors[CONF_SUN_ENTITY] = "required"

    return errors


def _validate_window_input(user_input: dict[str, Any]) -> dict[str, str]:
    """Validate one exterior opening."""
    errors: dict[str, str] = {}

    for key in (CONF_WIDTH, CONF_HEIGHT):
        try:
            if float(user_input[key]) <= 0:
                errors[key] = "positive_number"
        except (KeyError, TypeError, ValueError):
            errors[key] = "required"

    try:
        azimuth = float(user_input[CONF_AZIMUTH])
        if not 0 <= azimuth < 360:
            errors[CONF_AZIMUTH] = "azimuth_range"
    except (KeyError, TypeError, ValueError):
        errors[CONF_AZIMUTH] = "required"

    return errors


def _window_from_input(user_input: dict[str, Any]) -> dict[str, Any]:
    """Normalise one valid window form submission for storage."""
    window: dict[str, Any] = {
        CONF_WIDTH: float(user_input[CONF_WIDTH]),
        CONF_HEIGHT: float(user_input[CONF_HEIGHT]),
        CONF_AZIMUTH: float(user_input[CONF_AZIMUTH]),
    }
    if cover_entity := user_input.get(CONF_COVER_ENTITY):
        window[CONF_COVER_ENTITY] = cover_entity
    return window


class RoomDaylightConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle setup and reconfiguration for Room Daylight."""

    VERSION = 2

    def __init__(self) -> None:
        """Initialise temporary state used while walking multi-step forms."""
        self._room_data: dict[str, Any] = {}
        self._windows: list[dict[str, Any]] = []
        self._window_count = 1
        self._window_index = 0
        self._reconfigure = False
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

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Collect initial room and source configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _validate_room_input(user_input)
            if not errors:
                room_data = dict(user_input)
                name = str(room_data[CONF_NAME]).strip()
                window_count = int(room_data.pop(CONF_WINDOW_COUNT))

                await self.async_set_unique_id(slugify(name))
                self._abort_if_unique_id_configured()

                room_data[CONF_NAME] = name
                self._room_data = room_data
                self._start_window_steps(window_count=window_count)
                return await self.async_step_window()

        return self.async_show_form(
            step_id="user",
            data_schema=_room_schema(include_name=True),
            errors=errors,
        )

    async def async_step_window(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Collect one exterior window or glazed door."""
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _validate_window_input(user_input)
            if not errors:
                self._windows.append(_window_from_input(user_input))
                self._window_index += 1

                if self._window_index < self._window_count:
                    return await self.async_step_window()

                data = {**self._room_data, CONF_WINDOWS: list(self._windows)}
                if self._reconfigure:
                    return self.async_update_reload_and_abort(
                        self._get_reconfigure_entry(),
                        data_updates=data,
                    )
                return self.async_create_entry(title=data[CONF_NAME], data=data)

        schema = _window_schema()
        if self._reconfigure and self._window_index < len(self._existing_windows):
            schema = self.add_suggested_values_to_schema(
                schema,
                self._existing_windows[self._window_index],
            )

        return self.async_show_form(
            step_id="window",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "window_number": str(self._window_index + 1),
                "window_total": str(self._window_count),
            },
        )

    async def async_step_reconfigure(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Reconfigure structural room inputs and exterior openings."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _validate_room_input(user_input)
            if not errors:
                room_data = {**entry.data, **user_input}
                window_count = int(room_data.pop(CONF_WINDOW_COUNT))

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
        }
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
