# Development notes

Room Daylight is split into a small Home Assistant layer and a pure calculation layer. Keeping that boundary clear makes the model easier to test and future features easier to review.

## Data flow

```text
Home Assistant entities
        │
        ▼
     sensor.py
  collect/normalise
        │
        ▼
  calculation.py
   pure model
        │
        ▼
 DaylightEstimate
        │
        ▼
     sensor.py
 entity + diagnostics
```

### `calculation.py`

Contains the daylight model and its result dataclasses. It must remain independent of Home Assistant so the model can be tested with ordinary Python unit tests.

If a calculation can be expressed without reading Home Assistant state, it probably belongs here.

### `sensor.py`

Owns the Home Assistant sensor entities. It reads entity states, resolves window coverings and optional indoor sensors, calls the pure model, and exposes the result and diagnostics.

Avoid reimplementing mathematical rules here. Convert Home Assistant state into model inputs, then let `calculation.py` do the calculation.

### `config_flow.py`

Owns setup, reconfigure and options forms. Form schemas and validation should stay close together so a field's accepted values are easy to understand.

### `const.py`

Contains persisted config keys and shared defaults. Take care when changing stored keys or defaults because existing config entries may need migration logic in `__init__.py`.

## Changing the model

When changing daylight behaviour:

1. make the model change in `calculation.py`;
2. add or update a focused test in `tests/test_calculation.py`;
3. expose new diagnostics in `sensor.py` only when they are useful to users;
4. document user-visible behaviour in the README; and
5. use a config-entry migration if stored data changes.

Prefer explicit intermediate values over compact formulas when that makes the model easier to audit.

## Home Assistant conventions

Follow current Home Assistant patterns for config entries, selectors and entities. Hassfest and HACS validation run on pull requests and are the final check for integration-specific conventions.

## Model parameters

Advanced tuning values are persisted in `ConfigEntry.data`; do not read model defaults directly from `sensor.py`. Existing entries are migrated so their effective defaults become explicit configuration. Per-window transmission is stored with each window.

Config-flow validation is intentionally duplicated at two layers: selectors define frontend ranges, while flow validation returns field-specific errors for submitted or restored values. Keep both when adding new numeric fields.
