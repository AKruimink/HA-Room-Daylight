# Room Daylight architecture

This document records the design rules behind the Room Daylight 1.0.0 implementation. The goal is to make later maintenance safer: changes should preserve these invariants unless the data model is deliberately redesigned.

## 1. Configuration hierarchy

Room Daylight owns one Home Assistant `ConfigEntry` containing the global daylight environment:

```text
Room Daylight ConfigEntry
├── outdoor illuminance entity
├── sun entity
├── global model values/defaults
├── Room ConfigSubentry
├── Room ConfigSubentry
└── Connection ConfigSubentry
```

`room` and `connection` are separate config-subentry types.

A room or connection is identified internally by its stable `subentry_id`. User-facing names are labels only; renaming an object must not change entity unique IDs or connection references.

## 2. Reload ownership

All persistent config changes ultimately update the parent `ConfigEntry`, including subentry additions, updates and removals.

The integration therefore has exactly one reload owner:

```text
ConfigEntry update listener -> async_reload(entry_id)
```

Config-flow and subentry-flow success paths use update-only helpers and do not explicitly reload. This prevents two independent reload paths from racing each other.

At setup, the coordinator reparses the complete immutable configuration snapshot. A reload after any structural change is deliberately preferred over trying to mutate a live graph in several places.

## 3. Layer boundaries

### `models.py`

Frozen dataclasses and conversion from stored mappings. No Home Assistant imports.

### `calculation.py`

Pure exterior-daylight geometry and post-network local lux correction. No Home Assistant imports.

### `network.py`

Pure bounded room-graph solver. No Home Assistant imports.

### `coordinator.py`

The Home Assistant adapter. It resolves entity state, subscribes to dependencies, constructs runtime connection transmissions, orchestrates the pure calculation pipeline and publishes coherent room snapshots.

### `sensor.py`

Presentation only. Sensor entities should read coordinator snapshots and avoid performing independent daylight calculations.

### `config_flow.py`

Persistence and UI only. It converts user-friendly concepts into the normalised stored model.

## 4. Exterior geometry

Every exterior glazed opening is represented by a plane.

Coordinate convention:

- x = east;
- y = north;
- z = up;
- azimuth = clockwise from north;
- tilt = angle of the plane from horizontal, equivalently angle of its outward normal from vertical.

The sun vector is:

```text
(
    cos(elevation) * sin(azimuth),
    cos(elevation) * cos(azimuth),
    sin(elevation),
)
```

The outward opening normal is:

```text
(
    sin(tilt) * sin(azimuth),
    sin(tilt) * cos(azimuth),
    cos(tilt),
)
```

Direct incidence is the positive part of their dot product. Sun below the horizon always produces a direct factor of zero.

The diffuse sky-view approximation for an upward-facing plane is:

```text
sky_view = (1 + cos(tilt)) / 2
```

and the orientation factor blends direct incidence with sky view using the configured diffuse fraction.

This is intentionally a heuristic orientation model, not a physically complete sky luminance model.

## 5. Native room daylight

Each exterior opening contributes approximately:

```text
outdoor_lux
* (opening_area / room_floor_area)
* effective_glazing_transmission
* orientation_factor
* room_daylight_utilisation
```

Opening contributions are summed and bounded to the non-negative outdoor illuminance value.

Rooms with no exterior glazed openings have zero native daylight by definition.

A cover's openness multiplies glazing transmission. Unavailable cover state fails closed.

## 6. Room network

A configured physical connection is bidirectional, but its influence is directed because the receiving room's floor area appears in the weight:

```text
weight(receiving_room) =
    opening_area
    / receiving_room_floor_area
    * transfer_efficiency
    * runtime_transmission
```

Runtime transmission interpolates between `closed_transmission` and fully open transmission:

```text
runtime_transmission =
    closed_transmission
    + openness * (1 - closed_transmission)
```

No state entity means permanently open. An unavailable configured state entity fails closed before interpolation.

## 7. Bounded network solver

