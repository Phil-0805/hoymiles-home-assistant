# v0.6.1b3 — experimental S-Miles Installer monitoring

**Prerelease for account testing. Latest stable remains v0.6.0.**

This beta follows the remaining pre-inspection rejection in issue #16 after
successful DC0 discovery. Static analysis of Installer V3.14.0 establishes a
separate `smc/ad/3.14.0/159/<dc>` identity, a direct neapi pre-inspection start,
app_type 2 routing and a different explicit v1 password calculation.
It does **not** establish the affected account's exact rejection reason or a
confirmed fix. Testing on that account is still required.

## Select the matching account type

Install **v0.6.1b3** through HACS with prereleases enabled and restart HA. In the
integration's account setup, select **S-Miles Installer (experimental, read only)**
for the account that signs into the Installer app. Home remains the default for
existing entries and Home users. The account type is also available during
reauthentication, retaining the existing station and entity identities.
If the previous setup never completed, retry it and select Installer there.
Do not delete an existing working integration or change passwords for this test.

Installer starts pre-inspection on the Installer route, omits old tokens and
selects the password calculation solely from the returned v1/v2/v3. No alternate
profile, host or hash is tried after an arbitrary rejection. Only DC0/1 routing
has been verified for this profile; unsupported challenge regions stop before
password login. Interactive account actions must be completed in the official
app. Existing TLS, auth-redirect restrictions, JSON bounds, request pacing and
account-wide server pauses are retained. Tokens are separated by profile.

## Monitoring scope

Supported experimental reads are plant listing through the manufacturer's web
list operation, validated device-tree discovery, live server lookup/live values,
energy totals and basic inverter identity/model. The Installer app's newer list
UI is not fully replicated; manual station-ID entry remains available if listing
fails, and device access is checked before completing setup.

**Installer battery/device controls, battery temperatures, module charts and
additional inverter telemetry are not enabled.** Unsupported controls are not
offered in options, and their requests are blocked even if old permissions were
enabled. Home functionality, including b2's TOU/basic-plan fixes, is retained.
This is not a full Installer app replacement or a TOU plan editor.

## Report results

Please test once and report separately whether authentication, plant listing,
plant validation and current readings work. Compare PV/grid/load power and
energy totals with the official app. Missing fields stay unavailable; synthetic
protocol tests do not prove live-account permissions or hardware behavior.

For failure, share only the fresh `hoymiles_home.cloud_logging` warnings with
stage, reason, numeric/type labels and `client_profile=installer` where present.
Debug logging is unnecessary. Do not post credentials, tokens, nonce, salt,
password hashes, full URLs, identifiers, raw responses or HARs.

For manual installation, download `hoymiles_home.zip` from
[this release](https://github.com/Phil-0805/hoymiles-home-assistant/releases/tag/v0.6.1b3),
back up the installed integration, extract into `custom_components/hoymiles_home`
and restart HA. `manifest.json` must sit directly in that directory. To roll back,
restore the backup or reinstall the previous version and restart HA.

## Evidence and validation

APK from a third-party mirror, actual package/version/hash checked; publisher
signature authenticity was not independently confirmed. No app was installed
or run, no real account login/device operation was performed and no issue
comment was posted by the agent. Manufacturer source/binaries remain outside
the repository. See
[the protocol notes](https://github.com/Phil-0805/hoymiles-home-assistant/blob/v0.6.1b3/docs/installer-app-protocol.md)
for provenance, call chains, public routing checks and limitations.

Local validation: **921 HA tests on each of HA 2026.10.4 and
2026.11.0**, plus **56 unit tests and 134 subtests**, syntax, translation-key parity, local links,
whitespace and release package checks. Required CI, HACS and Hassfest gate
publication. Account confirmation remains outstanding.
