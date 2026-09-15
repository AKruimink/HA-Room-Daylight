# Room Daylight

Room Daylight is a Home Assistant custom integration that estimates **natural daylight inside rooms** for automation and dashboard use.

Version **1.0.0** is a clean-slate whole-house model. Instead of configuring one integration entry per room, it uses one global Room Daylight entry with independently managed **room** and **connection** subentries.

> Room Daylight is an automation-oriented daylight heuristic. It is designed to give stable, explainable estimates for Home Assistant automations; it is not a replacement for Radiance, climate-based daylight modelling, or a calibrated architectural lux study.

## What 1.0.0 models

```text
Outdoor illuminance + sun position
              |
              v
     Exterior glazed openings
              |
              v
        Native daylight
              |
              v
      Whole-house room graph
      doors / arches / stairs
              |
              v
       Modelled daylight
              |
              v
       Local lux correction
              |
              v
       Estimated daylight
```

The model supports:

- one house-wide outdoor illuminance source and sun entity;
- rooms with zero or more exterior glazed openings;
- vertical windows and glazed exterior doors;
- rooflights and skylights with proper 3D solar incidence;
- arbitrary custom glazed planes;
- blinds and curtains exposed as Home Assistant `cover` entities;
- room-to-room daylight transfer through doors, archways, stairwells and custom openings;
- multiple physical connections between the same pair of rooms;
- optional door/opening state entities;
- multi-hop daylight transfer across several rooms;
- optional indoor lux sensor correction that remains local to its room;
- artificial-light suppression so configured lamps do not contaminate the daylight correction;
- detailed per-room diagnostics explaining where the estimate came from.

## Requirements

- Home Assistant **2026.8.0 or newer**.
- An outdoor illuminance sensor with device class `illuminance`.
- The normal Home Assistant `sun` integration (usually `sun.sun`).

The integration has no third-party Python runtime dependencies.

## Installation

### HACS

1. Add this repository to HACS as a custom **Integration** repository.
2. Install **Room Daylight**.
3. Restart Home Assistant.
4. Go to **Settings -> Devices & services -> Add integration**.
5. Search for **Room Daylight**.

### Manual

Copy:

```text
custom_components/room_daylight/
```

into your Home Assistant configuration directory at:

```text
/config/custom_components/room_daylight/
```

Restart Home Assistant and add the integration from **Settings -> Devices & services**.

## Removal

1. In Home Assistant, open **Settings -> Devices & services -> Integrations**.
2. Remove **Room Daylight**.
3. If installed through HACS, uninstall the repository from HACS. For a manual installation, remove `/config/custom_components/room_daylight`.
4. Restart Home Assistant after removing the integration files.

If you only want to remove a room, remove any connections that reference it first. A dangling connection is ignored safely at runtime, but removing the connection first keeps the stored configuration tidy.

## Initial setup

Room Daylight is deliberately a **single integration entry**.

During initial setup choose:

- **Outdoor illuminance** — the exterior lux sensor used as the house-wide daylight environment.
- **Sun entity** — normally `sun.sun`.
- **Model defaults** — optional tuning defaults for newly configured rooms, openings and connections.

After the parent entry is created, Home Assistant immediately opens the first room flow. Additional rooms and connections are managed beneath the same Room Daylight integration entry.

## Rooms

Each room stores:

- room name;
- floor area in m²;
- optional Home Assistant area;
- zero to twenty exterior glazed openings;
- optional indoor illuminance sensors;
- optional artificial-light entities that can affect those sensors;
- room-level daylight utilisation and sensor-correction tuning.

A room may have **zero exterior openings**. This is the intended configuration for hallways, landings and other internal spaces that receive daylight only through connected rooms.

Room identity is based on Home Assistant's stable config-subentry ID, not the room name. Renaming a room therefore does not change its sensor unique IDs or break its connections.

## Exterior glazed openings

An exterior glazed opening is any glazed surface that admits daylight directly from outside: a normal window, glazed exterior door, French door, sliding patio door, rooflight, skylight, and so on.

Every opening is reduced internally to a plane with:

- glazed area;
- azimuth;
- tilt;
- glazing transmission;
- optional cover openness.

### Wall window / glazed exterior door

Configure:

- name;
- width and height;
- outward-facing direction (azimuth);
- optional blind/curtain cover;
- glazing transmission.

Wall glazing always uses a tilt of **90°**.

### Rooflight / skylight

Configure:

- name;
- width and length;
- roof pitch;
- facing direction;
- optional blind cover;
- glazing transmission.

A flat rooflight uses a roof pitch of **0°**. Its azimuth has no practical effect because its surface normal points straight upwards.

