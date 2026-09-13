# Room Daylight

![Room Daylight icon](images/icon.png)

Room Daylight is a Home Assistant custom integration that estimates the amount of natural daylight available inside individual rooms.

Instead of relying on one indoor illuminance sensor, whose reading can vary significantly with placement, direct sunlight, furniture and artificial lighting, Room Daylight combines an outdoor illuminance reading with room and window information to create a stable estimated daylight sensor in lux.

Each configured room creates its own illuminance sensor for use in automations, dashboards, scripts and templates.

## Features

- Configure any number of rooms through the Home Assistant UI.
- Each room is a normal integration config entry with its own illuminance entity.
- Reconfigure room geometry and source entities without deleting the room.
- Change optional indoor sensors and artificial-light exclusions from Configure / Options.
- Use any existing outdoor illuminance sensor as the daylight source.
- Account for current sun azimuth and elevation from a user-selected Sun entity.
- Configure multiple windows with dimensions and orientation.
- Exclude windows when linked blinds or curtains are closed.
- Optionally use existing indoor lux sensors as bounded supporting inputs.
- Ignore indoor lux readings while selected artificial lights are on.
- Expose useful calculation diagnostics as sensor attributes.
- No YAML configuration required.

## How it works

Room Daylight uses:

- outdoor illuminance;
- current sun position;
- room floor area;
- window dimensions;
- window orientation;
- optional window coverings;
- optional indoor illuminance sensors; and
- optional artificial-light entities.

The outdoor illuminance value is treated as the source of truth for current outdoor brightness. Room Daylight therefore does not perform its own cloud or weather calculation.

This keeps the integration independent of the source of the outdoor value. You can start with an estimated outdoor illuminance integration and later replace it with a physical outdoor lux sensor or weather station without changing the room model.

Indoor lux sensors are optional. When present, their readings are used as a bounded correction to the calculated estimate rather than replacing the model outright. This reduces the effect of badly placed sensors, dark corners and direct sun patches.

## Recommended companion integrations and sensors

### Illuminance

[Illuminance](https://github.com/pnbruckner/ha-illuminance) is a useful companion integration if you do not have a physical outdoor illuminance sensor. It estimates outdoor illuminance from the sun position and can incorporate weather or cloud information.

Room Daylight can then use that resulting lux sensor as its outdoor source.

### Physical outdoor illuminance sensors

Any Home Assistant sensor providing illuminance in lux can be used, including compatible ESPHome, Zigbee or Z-Wave light sensors and weather stations.

### Indoor illuminance sensors

Lux readings exposed by motion sensors, presence sensors, plant sensors or dedicated light sensors can optionally reinforce the model. They are never required.

### Blinds and curtains

A Home Assistant `cover`, `binary_sensor` or `input_boolean` can be linked to a window. A covered window is removed from the daylight contribution.

## Example automation

Once a room has been configured, Home Assistant exposes an illuminance entity such as:

```text
sensor.lounge_estimated_daylight
```

A lighting automation can then simply use a condition such as:

```text
Motion detected
AND
Lounge Estimated Daylight < 120 lx
THEN
Turn on lounge lights
```

## Installation

### HACS

1. Open HACS.
2. Add this GitHub repository as a custom repository of type **Integration**.
3. Download **Room Daylight**.
4. Restart Home Assistant.
5. Go to **Settings → Devices & services → Add integration**.
6. Search for **Room Daylight**.

### Manual

Copy:

```text
custom_components/room_daylight
```

to:

```text
<config>/custom_components/room_daylight
```

Then restart Home Assistant.

## Configuration

Each Room Daylight config entry represents one room.

The setup flow asks for:

1. room name;
2. an outdoor illuminance entity (filtered to illuminance sensors);
3. a Sun entity providing azimuth and elevation;
4. room floor area;
5. the number of external glazed openings;
6. optional indoor illuminance sensors;
7. optional artificial lights that invalidate indoor lux readings; and
8. each window or glazed door, including width, height, outward-facing azimuth and optional covering entity.

After setup, use **Configure / Options** to change the optional indoor sensors and lights. Use **Reconfigure** from the config-entry menu to change the outdoor source, Sun entity, room area, or windows.

Window azimuth follows the standard compass convention:

| Direction | Azimuth |
| --- | ---: |
| North | 0° |
| East | 90° |
| South | 180° |
| West | 270° |

## Accuracy

Room Daylight is intended to provide a stable automation-oriented estimate of usable room daylight. It is not a photometrically accurate building-lighting simulation.

The model is deliberately designed to be predictable, explainable and resistant to noisy local lux sensors.

## Development

Repository validation runs through GitHub Actions using both Hassfest and HACS validation. The pure daylight calculation also has unit tests under `tests/`.

The integration includes local Home Assistant branding assets under `custom_components/room_daylight/brand/` so the icon can be used in Home Assistant and by HACS.

## Contributing

Bug reports, feature requests and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) before submitting code changes.

## Licence

MIT
