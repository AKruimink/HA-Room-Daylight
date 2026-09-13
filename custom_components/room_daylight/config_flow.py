"""Config flow for Room Daylight."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)
from homeassistant.util import slugify

from .const import (
    CONF_ADD_ANOTHER,
    CONF_ARTIFICIAL_LIGHTS,
    CONF_AZIMUTH,
    CONF_COVER_ENTITY,
    CONF_FLOOR_AREA,
    CONF_HEIGHT,
    CONF_INDOOR_ILLUMINANCE,
    CONF_OUTSIDE_ILLUMINANCE,
    CONF_WIDTH,
    CONF_WINDOWS,
    DOMAIN,
)


def _number_selector(minimum: float, maximum: float, step: float) -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=step,
            mode=NumberSelectorMode.BOX,
        )
    )


class RoomDaylightConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Room Daylight."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise the flow."""
        self._room_data: dict[str, Any] = {}
        self._windows: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Collect the room and sensor inputs."""
        errors: dict[str, str] = {}

        if user_input is not None:
            name = str(user_input[CONF_NAME]).strip()
            if not name:
                errors[CONF_NAME] = "required"
            else:
                await self.async_set_unique_id(slugify(name))
                self._abort_if_unique_id_configured()
                self._room_data = dict(user_input)
                self._room_data[CONF_NAME] = name
                return await self.async_step_window()

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME): str,
                vol.Required(CONF_OUTSIDE_ILLUMINANCE): EntitySelector(
                    EntitySelectorConfig(domain="sensor")
                ),
                vol.Required(CONF_FLOOR_AREA): _number_selector(0.1, 1000.0, 0.1),
                vol.Optional(CONF_INDOOR_ILLUMINANCE, default=[]): EntitySelector(
                    EntitySelectorConfig(domain="sensor", multiple=True)
                ),
                vol.Optional(CONF_ARTIFICIAL_LIGHTS, default=[]): EntitySelector(
                    EntitySelectorConfig(domain="light", multiple=True)
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_window(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Collect one window and repeat until the user is finished."""
        if user_input is not None:
            window = {
                CONF_WIDTH: float(user_input[CONF_WIDTH]),
                CONF_HEIGHT: float(user_input[CONF_HEIGHT]),
                CONF_AZIMUTH: float(user_input[CONF_AZIMUTH]),
            }
            if cover_entity := user_input.get(CONF_COVER_ENTITY):
                window[CONF_COVER_ENTITY] = cover_entity
            self._windows.append(window)

            if user_input.get(CONF_ADD_ANOTHER, False):
                return await self.async_step_window()

            data = dict(self._room_data)
            data[CONF_WINDOWS] = list(self._windows)
            return self.async_create_entry(title=data[CONF_NAME], data=data)

        schema = vol.Schema(
            {
                vol.Required(CONF_WIDTH): _number_selector(0.01, 50.0, 0.01),
                vol.Required(CONF_HEIGHT): _number_selector(0.01, 20.0, 0.01),
                vol.Required(CONF_AZIMUTH): _number_selector(0.0, 359.0, 1.0),
                vol.Optional(CONF_COVER_ENTITY): EntitySelector(
                    EntitySelectorConfig(
                        domain=["cover", "binary_sensor", "input_boolean"]
                    )
                ),
                vol.Optional(CONF_ADD_ANOTHER, default=False): BooleanSelector(),
            }
        )

        return self.async_show_form(
            step_id="window",
            data_schema=schema,
            description_placeholders={
                "window_number": str(len(self._windows) + 1),
            },
        )
