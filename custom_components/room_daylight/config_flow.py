"""Config flow for Room Daylight."""

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


def _number_selector(*, step: float, unit: str | None = None) -> NumberSelector:
    """Create an empty number box; range validation is done by the flow."""
    return NumberSelector(
        NumberSelectorConfig(
            step=step,
            mode=NumberSelectorMode.BOX,
            unit_of_measurement=unit,
        )
    )


def _illuminance_selector(*, multiple: bool = False) -> EntitySelector:
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
    return EntitySelector(EntitySelectorConfig(filter={"domain": "sun"}))


def _lights_selector() -> EntitySelector:
    return EntitySelector(
        EntitySelectorConfig(multiple=True, filter={"domain": "light"})
    )


def _covering_selector() -> EntitySelector:
    return EntitySelector(
        EntitySelectorConfig(
            filter={"domain": ["cover", "binary_sensor", "input_boolean"]}
        )
    )


def _room_schema(*, include_name: bool) -> vol.Schema:
    fields: dict[Any, Any] = {}
    if include_name:
        fields[vol.Required(CONF_NAME)] = TextSelector()
    fields.update(
        {
            vol.Required(CONF_OUTSIDE_ILLUMINANCE): _illuminance_selector(),
            vol.Required(CONF_SUN_ENTITY): _sun_selector(),
            vol.Required(CONF_FLOOR_AREA): _number_selector(step=0.1, unit="m²"),
            vol.Required(CONF_WINDOW_COUNT, default=1): NumberSelector(
                NumberSelectorConfig(
                    min=1,
                    max=20,
                    step=1,
                    mode=NumberSelectorMode.BOX,
                )
            ),
        }
    )
    if include_name:
        fields[vol.Optional(CONF_INDOOR_ILLUMINANCE, default=[])] = (
            _illuminance_selector(multiple=True)
        )
        fields[vol.Optional(CONF_ARTIFICIAL_LIGHTS, default=[])] = _lights_selector()
    return vol.Schema(fields)


def _window_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_WIDTH): _number_selector(step=0.01, unit="m"),
            vol.Required(CONF_HEIGHT): _number_selector(step=0.01, unit="m"),
            vol.Required(CONF_AZIMUTH): _number_selector(step=1, unit="°"),
            vol.Optional(CONF_COVER_ENTITY): _covering_selector(),
        }
    )


def _validate_room_input(user_input: dict[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}
    if CONF_NAME in user_input and not str(user_input[CONF_NAME]).strip():
        errors[CONF_NAME] = "required"
    try:
        floor_area = float(user_input[CONF_FLOOR_AREA])
        if floor_area <= 0:
            errors[CONF_FLOOR_AREA] = "positive_number"
    except (KeyError, TypeError, ValueError):
        errors[CONF_FLOOR_AREA] = "required"
    if not user_input.get(CONF_OUTSIDE_ILLUMINANCE):
        errors[CONF_OUTSIDE_ILLUMINANCE] = "required"
    if not user_input.get(CONF_SUN_ENTITY):
        errors[CONF_SUN_ENTITY] = "required"
    return errors


def _validate_window_input(user_input: dict[str, Any]) -> dict[str, str]:
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


class RoomDaylightConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Room Daylight."""

    VERSION = 2

    def __init__(self) -> None:
        self._room_data: dict[str, Any] = {}
        self._windows: list[dict[str, Any]] = []
        self._window_count = 1
        self._window_index = 0
        self._reconfigure = False
        self._existing_windows: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Collect room and sensor inputs."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_room_input(user_input)
            if not errors:
                name = str(user_input[CONF_NAME]).strip()
                await self.async_set_unique_id(slugify(name))
                self._abort_if_unique_id_configured()
                self._room_data = dict(user_input)
                self._room_data[CONF_NAME] = name
                self._window_count = int(user_input.pop(CONF_WINDOW_COUNT))
                self._room_data.pop(CONF_WINDOW_COUNT, None)
                self._windows = []
                self._window_index = 0
                return await self.async_step_window()
        return self.async_show_form(
            step_id="user",
            data_schema=_room_schema(include_name=True),
            errors=errors,
        )

    async def async_step_window(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Collect each window/glazed opening."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_window_input(user_input)
            if not errors:
                window = {
                    CONF_WIDTH: float(user_input[CONF_WIDTH]),
                    CONF_HEIGHT: float(user_input[CONF_HEIGHT]),
                    CONF_AZIMUTH: float(user_input[CONF_AZIMUTH]),
                }
                if cover_entity := user_input.get(CONF_COVER_ENTITY):
                    window[CONF_COVER_ENTITY] = cover_entity
                self._windows.append(window)
                self._window_index += 1
                if self._window_index < self._window_count:
                    return await self.async_step_window()

                data = dict(self._room_data)
                data[CONF_WINDOWS] = list(self._windows)
                if self._reconfigure:
                    entry = self._get_reconfigure_entry()
                    return self.async_update_reload_and_abort(
                        entry,
                        data_updates=data,
                    )
                return self.async_create_entry(title=data[CONF_NAME], data=data)

        schema = _window_schema()
        if self._reconfigure and self._window_index < len(self._existing_windows):
            schema = self.add_suggested_values_to_schema(
                schema, self._existing_windows[self._window_index]
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
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Reconfigure structural room inputs and windows."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_room_input(user_input)
            if not errors:
                self._reconfigure = True
                self._room_data = dict(entry.data)
                self._room_data.update(user_input)
                self._window_count = int(self._room_data.pop(CONF_WINDOW_COUNT))
                self._existing_windows = list(entry.data.get(CONF_WINDOWS, []))
                self._windows = []
                self._window_index = 0
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
                _room_schema(include_name=False), suggested
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow."""
        return RoomDaylightOptionsFlow()


class RoomDaylightOptionsFlow(config_entries.OptionsFlowWithReload):
    """Manage optional indoor sensors and artificial-light exclusions."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
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
