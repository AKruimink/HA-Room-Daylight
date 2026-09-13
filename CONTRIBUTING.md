# Contributing to Room Daylight

Contributions are welcome through GitHub pull requests.

## Before opening a pull request

1. Fork the repository.
2. Create a branch from `dev` for your change.
3. Keep changes focused on one feature or fix.
4. Add or update tests when changing the daylight calculation.
5. Run the unit tests:

   ```bash
   python -m unittest discover -s tests -v
   ```

6. Make sure the GitHub Hassfest and HACS validation checks pass.

## Pull requests

Please explain what the change does, why it is needed, and how it was tested. Screenshots are useful for config-flow or Home Assistant UI changes.

Do not include Home Assistant secrets, tokens, precise location data, or other private information in issues, logs, fixtures, or pull requests.

## Code ownership

The maintainer reviews and merges changes to the default branch. Opening a pull request does not grant direct write access to the repository.
