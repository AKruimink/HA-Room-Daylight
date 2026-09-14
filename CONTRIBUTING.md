# Contributing to Room Daylight

Contributions are welcome. Keeping the code easy to understand is a project goal, so focused changes are preferred over large unrelated refactors.

## Workflow

1. Fork the repository.
2. Create a branch from `dev`.
3. Make one focused change per pull request.
4. Open the pull request back into `dev`.
5. Add or update tests when behaviour changes.

Useful branch names include:

```text
feature/window-transmission
fix/missing-sun-state
docs/improve-setup-guide
```

## Project structure

The integration is intentionally small:

```text
custom_components/room_daylight/
├── __init__.py       # Config-entry lifecycle and migrations
├── calculation.py    # Pure daylight model; no Home Assistant dependencies
├── config_flow.py    # Setup, reconfigure and options flows
├── const.py          # Shared config keys and model defaults
└── sensor.py         # Home Assistant entities and state collection
```

Keep calculation logic in `calculation.py` where possible. Home Assistant state handling belongs in the entity/config layers rather than in the pure model.

## Python style

Follow the style already used in the integration:

- use type hints for function inputs and return values;
- prefer small functions with one clear responsibility;
- use descriptive names instead of abbreviations;
- keep control flow shallow where practical;
- add comments for *why* something is done, not for obvious syntax;
- use docstrings for public classes/functions and non-obvious helpers;
- avoid duplicating model logic in the Home Assistant entity layer;
- keep behaviour changes separate from formatting/refactoring changes when possible.

The code targets modern Python and Home Assistant. Keep formatting compatible with standard Ruff/Black-style Python formatting (88-character lines where practical).

## Tests

Run the pure calculation tests before opening a pull request:

```bash
python -m unittest discover -s tests -v
```

You can also check that the integration compiles cleanly:

```bash
python -m compileall custom_components/room_daylight tests
```

GitHub Actions additionally runs Hassfest and HACS validation. All required checks should pass before a pull request is merged.

## Pull requests

Please include:

- what changed;
- why the change is useful;
- how it was tested; and
- screenshots for user-interface changes where helpful.

Do not include Home Assistant secrets, access tokens, precise location data or other private configuration in issues, fixtures, logs or pull requests.
