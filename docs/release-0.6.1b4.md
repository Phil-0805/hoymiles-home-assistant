# v0.6.1b4 — reliable live-response diagnostics

**Prerelease for testing. Latest stable remains v0.6.0.**

This beta packages the live-diagnostic changes as a complete HACS update,
replacing the need to manually edit Python files. The maintainer's manual
test installation raised `UnboundLocalError: object_state` when describing an
invalid live response. All diagnostic state variables in b4 are initialized
unconditionally, including when the response has no connection state or delay.
Synthetic tests cover empty, incomplete, delay-only and non-object payloads.

## What changes

- Invalid live-response warnings distinguish an empty object from a nonempty
  object and record only the fixed type/state of the optional `dly` field.
  No raw payload, field names supplied by the server, measurements, delay values,
  URLs, credentials or device identifiers are logged.
- Recovery messages add `recovery_scope=same_refresh` when the existing retry
  succeeds inside one live call, or `recovery_scope=later_refresh` when an
  invalid-data episode was already present at the start of the call.
- The misleading error **Live URI expired** is replaced by **Live response
  contains no usable telemetry after retry**. Invalid samples after a URI
  refresh do not prove that the address itself expired.

**This fixes the diagnostic exception in the manually edited installation and
improves attribution; it is not a confirmed fix for the cloud's unusable live
responses.** Warnings remain visible. Live acceptance, two-attempt recovery,
request bodies, account pacing, server pauses, polling and energy calculations
are unchanged. Missing samples are never converted into zero power or refreshed
using an old measurement.

The current S-Miles Home V2.14.0 battery request was checked statically and uses
the existing `{sid,m:0}` body. No speculative request flags or alternative
commands are introduced. See [the investigation](live-data-investigation.md)
for source hashes, evidence and remaining uncertainty.

## Install and test

1. In HACS, enable prerelease versions and select **v0.6.1b4**. If you edited
   `api.py` or `cloud_logging.py` manually, use HACS to download the complete
   version again so those files are replaced together.
2. Restart **Home Assistant Core**, not only the code-server add-on. Keep the
   existing integration, entities and dashboards; no password change or
   recreation of the integration is required.
3. Confirm that readings update normally. No warning is expected merely because
   Home Assistant restarted.
4. If the problem returns, share only fresh `hoymiles_home.cloud_logging`
   warning/recovery lines and whether the actual power entities became
   unavailable at the same time. The new fields include `object_state`,
   `dly_type`, `dly_state` and `recovery_scope`. No raw cloud capture or debug
   logging is needed. Do not share credentials, tokens, identifiers or HAR files.

`same_refresh` means that this live call returned a valid retry to the caller;
the earlier invalid sample alone did not fail that call. It does not prove that
every other request later in the coordinator update succeeded. `later_refresh`
identifies an episode extending beyond the current call's start.

For manual installation, download `hoymiles_home.zip` from
[this release](https://github.com/Phil-0805/hoymiles-home-assistant/releases/tag/v0.6.1b4),
back up the installed integration, extract into `custom_components/hoymiles_home`
and restart Home Assistant. The ZIP has `manifest.json` at its root. Restore the
backup or reinstall a previous release and restart to roll back.

## Included behavior and limits

Home's b2 TOU display/availability fix has now been reported working by the
issue #34 reporter; the maintainer separately confirms their own TOU test.
The reporter has not described a completed write. Reserve-SOC remains
intentionally unavailable in TOU; this is not a schedule editor.

Installer retains b3's **experimental, read-only monitoring** scope. Successful
Installer access is now reported in issue #16, while the requested app comparison
of measurements/energy totals is pending. Additional Installer charts and
storage controls were researched, but are **not enabled in this beta**. The
[capability review](installer-capability-review.md) records the separate float64
chart format and storage protocol; it is not a claim of feature parity.

Local validation: **936 HA tests on each of HA 2026.10.4 and 2026.11.0**,
**56 unit tests**, syntax, translation-key parity, documentation links,
whitespace and deterministic release-package checks. Required CI, HACS and
Hassfest gate publication. Tests use synthetic data. No real account/device
request or issue comment was made by the agent.
