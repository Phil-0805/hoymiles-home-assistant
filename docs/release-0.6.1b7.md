# v0.6.1b7 — standalone HMS compatibility

This beta addresses [issue #38](https://github.com/Phil-0805/hoymiles-home-assistant/issues/38)
for the **Home** profile, while retaining b6's live recovery. Stable remains
**v0.6.0**. Installer remains experimental and read-only.

## Changes from b6

- Permit the existing output-power control on an explicitly recognized single
  HMS inverter with optional DTU nodes and no battery/unknown device types.
  A unique AC battery controller is no longer required for that narrow topology.
  The existing output-control permission must be enabled. Fresh phase selection,
  returned limits, preflight checks, one write and full readback remain required.
  Missing phase evidence or limits still disables the control; no guessed 2000 W
  maximum is introduced. Mixed/ambiguous/unrecognized trees remain conservative.
- Supplement missing or stale inverter temperature, AC voltage and frequency
  with the Home app's timestamped microinverter chart. Enable **Additional
  inverter telemetry** in integration options. A successful snapshot response
  with missing/stale metrics can add one batch read per existing five-minute
  poll; working fresh metrics need no extra request. Failed snapshot requests
  do not trigger a fallback. Chart timestamps determine freshness, not request
  time. No old sample is presented as new and no missing value becomes zero.
- Skip mode/SOC and battery-temperature reads on the same recognized inverter-only
  topology, including manual mode/SOC refreshes. Unknown trees retain existing
  behavior. This avoids unnecessary requests without claiming the previous
  generic cloud rejection proves a specific cause.
- Report extra telemetry as readable only when at least one metric has a fresh
  sample. Individual sensor availability remains independent per metric.

No live polling/retry policy, module-input chart, entity ID, energy calculation,
Home battery command or Installer capability is changed. B6's limited INFO-only
handling of a successfully recovered first `dly` reply remains; genuine failures
still warn. Stable v0.6.1 has not been published.

## Install and compare with the app

1. Install **v0.6.1b7** fully through HACS prereleases and restart HA Core.
   Keep the existing integration and entities. If files were edited manually,
   use HACS Redownload to restore a consistent package.
2. For HMS telemetry, enable the extra-inverter-telemetry option, allow one slow
   poll and compare temperature/voltage/frequency with the official Home app.
   Chart measurements can lag; unavailable stale values are intentional.
3. To test output control, enable the option naming battery mode, SOC and output
   power. Check the reported current value and maximum first. Only make a
   deliberate permitted change, compare the corresponding app setting and
   restore the original value. Avoid simultaneous app edits. Cloud readback
   confirms the stored setting, not physical output under every condition.
4. If output still reports `no_unique_target` or telemetry remains unavailable,
   attach freshly exported, privacy-checked diagnostics and the installed
   version. A different tree layout needs inspection; do not delete/recreate the
   integration or publish tokens, serials, raw replies or private captures.

The reporter's installation has not yet tested b7. The earlier custom-integration
success is user-reported evidence, not a cross-firmware support guarantee.
See [the claim-by-claim review and protocol evidence](standalone-hms-issue-38.md).

## Validation

**992 HA tests on each of HA 2026.10.4 and 2026.11.0**, **56 unit tests**,
Python syntax, translation-key parity, changed documentation links, whitespace
and the deterministic **38-file HACS ZIP** including LICENSE passed locally.

Synthetic tests cover exact chart transport, timestamp alignment/expiry,
ambiguous/foreign identities, narrow tree recognition, omitted battery reads,
fresh output limits, target/permission/unload changes and full readback without
repeating writes. Existing tests cover Home and Installer isolation, exact
station output transport, phases, other controls and live regression recovery.
Local HA tests, unit tests, syntax, translation parity, whitespace and the
deterministic HACS package are checked before release; CI, HACS and Hassfest
gate publication. No real account/device call was made by the agent.
