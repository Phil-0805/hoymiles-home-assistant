## Easier setup with station selection

Sign in with your S-Miles Home email and password, then choose a plant by name
and numeric station ID. Manual ID entry remains available, including when the
account's plant list cannot be retrieved. Add the integration again for another
plant from the same account.

- Existing integration entries, entity identifiers and stored data retain the
  same schema. No deletion or reconfiguration is required for existing users.
- Includes English and German setup instructions and translations.
- Adds the cyan/blue solar-panel and lightning icon on a dark circular badge.
- HACS and Hassfest validation run without ignored checks.
- 26 existing tests and 24 Home Assistant setup/discovery tests pass.

Maintainer live test (26 October 2026): plant selection works, selecting the
already configured plant is correctly rejected as a duplicate, and existing
history and measurements remain intact. This confirms that account and setup;
it does not establish compatibility with every Hoymiles account or device.

### Update

Install **0.4.0** in HACS and restart Home Assistant. Beta users can switch from
**0.4.0b1** to this stable release. Existing configured plants do not need to be
removed. Station selection is shown when adding the integration.

This release prepares the project for HACS default-catalog submission. Until
accepted, adding this repository as a custom HACS repository is still required.
