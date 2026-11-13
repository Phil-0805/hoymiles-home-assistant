# v0.6.1b10 — standalone HMS and daylight telemetry follow-up

This beta follows the b9 daylight/rollback reports in
[issue #38](https://github.com/Phil-0805/hoymiles-home-assistant/issues/38).
Stable remains **v0.6.0**. Installer remains experimental and read-only.

## Changes from b9

- Correct standalone recognition for the Home app's **type-1 DTU** and nested
  **`devices`** representation, alongside the existing supported tree layout.
  Previously these could block recognition despite an identified HMS model.
  One explicit HMS, validated identities/provenance, no storage, no unknown
  devices and no duplicates remain required. The same recognition skips battery
  readers on the supported inverter-only layout.
- Accept unambiguous **H:MM** chart labels and an ending **24:00** boundary without
  discarding earlier aligned samples. The boundary itself is never treated as a
  current measurement. Align chart selection with the existing one-minute clock
  tolerance; the ten-minute sample lifetime remains unchanged. This fixes
  reproduced parser/cutoff defects, not a proven complete explanation of every
  b9 telemetry failure: the supplied diagnostics do not contain the actual axes.
- Keep an explicitly reported **0 W** PV value available with an offline flag.
  The station still needs a valid Live sample; each input still needs a fresh
  explicit chart zero. Missing, malformed or stale data is not replaced by zero.
- Keep the **last confirmed output setting** visible overnight or after a failed
  settings read while its original target and permissions remain valid and the
  coordinator remains available. Attributes distinguish `current` from
  `last_confirmed` and expose `last_confirmed_at`. This is an in-memory snapshot;
  reload/restart requires a new successful read. Every change still performs a
  locked fresh read, fresh-limit validation, a single write and complete readback.
  A retained value/range never authorizes a write by itself.
- Remove the separate **Last inverter temperature** diagnostic entity. Cleanup
  targets only its exact owned registry identities, including renamed/disabled
  entries. The normal temperature sensor, battery sensors and devices remain.
  The normal temperature sensor continues to become unavailable when stale.
- Add fixed standalone-rejection/decoder reasons and per-field age/status to
  diagnostics. This distinguishes a successful request from usable fresh data
  without exporting raw responses, chart labels, serials, IDs or exception text.

No new API command, endpoint, faster poll, write retry, guessed power maximum or
energy-calculation change is introduced. Rated inverter power is not proof of a
confirmed setting or an allowed write range. B8's partial startup and automatic
Live recovery are retained.

## Upgrade and test

1. Install **v0.6.1b10** completely via HACS prereleases and restart HA Core.
   Keep the existing integration and options; do not delete/re-add the entry.
2. With additional inverter telemetry enabled, wait for the normal five-minute
   chart interval during production. Check power, voltage and current for all
   four inputs, plus normal inverter temperature against the app.
3. On a standalone HMS, check `standalone_hms_recognized` and
   `standalone_hms_reason`, `battery_telemetry.applicable`, and whether output
   settings can be read. A recognized tree does not guarantee API support.
4. If output was successfully read before night, check that its confirmed value
   stays visible with its confirmation time. If deliberately testing a permitted
   change, compare readback with the app and restore the original setting.
5. If inputs/temperature remain unavailable, export fresh privacy-checked
   diagnostics during production. The new inverter `telemetry` section reports
   read outcomes and field ages. Do not publish raw charts, credentials, tokens,
   serials or unredacted screenshots.

No current measurement means unavailable; neither an offline flag nor an old
temperature proves a current physical value. The separate last-temperature
entity is intentionally removed. Existing automations referencing it need
adjustment; the normal sensor's identity is unchanged.

## Validation and limits

The runtime changes passed **1203 HA tests plus 134 subtests on each of
HA 2026.10.4 and 2026.11.0**, and **56 unit tests** locally. Checks cover real
API-to-poller decoding, HA zero-state publication, source-backed Home topology,
field expiry, retained output/preflight guards and exact registry removal.
Syntax, translation keys, whitespace, review links and the 38-file HACS package
were checked. Required PR/release CI, HACS and Hassfest gate publication.

No real account or device requests were made by the agent. The reporter's
specific tree/chart variants and the effectiveness of these corrections still
need hardware confirmation. See the [investigation and source hashes](b9-daylight-investigation.md).
