"""Config flow for Room Daylight."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import voluptuous as vol

from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    SOURCE_USER,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentry,
    ConfigSubentryFlow,
    FlowType,
    SubentryFlowContext,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import SectionConfig, section
from homeassistant.helpers import selector

from .const import (
    CONF_AREA_ID,
    CONF_ARTIFICIAL_LIGHT_ENTITIES,
    CONF_AZIMUTH,
    CONF_CLOSED_TRANSMISSION,
    CONF_CONNECTION_MODEL,
    CONF_CONNECTION_NAME,
    CONF_CONNECTION_TYPE,
    CONF_COVER_ENTITY,
    CONF_DAYLIGHT_UTILISATION,
    CONF_DIFFUSE_FRACTION,
    CONF_FLOOR_AREA,
    CONF_GLAZING_TRANSMISSION,
    CONF_HEIGHT,
    CONF_INDOOR_LUX_SENSORS,
    CONF_INVERT_STATE,
    CONF_LENGTH,
    CONF_MODEL_DEFAULTS,
    CONF_OPENING_COUNT,
    CONF_OPENING_ID,
    CONF_OPENING_NAME,
    CONF_OPENING_TYPE,
    CONF_OPENINGS,
    CONF_OUTDOOR_ILLUMINANCE_ENTITY,
    CONF_ROOF_PITCH,
    CONF_ROOM_A,
    CONF_ROOM_B,
    CONF_ROOM_MODEL,
    CONF_ROOM_NAME,
    CONF_SENSOR_CORRECTION_STRENGTH,
    CONF_STATE_ENTITY,
    CONF_SUN_ENTITY,
    CONF_TILT,
    CONF_TRANSFER_EFFICIENCY,
    CONF_TRANSMISSION,
    CONF_WIDTH,
    CONNECTION_TYPES,
    CONNECTION_TYPE_STAIRWELL,
    DEFAULT_DAYLIGHT_UTILISATION,
    DEFAULT_DIFFUSE_FRACTION,
    DEFAULT_GLAZING_TRANSMISSION,
    DEFAULT_SENSOR_CORRECTION_STRENGTH,
    DEFAULT_SUN_ENTITY,
    DEFAULT_TRANSFER_EFFICIENCY,
    DOMAIN,
    MAX_EXTERIOR_OPENINGS,
    MAX_FLOOR_AREA_M2,
    MAX_OPENING_DIMENSION_M,
    MIN_FLOOR_AREA_M2,
    MIN_OPENING_DIMENSION_M,
    NAME,
    OPENING_TYPES,
    OPENING_TYPE_ROOFLIGHT,
    OPENING_TYPE_WALL,
    SUBENTRY_TYPE_CONNECTION,
    SUBENTRY_TYPE_ROOM,
)


def _number_selector(
    minimum: float,
    maximum: float,
    *,
    step: float = 0.01,
) -> selector.NumberSelector:
    """Return a boxed numeric selector with consistent behaviour."""

    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=step,
            mode=selector.NumberSelectorMode.BOX,
        )
    )


def _ratio_selector() -> selector.NumberSelector:
    """Return a 0..1 ratio selector."""

    return _number_selector(0.0, 1.0, step=0.01)


def _entity_selector(
    domains: str | list[str],
    *,
    multiple: bool = False,
    device_class: str | None = None,
) -> selector.EntitySelector:
    """Return an entity selector using current filter-style configuration."""

    entity_filter: selector.EntityFilterSelectorConfig = {"domain": domains}
    if device_class is not None:
        entity_filter["device_class"] = device_class
    return selector.EntitySelector(
        selector.EntitySelectorConfig(
            filter=entity_filter,
            multiple=multiple,
        )
    )


def _static_select(
    options: tuple[str, ...],
    translation_key: str,
) -> selector.SelectSelector:
    """Return a localisable single-value selector."""

    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=list(options),
            translation_key=translation_key,
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _model_defaults(data: dict[str, Any]) -> dict[str, float]:
    """Return global model defaults, filling any absent values defensively."""

    model = data.get(CONF_MODEL_DEFAULTS, {})
    return {
        CONF_DIFFUSE_FRACTION: float(
            model.get(CONF_DIFFUSE_FRACTION, DEFAULT_DIFFUSE_FRACTION)
        ),
        CONF_GLAZING_TRANSMISSION: float(
            model.get(CONF_GLAZING_TRANSMISSION, DEFAULT_GLAZING_TRANSMISSION)
        ),
        CONF_DAYLIGHT_UTILISATION: float(
            model.get(CONF_DAYLIGHT_UTILISATION, DEFAULT_DAYLIGHT_UTILISATION)
        ),
        CONF_TRANSFER_EFFICIENCY: float(
            model.get(CONF_TRANSFER_EFFICIENCY, DEFAULT_TRANSFER_EFFICIENCY)
        ),
        CONF_SENSOR_CORRECTION_STRENGTH: float(
            model.get(
                CONF_SENSOR_CORRECTION_STRENGTH,
                DEFAULT_SENSOR_CORRECTION_STRENGTH,
            )
        ),
    }


def _global_schema(existing: dict[str, Any] | None = None) -> vol.Schema:
    """Build the parent-entry schema."""

    existing = existing or {}
    defaults = _model_defaults(existing)
    return vol.Schema(
        {
            vol.Required(
                CONF_OUTDOOR_ILLUMINANCE_ENTITY,
                description={
                    "suggested_value": existing.get(
                        CONF_OUTDOOR_ILLUMINANCE_ENTITY
                    )
                },
            ): _entity_selector("sensor", device_class="illuminance"),
            vol.Required(
                CONF_SUN_ENTITY,
                default=existing.get(CONF_SUN_ENTITY, DEFAULT_SUN_ENTITY),
            ): _entity_selector("sun"),
            vol.Required(CONF_MODEL_DEFAULTS): section(
                vol.Schema(
                    {
                        vol.Required(
                            CONF_DIFFUSE_FRACTION,
                            default=defaults[CONF_DIFFUSE_FRACTION],
                        ): _ratio_selector(),
                        vol.Required(
                            CONF_GLAZING_TRANSMISSION,
                            default=defaults[CONF_GLAZING_TRANSMISSION],
                        ): _ratio_selector(),
                        vol.Required(
                            CONF_DAYLIGHT_UTILISATION,
                            default=defaults[CONF_DAYLIGHT_UTILISATION],
                        ): _ratio_selector(),
                        vol.Required(
                            CONF_TRANSFER_EFFICIENCY,
                            default=defaults[CONF_TRANSFER_EFFICIENCY],
                        ): _ratio_selector(),
                        vol.Required(
                            CONF_SENSOR_CORRECTION_STRENGTH,
                            default=defaults[CONF_SENSOR_CORRECTION_STRENGTH],
                        ): _ratio_selector(),
                    }
                ),
                SectionConfig(collapsed=True),
            ),
        }
    )


class RoomDaylightConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configure the single house-wide Room Daylight environment."""

    VERSION = 1

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls,
        config_entry: ConfigEntry,
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return the subentry types managed by this integration."""

        return {
            SUBENTRY_TYPE_ROOM: RoomSubentryFlow,
            SUBENTRY_TYPE_CONNECTION: ConnectionSubentryFlow,
        }

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Set up the global daylight environment."""

        if user_input is not None:
            return self.async_create_entry(title=NAME, data=user_input)

        return self.async_show_form(step_id="user", data_schema=_global_schema())

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfigure global daylight sources and defaults."""

        entry = self._get_reconfigure_entry()
        if user_input is not None:
            # The config-entry update listener owns reloading.  Keeping reload
            # in one place also means room/connection add, edit and removal
            # use the exact same lifecycle path.
            return self.async_update_and_abort(entry, data=user_input)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_global_schema(dict(entry.data)),
        )

    async def async_on_create_entry(
        self, result: ConfigFlowResult
    ) -> ConfigFlowResult:
        """Open the first room flow immediately after initial setup."""

        subentry_result = await self.hass.config_entries.subentries.async_init(
            (result["result"].entry_id, SUBENTRY_TYPE_ROOM),
            context=SubentryFlowContext(source=SOURCE_USER),
        )
        result["next_flow"] = (
            FlowType.CONFIG_SUBENTRIES_FLOW,
            subentry_result["flow_id"],
        )
        return result


class RoomSubentryFlow(ConfigSubentryFlow):
    """Add or reconfigure one room and its exterior glazed openings."""

    def __init__(self) -> None:
        """Initialise transient wizard state."""

        self._prepared = False
        self._existing: dict[str, Any] = {}
        self._room_data: dict[str, Any] = {}
        self._existing_openings: list[dict[str, Any]] = []
        self._openings: list[dict[str, Any]] = []
        self._opening_count = 0
        self._opening_index = 0
        self._opening_type: str | None = None

    def _prepare(self) -> None:
        """Load reconfigure data once, or initialise an empty room."""

        if self._prepared:
            return
        if self.source == SOURCE_RECONFIGURE:
            self._existing = dict(self._get_reconfigure_subentry().data)
            self._existing_openings = [
                dict(item) for item in self._existing.get(CONF_OPENINGS, ())
            ]
        self._prepared = True

    def _room_schema(self) -> vol.Schema:
        """Build the basic room schema using parent defaults."""

        parent_defaults = _model_defaults(dict(self._get_entry().data))
        room_model = self._existing.get(CONF_ROOM_MODEL, {})
        daylight_utilisation = float(
            room_model.get(
                CONF_DAYLIGHT_UTILISATION,
                parent_defaults[CONF_DAYLIGHT_UTILISATION],
            )
        )
        sensor_correction = float(
            room_model.get(
                CONF_SENSOR_CORRECTION_STRENGTH,
                parent_defaults[CONF_SENSOR_CORRECTION_STRENGTH],
            )
        )

        schema: dict[Any, Any] = {
            vol.Required(
                CONF_ROOM_NAME,
                default=self._existing.get(CONF_ROOM_NAME, ""),
            ): selector.TextSelector(),
            vol.Required(
                CONF_FLOOR_AREA,
                default=self._existing.get(CONF_FLOOR_AREA, 10.0),
            ): _number_selector(MIN_FLOOR_AREA_M2, MAX_FLOOR_AREA_M2, step=0.1),
            vol.Optional(
                CONF_AREA_ID,
                description={
                    "suggested_value": self._existing.get(CONF_AREA_ID)
                },
            ): selector.AreaSelector(),
            vol.Required(
                CONF_OPENING_COUNT,
                default=len(self._existing_openings),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=MAX_EXTERIOR_OPENINGS,
                    step=1,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(
                CONF_INDOOR_LUX_SENSORS,
                default=list(self._existing.get(CONF_INDOOR_LUX_SENSORS, ())),
            ): _entity_selector(
                "sensor",
                multiple=True,
                device_class="illuminance",
            ),
            vol.Optional(
                CONF_ARTIFICIAL_LIGHT_ENTITIES,
                default=list(
                    self._existing.get(CONF_ARTIFICIAL_LIGHT_ENTITIES, ())
                ),
            ): _entity_selector(["light", "switch"], multiple=True),
            vol.Required(CONF_ROOM_MODEL): section(
                vol.Schema(
                    {
                        vol.Required(
                            CONF_DAYLIGHT_UTILISATION,
                            default=daylight_utilisation,
                        ): _ratio_selector(),
                        vol.Required(
                            CONF_SENSOR_CORRECTION_STRENGTH,
                            default=sensor_correction,
                        ): _ratio_selector(),
                    }
                ),
                SectionConfig(collapsed=True),
            ),
        }
        return vol.Schema(schema)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Add a room."""

        self._prepare()
        return await self._async_step_room(user_input, "user")

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Reconfigure a room."""

        self._prepare()
        return await self._async_step_room(user_input, "reconfigure")

    async def _async_step_room(
        self,
        user_input: dict[str, Any] | None,
        step_id: str,
    ) -> SubentryFlowResult:
        """Handle common room fields."""

        if user_input is None:
            return self.async_show_form(
                step_id=step_id,
                data_schema=self._room_schema(),
            )

        data = dict(user_input)
        room_name = str(data.get(CONF_ROOM_NAME, "")).strip()
        if not room_name:
            return self.async_show_form(
                step_id=step_id,
                data_schema=self._room_schema(),
                errors={CONF_ROOM_NAME: "name_required"},
            )
        data[CONF_ROOM_NAME] = room_name
        self._opening_count = int(data.pop(CONF_OPENING_COUNT))
        self._room_data = data
        self._openings = []
        self._opening_index = 0
        self._opening_type = None

        if self._opening_count == 0:
            return self._finish_room()
        return await self.async_step_opening()

    async def async_step_opening(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Choose the type for the current exterior glazed opening."""

        existing = self._current_existing_opening()
        if user_input is not None:
            self._opening_type = str(user_input[CONF_OPENING_TYPE])
            return await self.async_step_opening_details()

        return self.async_show_form(
            step_id="opening",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_OPENING_TYPE,
                        default=existing.get(CONF_OPENING_TYPE, OPENING_TYPE_WALL),
                    ): _static_select(OPENING_TYPES, "opening_type"),
                }
            ),
            description_placeholders={
                "number": str(self._opening_index + 1),
                "total": str(self._opening_count),
            },
        )

    async def async_step_opening_details(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Configure dimensions and orientation for the current opening."""

        if self._opening_type is None:
            return await self.async_step_opening()

        existing = self._current_existing_opening()
        if user_input is not None:
            data = dict(user_input)
            opening_name = str(data.get(CONF_OPENING_NAME, "")).strip()
            if not opening_name:
                return self.async_show_form(
                    step_id="opening_details",
                    data_schema=self._opening_details_schema(existing),
                    errors={CONF_OPENING_NAME: "name_required"},
                    description_placeholders={
                        "number": str(self._opening_index + 1),
                        "total": str(self._opening_count),
                    },
                )
            data[CONF_OPENING_NAME] = opening_name
            opening = self._normalise_opening(data, existing)
            self._openings.append(opening)
            self._opening_index += 1
            self._opening_type = None
            if self._opening_index < self._opening_count:
                return await self.async_step_opening()
            return self._finish_room()

        return self.async_show_form(
            step_id="opening_details",
            data_schema=self._opening_details_schema(existing),
            description_placeholders={
                "number": str(self._opening_index + 1),
                "total": str(self._opening_count),
            },
        )

    def _current_existing_opening(self) -> dict[str, Any]:
        """Return the opening currently being reconfigured, if any."""

        if self._opening_index < len(self._existing_openings):
            return self._existing_openings[self._opening_index]
        return {}

    def _opening_details_schema(self, existing: dict[str, Any]) -> vol.Schema:
        """Build a type-specific opening details schema."""

        defaults = _model_defaults(dict(self._get_entry().data))
        fields: dict[Any, Any] = {
            vol.Required(
                CONF_OPENING_NAME,
                default=existing.get(
                    CONF_OPENING_NAME,
                    f"Opening {self._opening_index + 1}",
                ),
            ): selector.TextSelector(),
            vol.Required(
                CONF_WIDTH,
                default=existing.get(CONF_WIDTH, 1.0),
            ): _number_selector(
                MIN_OPENING_DIMENSION_M, MAX_OPENING_DIMENSION_M, step=0.01
            ),
        }

        if self._opening_type == OPENING_TYPE_ROOFLIGHT:
            fields[
                vol.Required(
                    CONF_LENGTH,
                    default=existing.get(
                        CONF_LENGTH,
                        existing.get(CONF_HEIGHT, 1.0),
                    ),
                )
            ] = _number_selector(
                MIN_OPENING_DIMENSION_M, MAX_OPENING_DIMENSION_M, step=0.01
            )
            fields[
                vol.Required(
                    CONF_ROOF_PITCH,
                    default=existing.get(
                        CONF_ROOF_PITCH,
                        existing.get(CONF_TILT, 0.0),
                    ),
                )
            ] = _number_selector(0.0, 90.0, step=0.5)
        else:
            fields[
                vol.Required(
                    CONF_HEIGHT,
                    default=existing.get(
                        CONF_HEIGHT,
                        existing.get(CONF_LENGTH, 1.0),
                    ),
                )
            ] = _number_selector(
                MIN_OPENING_DIMENSION_M, MAX_OPENING_DIMENSION_M, step=0.01
            )
            if self._opening_type != OPENING_TYPE_WALL:
                fields[
                    vol.Required(
                        CONF_TILT,
                        default=existing.get(CONF_TILT, 90.0),
                    )
                ] = _number_selector(0.0, 180.0, step=0.5)

        fields[
            vol.Required(
                CONF_AZIMUTH,
                default=existing.get(CONF_AZIMUTH, 180.0),
            )
        ] = _number_selector(0.0, 359.9, step=0.1)
        fields[
            vol.Optional(
                CONF_COVER_ENTITY,
                description={"suggested_value": existing.get(CONF_COVER_ENTITY)},
            )
        ] = _entity_selector("cover")
        fields[
            vol.Required(
                CONF_TRANSMISSION,
                default=existing.get(
                    CONF_TRANSMISSION,
                    defaults[CONF_GLAZING_TRANSMISSION],
                ),
            )
        ] = _ratio_selector()
        return vol.Schema(fields)

    def _normalise_opening(
        self,
        user_input: dict[str, Any],
        existing: dict[str, Any],
    ) -> dict[str, Any]:
        """Convert type-specific form data to the common opening model."""

        data = dict(user_input)
        data[CONF_OPENING_ID] = existing.get(CONF_OPENING_ID, uuid4().hex)
        data[CONF_OPENING_TYPE] = self._opening_type
        if self._opening_type == OPENING_TYPE_WALL:
            data[CONF_TILT] = 90.0
        elif self._opening_type == OPENING_TYPE_ROOFLIGHT:
            data[CONF_TILT] = float(data[CONF_ROOF_PITCH])
        return data

    def _finish_room(self) -> SubentryFlowResult:
        """Create or update the room subentry."""

        data = {**self._room_data, CONF_OPENINGS: self._openings}
        title = str(data[CONF_ROOM_NAME]).strip()
        if self.source == SOURCE_USER:
            return self.async_create_entry(title=title, data=data)
        return self.async_update_and_abort(
            self._get_entry(),
            self._get_reconfigure_subentry(),
            title=title,
            data=data,
        )


class ConnectionSubentryFlow(ConfigSubentryFlow):
    """Add or reconfigure a physical daylight connection between two rooms."""

    def __init__(self) -> None:
        """Initialise transient wizard state."""

        self._prepared = False
        self._existing: dict[str, Any] = {}
        self._connection_data: dict[str, Any] = {}

    def _prepare(self) -> None:
        """Load existing connection data when reconfiguring."""

        if self._prepared:
            return
        if self.source == SOURCE_RECONFIGURE:
            self._existing = dict(self._get_reconfigure_subentry().data)
        self._prepared = True

    def _rooms(self) -> list[ConfigSubentry]:
        """Return currently configured room subentries."""

        return [
            subentry
            for subentry in self._get_entry().subentries.values()
            if subentry.subentry_type == SUBENTRY_TYPE_ROOM
        ]

    def _room_options(self) -> list[selector.SelectOptionDict]:
        """Return selector options for configured rooms."""

        return [
            selector.SelectOptionDict(value=room.subentry_id, label=room.title)
            for room in self._rooms()
        ]

    def _room_title(self, room_id: str) -> str:
        """Resolve a room subentry ID to a friendly title."""

        room = self._get_entry().subentries.get(room_id)
        return room.title if room is not None else room_id

    def _connection_schema(self) -> vol.Schema:
        """Build the common connection schema."""

        options = self._room_options()
        first = options[0]["value"] if options else ""
        second = options[1]["value"] if len(options) > 1 else first
        room_ids = {option["value"] for option in options}
        room_a = self._existing.get(CONF_ROOM_A, first)
        room_b = self._existing.get(CONF_ROOM_B, second)
        if room_a not in room_ids:
            room_a = first
        if room_b not in room_ids:
            room_b = second
        if room_a == room_b and len(options) > 1:
            room_b = next(
                option["value"] for option in options if option["value"] != room_a
            )
        defaults = _model_defaults(dict(self._get_entry().data))
        connection_model = self._existing.get(CONF_CONNECTION_MODEL, {})

        return vol.Schema(
            {
                vol.Optional(
                    CONF_CONNECTION_NAME,
                    default=self._existing.get(CONF_CONNECTION_NAME, ""),
                ): selector.TextSelector(),
                vol.Required(
                    CONF_ROOM_A,
                    default=room_a,
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=options)
                ),
                vol.Required(
                    CONF_ROOM_B,
                    default=room_b,
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=options)
                ),
                vol.Required(
                    CONF_CONNECTION_TYPE,
                    default=self._existing.get(
                        CONF_CONNECTION_TYPE, CONNECTION_TYPES[0]
                    ),
                ): _static_select(CONNECTION_TYPES, "connection_type"),
                vol.Required(CONF_CONNECTION_MODEL): section(
                    vol.Schema(
                        {
                            vol.Required(
                                CONF_TRANSFER_EFFICIENCY,
                                default=connection_model.get(
                                    CONF_TRANSFER_EFFICIENCY,
                                    defaults[CONF_TRANSFER_EFFICIENCY],
                                ),
                            ): _ratio_selector(),
                        }
                    ),
                    SectionConfig(collapsed=True),
                ),
            }
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Add a connection."""

        self._prepare()
        if len(self._rooms()) < 2:
            return self.async_abort(reason="need_two_rooms")
        return await self._async_step_connection(user_input, "user")

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Reconfigure a connection."""

        self._prepare()
        if len(self._rooms()) < 2:
            return self.async_abort(reason="need_two_rooms")
        return await self._async_step_connection(user_input, "reconfigure")

    async def _async_step_connection(
        self,
        user_input: dict[str, Any] | None,
        step_id: str,
    ) -> SubentryFlowResult:
        """Handle room selection and connection type."""

        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input[CONF_ROOM_A] == user_input[CONF_ROOM_B]:
                errors["base"] = "same_room"
            else:
                self._connection_data = dict(user_input)
                return await self.async_step_connection_details()

        return self.async_show_form(
            step_id=step_id,
            data_schema=self._connection_schema(),
            errors=errors,
        )

    async def async_step_connection_details(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Configure opening dimensions and optional state sensing."""

        connection_type = str(self._connection_data[CONF_CONNECTION_TYPE])
        if user_input is not None:
            data = {**self._connection_data, **user_input}
            name = str(data.get(CONF_CONNECTION_NAME, "")).strip()
            if not name:
                name = (
                    f"{self._room_title(str(data[CONF_ROOM_A]))} ↔ "
                    f"{self._room_title(str(data[CONF_ROOM_B]))}"
                )
            data[CONF_CONNECTION_NAME] = name
            if self.source == SOURCE_USER:
                return self.async_create_entry(title=name, data=data)
            return self.async_update_and_abort(
                self._get_entry(),
                self._get_reconfigure_subentry(),
                title=name,
                data=data,
            )

        fields: dict[Any, Any] = {
            vol.Required(
                CONF_WIDTH,
                default=self._existing.get(CONF_WIDTH, 0.85),
            ): _number_selector(
                MIN_OPENING_DIMENSION_M, MAX_OPENING_DIMENSION_M, step=0.01
            ),
        }
        if connection_type == CONNECTION_TYPE_STAIRWELL:
            fields[
                vol.Required(
                    CONF_LENGTH,
                    default=self._existing.get(
                        CONF_LENGTH,
                        self._existing.get(CONF_HEIGHT, 2.0),
                    ),
                )
            ] = _number_selector(
                MIN_OPENING_DIMENSION_M, MAX_OPENING_DIMENSION_M, step=0.01
            )
        else:
            fields[
                vol.Required(
                    CONF_HEIGHT,
                    default=self._existing.get(
                        CONF_HEIGHT,
                        self._existing.get(CONF_LENGTH, 2.0),
                    ),
                )
            ] = _number_selector(
                MIN_OPENING_DIMENSION_M, MAX_OPENING_DIMENSION_M, step=0.01
            )

        fields[
            vol.Optional(
                CONF_STATE_ENTITY,
                description={"suggested_value": self._existing.get(CONF_STATE_ENTITY)},
            )
        ] = _entity_selector(["binary_sensor", "input_boolean", "cover"])
        fields[
            vol.Required(
                CONF_INVERT_STATE,
                default=self._existing.get(CONF_INVERT_STATE, False),
            )
        ] = selector.BooleanSelector()
        fields[
            vol.Required(
                CONF_CLOSED_TRANSMISSION,
                default=self._existing.get(CONF_CLOSED_TRANSMISSION, 0.0),
            )
        ] = _ratio_selector()

        return self.async_show_form(
            step_id="connection_details",
            data_schema=vol.Schema(fields),
        )
