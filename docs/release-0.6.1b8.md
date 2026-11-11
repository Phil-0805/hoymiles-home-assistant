# v0.6.1b8 — station setup without a live server address

This beta addresses the initialization failure reported in
[issue #38](https://github.com/Phil-0805/hoymiles-home-assistant/issues/38): both
live discovery routes returned a successful response with an empty URI. The
reporter reproduced this with v0.6.0 as well as b7. The cloud-side reason,
including any relationship to nighttime/inverter inactivity, is not confirmed.
Stable remains **v0.6.0**. Installer remains experimental and read-only.

## Changes from b7

- Allow setup to complete when the specific live error is `missing_uri`, after
  independently confirming the selected station in the account's freshly read
  plant list and loading its device tree. Available station totals and existing
  independent background readers can load without a live-stream address.
- Keep live power, SOC, status and locally calculated energy entities unavailable
  until an actual live sample arrives. Missing URI does not imply zero power or
  a confirmed offline connection state. No cached live sample is presented as new.
- Retry live discovery through the existing coordinator scheduler, no earlier
  than one minute after the failed discovery finishes. Successful recovery
  enables live telemetry and restores normal server-delay-based polling without
  re-adding or restarting the integration. No separate timer or setup wait is added.
- Keep authentication, rate limits, HTTP/transport errors, unsafe addresses and
  invalid live telemetry on their existing error paths. Only the typed
  `missing_uri` condition permits partial startup; an inaccessible station or
  failed device-tree request still prevents setup.
- Export a fixed `live_available` diagnostic flag, without raw cloud data or
  private identifiers. Existing entity IDs, settings, control permissions,
  Home/Installer separation and account pacing remain in place.

## Energy totals

Daily, monthly, yearly and lifetime **PV yields are read from the cloud** using
the existing independent station endpoint and freshness rules. They do not
depend on integrating HA live-power samples. Missing/stale cloud totals remain
unknown/unavailable rather than becoming zero.

The separate **locally calculated house-consumption and battery charge/discharge
energies** require live measurements. Already accumulated daily counters are
preserved, but a measurement gap cannot be reconstructed and may leave those
local totals incomplete. Integration samples are reset across the gap so no
energy is invented between the last old and first new reading.

## Test and upgrade

1. Download **v0.6.1b8** completely through HACS prereleases and restart Home
   Assistant Core. Keep the existing entry, entities and options.
2. While the live URI is unavailable, verify that setup completes and check the
   available station totals. Live-dependent entities and connection state can
   remain unavailable; this does not prove the inverter is offline.
3. When the official app/device becomes active, check that live values return
   automatically. Discovery is retried at the reduced interval while waiting.
4. Compare PV totals with the official app. If setup still fails, report the
   installed version and fresh sanitized errors. Do not publish credentials,
   tokens, device identifiers or raw API responses.

The b7 standalone-HMS telemetry/output changes are retained. This beta fixes
startup resilience, not the cloud's omission of a URI. Hardware confirmation of
inactive-device cold start and later recovery is still outstanding.

## Validation

**1018 HA tests on each of HA 2026.10.4 and 2026.11.0**, **56 unit tests**, Python
syntax, translation-key parity and whitespace checks passed locally. The 26 new
cases cover real HA first refresh and setup, both profiles, exact station
membership, entity availability, bounded retry/recovery, fatal auth/rate/other
errors, offline samples, energy gaps, totals expiry and unload cancellation.
Required CI, HACS and Hassfest gate publication; the HACS ZIP is checked locally
and against the actual published asset. No real account/device was contacted.

See [the implementation scope and evidence](setup-without-live-uri.md).
