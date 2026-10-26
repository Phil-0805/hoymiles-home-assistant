## Station selection beta

After signing in with an S-Miles Home account, select a plant by name and numeric
station ID. Each setup adds one plant; repeat setup to add another plant from
the same account.

- Supports paginated station lists and distinguishes duplicate plant names by ID.
- Keeps manual numeric ID entry in the dropdown and falls back to a manual form
  if discovery is unavailable or the account returns no plants.
- Validates the selected station using the account's device tree before saving.
- Preserves the existing config-entry schema and unique IDs. Existing entries do
  not need to be removed or recreated.
- Includes English and German setup text and Home Assistant config-flow tests.

This is an opt-in pre-release. Choose `0.4.0b1` explicitly in HACS when available
and restart Home Assistant. Stable users do not need to install the beta.
A Home Assistant backup is recommended before testing.

Station discovery uses the unofficial S-Miles Home `select_by_page_c` endpoint.
Its protocol is corroborated by the ioBroker Hoymiles client; this beta has not
yet been live-tested against the maintainer's account. Automated tests use
mocked network responses and Home Assistant's real config-flow manager.

If discovery fails, manual setup remains available. Report the beta version,
whether the plant list appeared, and the displayed error without passwords,
tokens or unredacted diagnostics.