### Custom glazed plane

Configure width, height, azimuth and tilt explicitly.

### Orientation conventions

Azimuth is clockwise from north:

| Direction | Azimuth |
| --- | ---: |
| North | 0° |
| East | 90° |
| South | 180° |
| West | 270° |

Tilt is measured from horizontal:

| Surface | Tilt |
| --- | ---: |
| Flat, sky-facing rooflight | 0° |
| 35° pitched rooflight | 35° |
| Vertical wall glazing | 90° |

The direct component is calculated from the dot product of the sun vector and opening surface normal. This means a high sun naturally has strong incidence on a rooflight while a vertical façade opening behaves differently. Diffuse daylight also uses an isotropic sky-view factor, so upward-facing glazing sees more sky than vertical glazing.

## Blinds and curtains

An exterior opening can reference a Home Assistant `cover` entity.

- If `current_position` is available, 0% is treated as fully closed and 100% as fully open.
- Otherwise `open`/`opening` is treated as open and `closed`/`closing` as closed.
- Missing or unavailable cover state fails closed and contributes no daylight.

This conservative behaviour is intentional for lighting automation.

## Room connections

A connection is a first-class object between two rooms. It is not stored inside either room, so one physical doorway only needs to be configured once.

Supported connection types are:

- **Door / doorway** — width × height;
- **Open archway** — width × height;
- **Stairwell** — width × opening length;
- **Custom opening** — width × height.

Multiple connections between the same rooms are allowed.

### Optional state entity

A connection can reference a:

- `binary_sensor`;
- `input_boolean`;
- `cover`.

Without a state entity, the connection is considered permanently open.

For binary-style entities:

- `on` = open;
- `off` = closed.

`Invert state` handles devices with opposite semantics. Covers use `current_position` where available.

If a configured state entity is unavailable, the opening **fails closed**. Underestimating daylight and turning a light on is safer than assuming a doorway is open and leaving a room dark.

### Closed transmission

Connections are not internally restricted to a binary open/closed model.

`Closed transmission` lets a closed opening pass some daylight. For example:

- solid door: `0.00`;
- partly glazed internal door: perhaps `0.15`;
- open door: the runtime transmission rises to `1.00`.

The effective runtime transmission is interpolated continuously for position-aware covers.

## Whole-house transfer model

Room-to-room transfer uses a bounded weighted-equilibration solver.

For a connection transmitting light into room B:

```text
weight = opening_area
         / receiving_room_floor_area
         * transfer_efficiency
         * opening_transmission
```

The same physical opening is therefore mathematically asymmetric: it naturally affects a 5 m² hallway more strongly than a 30 m² lounge.

For each iteration:

```text
candidate = (
    native_lux
    + sum(connection_weight * neighbouring_room_lux)
) / (
    1 + sum(connection_weight)
)

new_lux = max(native_lux, candidate)
```

The solver stops when the largest change is below **0.1 lx** or after a hard maximum of 50 iterations.

### Important invariant

The room graph can redistribute modelled daylight, but it cannot manufacture brightness:

> A room cannot become brighter through transfer than the brightest reachable native daylight source.

This avoids the positive-feedback behaviour of a naïve additive room network and keeps multi-hop results predictable.

## Indoor lux sensor correction

Indoor physical lux sensors are optional and are used **after** room-network transfer.

That order is important:

```text
Exterior daylight
    -> native daylight
    -> room network
    -> modelled daylight
    -> local lux correction
    -> final estimate
```

Physical sensor readings never feed the room graph, so a sensor sitting in a sun patch cannot make distant rooms artificially brighter.

When several indoor sensors are configured, Room Daylight uses their **median** to reduce sensitivity to a single unusual measurement.

The correction is blended using the room's `Indoor sensor correction strength`.

If any configured artificial light entity is `on`, missing, unknown or unavailable,
sensor correction for that room is conservatively suppressed. The modelled
natural-light value is still available and the artificial light cannot propagate
into other rooms. Treating an unavailable light state this way prevents an
unverified electric-light contribution from being learnt as daylight.

## Sensors

Each room exposes one enabled sensor:

- **Estimated daylight** — the final automation-oriented estimate in lux.

It also creates disabled-by-default diagnostic sensors:

- **Native daylight**;
- **Transferred daylight**;
- **Indoor sensor median**;
- **Indoor sensor adjustment**;
- **Effective daylight ratio**.

Enable any diagnostic sensor from the entity registry when you want to tune or inspect the model.

The main Estimated daylight entity also exposes detailed attributes for every exterior opening and room connection, including incidence, sky view, cover openness, transfer weight, transmission, contribution and solver convergence information.