The network uses a Jacobi iteration. All rooms in an iteration are calculated from the previous complete iteration, which avoids update-order dependence.

For room *i*:

```text
candidate_i =
    (native_i + sum(weight_ij * previous_j))
    / (1 + sum(weight_ij))

next_i = max(native_i, candidate_i)
```

Convergence is declared when the largest absolute room change is below 0.1 lx. A 50-iteration hard stop prevents an accidental unbounded workload.

### Invariants

The implementation must preserve:

1. **Native floor** — network transfer never makes a room darker than its native daylight.
2. **No manufactured brightness** — a weighted-average transfer cannot make a room brighter than the brightest reachable native source.
3. **Equal-level stability** — connected rooms at the same native lux remain at that level.
4. **Multi-hop propagation** — daylight may cross several connections over successive iterations.
5. **Area asymmetry** — the same opening has more influence on a smaller receiving room.
6. **Multiple physical connections** — parallel doors/archways between the same room pair are valid and additive in their weights.

Any future solver change should add tests for these properties before replacing the current method.

## 8. Local sensor correction

Indoor lux sensors are deliberately excluded from the room graph.

The order is fixed:

```text
native exterior model
-> room graph
-> modelled daylight
-> room-local physical sensor correction
-> final estimate
```

The physical sensor aggregate is a median. Correction is a bounded linear blend controlled by `sensor_correction_strength`.

If a configured artificial-light entity is on, missing, unknown or unavailable,
correction is suppressed for the room. This stops electric lighting, or an
unverified light state, from being misinterpreted as natural light.

## 9. Event model

The coordinator subscribes to every entity that can change the output:

- global outdoor illuminance;
- sun entity;
- exterior opening covers;
- connection state entities;
- indoor lux sensors;
- configured artificial-light entities.

Any dependency state change recalculates the complete house graph and publishes one new `dict[room_id, RoomSnapshot]` through `DataUpdateCoordinator.async_set_updated_data()`.

The integration is push/event driven; it does not poll.

Whole-network recomputation is intentional. Typical homes have a small graph, and calculating it atomically avoids stale combinations where one room has been updated while a neighbouring room still exposes an earlier graph state.

## 10. Entity identity and ownership

Each room owns one Home Assistant helper device and its room sensors. Entities are added with that room's `config_subentry_id`.

Unique IDs are based on:

```text
{subentry_id}_{sensor_description_key}
```

They must never be based on a mutable room name.

Connection subentries do not create standalone entities. Their runtime effects are exposed in the primary room sensor's diagnostic attributes.

The sensor platform is coordinator-backed and read-only, so it declares
`PARALLEL_UPDATES = 0`. Sensor display names are provided through translation
keys rather than hard-coded English, while room names remain user-supplied data.

## 11. Diagnostics philosophy

The main `Estimated daylight` sensor is enabled by default.

Additional scalar diagnostics are disabled by default to avoid entity clutter. Detailed opening and connection information lives on the primary sensor as attributes.

Diagnostics should answer:

- How much daylight was native to this room?
- How much arrived through the room network?
- Which opening or connection was influential?
- What was the door/blind state and resulting transmission?
- Was local physical-sensor correction applied?
- Did the room graph converge?

Explainability is a design requirement because the integration is intended to drive automations.

## 12. Error posture

Daylight-control failures should be conservative:

- invalid/unavailable lux state is ignored or treated as zero;
- unavailable exterior cover state is closed;
- unavailable connection state is closed;
- missing or unavailable artificial-light state blocks physical-sensor correction;
- dangling connections to deleted rooms are ignored and logged;
- numerical model inputs are clamped where appropriate.

The preferred failure mode is underestimating natural light, which may switch an artificial light on, rather than overestimating daylight and leaving an occupied room dark.

## 13. Versioning

1.0.0 is a clean schema. There is no migration code for the experimental one-entry-per-room implementation.

Do not add compatibility machinery for unpublished development layouts unless there is a concrete installed schema that needs to be supported. Future released schema changes should use Home Assistant's normal config-entry/subentry migration mechanisms deliberately.
