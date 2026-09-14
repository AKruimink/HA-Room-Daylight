<p align="center">
  <img src="images/icon.png" alt="Room Daylight" width="128">
</p>

# Room Daylight

Room Daylight estimates how much natural daylight is available in each room of a Home Assistant home.

Indoor lux sensors are useful, but their readings can vary heavily with placement, direct sun, furniture and artificial lighting. Fixed sun-elevation rules have the opposite problem: they know where the sun is, but not how bright it actually is outside.

Room Daylight combines both ideas. It starts with an outdoor illuminance reading, then adjusts it for the room and its windows. Optional indoor lux sensors can gently correct the result without becoming the source of truth.

Each configured room creates an illuminance sensor such as:

```text
sensor.living_room_estimated_daylight
```

Use that sensor anywhere you would use a normal lux sensor: automations, dashboards, scripts or templates.

## What it uses

A room is calculated from:

- an outdoor illuminance sensor;
- a Home Assistant Sun entity;
- room floor area;
- window or glazed-door dimensions;
- window orientation;
- optional blinds or curtains;
- optional indoor illuminance sensors; and
- optional artificial lights that invalidate indoor sensor readings.

The outdoor illuminance source should already reflect current conditions. Room Daylight does not perform its own cloud or weather calculation.

If you do not have a physical outdoor lux sensor, [Illuminance](https://github.com/pnbruckner/ha-illuminance) is a good companion integration.

## How the estimate works

1. Each uncovered window contributes daylight based on its size and direction relative to the sun.
2. Those contributions are combined with the outdoor illuminance and room floor area to produce the base room estimate.
3. If indoor lux sensors are configured, their median reading is bounded to a sensible range around the model.
4. That bounded reading is blended conservatively into the final estimate.
5. Indoor sensor correction is disabled while any configured artificial light is on.

The result is intended for home automation, not as a replacement for a professional daylight simulation.

## Installation

### HACS

1. Open HACS.
2. Add this repository as a custom repository of type **Integration**.
3. Install **Room Daylight**.
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

Restart Home Assistant, then add **Room Daylight** from **Settings → Devices & services**.

## Setting up a room

Each Room Daylight config entry represents one room.

You will be asked for:

- **Room name** — for example, `Living Room`.
- **Outdoor illuminance** — a sensor reporting current outdoor light in lux.
- **Sun entity** — normally `sun.sun`.
- **Floor area** — approximate internal floor area in square metres.
- **Windows / glazed doors** — width, height and outward-facing azimuth.
- **Indoor lux sensors** — optional supporting measurements from the room.
- **Artificial lights** — optional lights that make indoor lux readings unsuitable for daylight correction while on.

Window azimuth uses normal compass bearings:

| Direction | Azimuth |
| --- | ---: |
| North | 0° |
| East | 90° |
| South | 180° |
| West | 270° |

A window can also be linked to a `cover`, `binary_sensor` or `input_boolean`. When the linked entity indicates that the window is covered, that window is excluded from the daylight calculation.

Use **Configure / Options** to change optional indoor sensors and artificial lights. Use **Reconfigure** to change the outdoor source, Sun entity, floor area or windows.

## Example automation

A typical lighting automation can simply check the room estimate:

```text
Motion detected
AND
Living Room Estimated Daylight < 120 lx
THEN
Turn on the living-room lights
```

The useful threshold depends on the room and what you do there. A hallway may be comfortable at a much lower value than a kitchen or office.

## Diagnostics

The main estimated-daylight entity exposes calculation details including:

- outdoor illuminance and sun position;
- base and final estimates;
- effective indoor/outdoor daylight ratio;
- contribution from each window;
- individual indoor sensor readings and their median;
- indoor sensor adjustment; and
- the model parameters currently in use.

Additional diagnostic entities are created but disabled by default:

- **Native Daylight**
- **Indoor Sensor Median**
- **Indoor Sensor Adjustment**
- **Effective Daylight Ratio**

Enable them from the entity registry if you want to graph or monitor individual parts of the model.

The effective daylight ratio is a practical diagnostic for this integration. It is not a formal architectural daylight-factor calculation.

## Accuracy

Room Daylight is deliberately a practical model. Real indoor daylight also depends on room depth, glazing type, external obstructions, surface reflectance and many other details that are not currently modelled.

The goal is a stable, explainable value that is useful for automations and behaves more consistently than a single badly placed lux sensor or a fixed sun-elevation threshold.

## Development

Pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for the repository workflow, coding guidelines and test commands.

## Licence

MIT