## Default model parameters

| Parameter | Default | Meaning |
| --- | ---: | --- |
| Diffuse daylight fraction | 0.35 | Share of the orientation heuristic attributed to diffuse sky light |
| Glazing transmission | 0.70 | Default optical transmission for newly configured exterior glazing |
| Daylight utilisation | 0.35 | Room-level reduction from admitted glazing light to useful room illuminance |
| Room-to-room transfer efficiency | 0.65 | Default efficiency for newly configured internal connections |
| Indoor sensor correction strength | 0.35 | Blend between the network model and local physical lux sensors |

`Diffuse daylight fraction` is a global runtime value. The other values are used as defaults when the corresponding room/opening/connection is configured and can then be tuned independently.

## Clean 1.0.0 schema

Version 1.0.0 intentionally contains **no migration path** from the previous experimental one-entry-per-room schema.

If an old development configuration still exists, remove it before installing 1.0.0 and configure the single new Room Daylight entry from scratch.

This keeps the production schema and runtime code small instead of carrying compatibility logic for unpublished development layouts.

## Architecture

The integration is split by responsibility:

```text
custom_components/room_daylight/
├── __init__.py       # config-entry lifecycle
├── config_flow.py    # parent + room + connection UI flows
├── coordinator.py    # HA state subscriptions and orchestration
├── models.py         # framework-independent data objects
├── calculation.py    # exterior daylight + local sensor maths
├── network.py        # pure room-graph solver
├── sensor.py         # thin coordinator-backed entities
├── const.py
├── manifest.json
└── translations/
    ├── de.json
    ├── en.json
    ├── es.json
    ├── fr.json
    └── nl.json
```

`calculation.py`, `network.py` and `models.py` deliberately have no Home Assistant imports. The daylight maths can therefore be unit-tested independently from Home Assistant's framework.

The maintained configuration and entity translations are English (`en`), German (`de`), Spanish (`es`), French (`fr`) and Dutch (`nl`). English is the canonical translation contract; maintained locale files contain the same keys and placeholders so new room, connection and exterior-opening UI is available consistently in every supported language.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the design invariants and lifecycle details.

## Troubleshooting

### Estimated daylight stays at 0 lx

Check the primary sensor attributes first. `outdoor_illuminance_available` should be `true` and `outdoor_lux` should contain a valid non-negative reading. Also check each opening's `cover_openness`: an unavailable blind or curtain entity deliberately fails closed.

### A connected room receives no transferred daylight

Check the connection diagnostics on the receiving room. An unavailable configured door/opening entity fails closed. A solid closed door with `Closed transmission = 0` therefore contributes no daylight until its state becomes open.

### Indoor sensor correction is not applied

Correction is intentionally suppressed when any configured artificial-light entity is on, missing, unknown or unavailable. The `sensor_correction_blocked` attribute exposes this decision.

### `network_converged` is false

The solver stops after a bounded number of iterations even if the configured graph has not reached the 0.1 lx convergence threshold. This should be unusual for realistic room and opening dimensions. Check for very large opening areas, very small receiving floor areas or unusually high transfer efficiency. The estimate remains bounded by the network's native daylight values.

## Development

Install the lightweight development tools into a virtual environment:

```bash
python -m pip install -r requirements-dev.txt
```

Run the test suite:

```bash
pytest -q
```

Run the pure-model coverage check:

```bash
pytest -q \
  --cov=custom_components.room_daylight.calculation \
  --cov=custom_components.room_daylight.models \
  --cov=custom_components.room_daylight.network \
  --cov-report=term-missing
```

Run lint and syntax checks:

```bash
ruff check .
python -m compileall -q custom_components tests
```

The framework-independent calculation, model and network layers are covered directly without requiring a Home Assistant installation. Home Assistant-facing config-flow, coordinator and entity lifecycle behaviour should additionally be smoke-tested in the minimum supported Home Assistant release before publishing a release.

The tests focus particularly on model parsing, rooflight geometry, zero-opening internal rooms, cover transmission, bounded output, local sensor correction, multi-hop transfer, asymmetric receiving-room weights, multiple connections, package metadata, translation contracts and the no-brightness-creation guarantee.

## Limitations

Room Daylight deliberately does not model:

- detailed room geometry or sensor coordinates;
- wall/ceiling reflectance or multiple internal reflections;
- obstructions, overhangs, neighbouring buildings or vegetation;
- weather/sky luminance distributions beyond the chosen outdoor lux source;
- spectral glazing properties;
- full photometric ray tracing.

Treat the result as a stable automation signal to be tuned against your home, not as an architectural compliance value.
