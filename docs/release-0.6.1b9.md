# v0.6.1b9 — HMS detection and timestamped measurements

This beta follows the b8 feedback in
[issue #38](https://github.com/Phil-0805/hoymiles-home-assistant/issues/38).
Stable remains **v0.6.0**. Installer remains experimental and read-only.

## Changes from b8

- Use the already discovered HMS model from matching `web_tree` or `micro_detail`
  metadata when selecting a standalone output-control target. Original device
  identity and topology remain authoritative; mismatches, conflicting models,
  unknown device types, multiple inverters and storage nodes retain their guards.
  This fixes the reproduced case where the displayed model was known but the
  target selector still saw only the original model-less tree.
- Reuse this corrected recognition to skip unnecessary battery mode/SOC and
  battery-temperature reads on the narrowly recognized inverter-only topology.
  Diagnostics now distinguish a configured reader (`enabled`) from whether it
  applies (`applicable`), and report whether standalone recognition succeeded.
- Read PV-input sample age from each metric's own aligned chart timestamp.
  Re-fetching the same old zero no longer renews its age. Sparse fields expire
  independently; unsupported/malformed axes remain unavailable instead of
  receiving an invented current timestamp. Local station dates/timezones and
  ambiguous DST times are checked. Future chart tails do not override older
  usable samples. Existing measurement precision is retained.
- Keep the normal inverter-temperature sensor unavailable after its sample
  expires. Add **Last inverter temperature / Letzte Wechselrichtertemperatur**
  as a separate diagnostic entity with the last value and `sample_time`.
  It has no statistics state class and adds no requests. HA suppresses ordinary
  extra attributes on unavailable sensors, so a separate entity makes the last
  sample inspectable. This cache is in memory; after a restart, a valid chart
  sample must be read before the diagnostic entity can show a value.
- Treat successful URI-discovery responses with no URI as deduplicated INFO
  events, with INFO recovery. B8's partial startup and bounded retry remain.
  Authentication, HTTP, redirect, rate, transport and invalid-data failures
  retain their warning/error behavior. No nighttime cause is assumed.

The broader review also tightens reserve-SOC inputs to whole percentages in
the existing 10–100 range, stops mode/SOC confirmation reads after unload or
permission withdrawal, rejects ambiguous legacy battery targets and malformed
command identities/status types, and preserves auth/rate failures through
legacy verification/fallbacks. Legacy errors no longer include a serial suffix.

## Controls and energy

Output settings remain independent of live production. Explicit control
permission, fresh phase information and maxima, target checks, one write and
full readback remain required. A failed read is not made successful by exposing
an indefinitely cached writable control. No default power maximum, new command
or automatic write retry is added.

Cloud PV daily/monthly/yearly/lifetime totals and local energy formulas remain
unchanged. B8's missing-sample gap handling remains. A genuine reported 0 W or
0 °C is still valid; no unproven zero-temperature sentinel is introduced.

## Upgrade and test

1. Install **v0.6.1b9** completely via HACS prereleases and restart HA Core.
   Keep the existing integration, entities and options.
2. Enable additional inverter telemetry to inspect temperatures and the new
   last-temperature diagnostic entity. Compare fresh readings with the app.
   Check `sample_time` before interpreting a retained diagnostic value.
3. On a standalone HMS, enable the control option naming battery mode, SOC and
   output power. Check whether the output setting and its reported maximum can
   now be read. For a deliberate permitted change, compare the app and restore
   the original setting; avoid simultaneous app edits.
4. If control remains unavailable, export fresh privacy-checked diagnostics.
   The original diagnostic did not expose the complete tree topology, so a
   different unsupported shape or another cloud error can still need inspection.
5. Confirm automatic live recovery when the inverter becomes active. When no
   current live sample exists, unavailable live power is intentional; an old
   chart/diagnostic value does not prove a live connection.

Real hardware confirmation of these follow-up changes remains outstanding.
If a fresh zero temperature looks wrong, provide its timestamp and a simultaneous
app comparison before treating zero as a missing-value code. Do not publish
credentials, serials, tokens or raw replies.

## Validation

**1097 HA tests on each of HA 2026.10.4 and 2026.11.0**, **56 unit tests**, Python
syntax, translation-key parity, whitespace and local HACS packaging checks
passed before release preparation. Real HA state-publication tests cover the
unavailable current sensor and the separate last-known temperature without a
statistics class. Required PR/release CI, HACS and Hassfest gate publication.
No real account/device requests were made by the agent.

See [the complete review and remaining limitations](issue-38-followup.md).
