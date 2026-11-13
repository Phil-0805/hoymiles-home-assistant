# v0.6.1b11 — stable chart availability between polls

This beta corrects the availability regression reproduced on b10: PV-input and
inverter detail values could disappear between successful five-minute reads,
then return at the next normal poll. Stable remains **v0.6.0**; Installer
remains experimental and read-only.

## Changes from b10

- Separate the original chart sample time from the last observed **progress**
  of each metric. A newer sample timestamp, or a changed finite value in the
  same time bucket, counts as progress. Repeated identical replies do not.
- Keep delayed but advancing chart measurements usable between normal polls.
  The reproduced sequence of sample ages **491 → 641 → 492 seconds** now stays
  available through real HA state publication, without making additional reads.
- Bound availability by source age **under 20 minutes** and time without
  progress **under 10 minutes**, retaining the existing one-minute clock-lead
  tolerance. These are client policies, not manufacturer API limits or a
  guarantee of physical real-time data. Frozen series, old startup samples,
  missing/nonfinite data, earlier replacements and failed reads cannot keep an
  old value fresh indefinitely. Genuine zero remains a valid value.
- Retain each original source timestamp. Acquisition/progress time does not
  replace `sample_time`, and one metric cannot refresh another metric's age.
  Diagnostics add bounded `progress_age_seconds` and the two policy bounds.
- Make aggregate `details_status` follow current field usability. It no longer
  stays `readable` after every detail field expires between polls.
- Publish module values and their source/progress clocks together, including
  partial success on timeout, so concurrent Live updates cannot attach new
  metadata to old published values.

The five-minute chart interval, station Live transport, account request pacing,
server pauses, settings controls and energy formulas remain unchanged. No new
endpoint, faster poll, command, write retry or standalone last-temperature
entity is added. B10's recognition, explicit offline-zero handling, retained
output display and exact obsolete-entity cleanup remain included.

## Earlier-version and manufacturer comparison

The published **v0.6.0** PV read, value selection and sensor availability code
was directly compared with b8 and is identical in the relevant paths. Both
already polled charts every five minutes, but dated PV freshness from successful
receipt. B9 switched those inputs to source-time expiry. Temperature/frequency/
AC voltage already used source-time expiry in v0.6.0; they are not all new b9
checks.

The pinned Home APK and current public web client were also inspected. Historical
charts and momentary per-input live power have different code paths. The examined
chart renderers do not establish HA's ten-minute entity expiry or an account-wide
request quota. Their distinct per-input live routes are not substituted for HA's
station Live request in this correction. See the [source comparison, hashes and
limitations](chart-progress-freshness.md).

## Upgrade and test

1. Install **v0.6.1b11** completely through HACS prereleases and restart HA Core.
   Keep the existing integration, settings and entity identities.
2. During production, allow the normal five-minute chart cycle to complete.
   Observe populated PV inputs and temperature/frequency/AC voltage over several
   cycles, including the period between reads when values previously disappeared.
3. Compare timestamps and values with the app. These remain cloud chart
   measurements; b11 does not make them seconds-current like station Live.
4. If values still disappear, export privacy-checked diagnostics while unavailable
   and after recovery. Compare `age_seconds`, `progress_age_seconds`, field status
   and read outcomes. Do not publish credentials, identifiers, raw replies or
   unredacted screenshots.

An unoccupied input with a non-advancing chart remains a separate case. No port
is globally assumed unused, and missing/stale values are not manufactured as
zero. No ongoing old measurement is presented by a separate last-temperature
entity.

## Validation

The final runtime changes passed **1213 HA tests plus 134 subtests on each of
HA 2026.10.4 and 2026.11.0**, plus **56 unit tests**, locally. Tests cover the
reported delayed-chart cycle in HA, unchanged request counts, zero/nonzero
stagnation, independent clocks, invalid replacements, failed reads, dynamic
aggregate status, concurrent batch publication, target pruning and shutdown.
Syntax, translation-key parity, documentation links, whitespace and the
38-file HACS package were checked. Required PR/release CI, HACS and Hassfest
gate publication. No actual account/device requests were made by the agent.

The reported failure is reproduced and corrected in tests. Confirmation on the
maintainer's and reporter's hardware is still required.
