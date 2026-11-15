# v0.6.2b3 — optional sampled history

This beta addresses [issue #51](https://github.com/Phil-0805/hoymiles-home-assistant/issues/51)
with optional history copies while keeping existing live sensors responsive.
Stable remains **v0.6.1**.

## Changes from b2

- Add **History sampling** in Configure for Home, Installer and Enduser profiles:
  Off (default), 10, 15, 30 or 60 seconds. Existing setups can enable it directly.
- Add nine station history copies: six power measurements and three daily
  household/battery charge/battery discharge energy counters. Existing live
  identities, automations, full-rate energy integration and cloud polling remain.
- Preserve source availability and real zero/signed power values. Ordinary
  publications use the next source update after the minimum interval; values
  are snapshots, not averages. Brief power peaks can be absent from history.
- Publish observed daily-energy tails before station-local midnight, including
  when the final cloud update is missing. Flush pending same-day energy on normal
  reload/shutdown and retain a saved same-day guard against counter rollback.
  An abrupt crash cannot guarantee the latest unsaved counter.
- Retain b1's six-input HMT monitoring and b2's direct Home login fix.
  Thanks to @Max7730 for confirming b2 works on the affected setup in #54.

**History copies alone do not reduce database writes.** Users must exclude the
corresponding live originals in their Recorder configuration and use history
copies for historical charts. Keeping both recorded adds rows. Excluded originals
remain live but stop accumulating new Recorder history/statistics. Existing data
is not migrated or deleted, and Energy dashboard sources are not changed.

Changing intervals preserves identities. Off unloads copies without deleting
registry entries or data. Availability transitions, initialization and the final
energy sampling window before midnight can add rows beyond ordinary sampling.
No automatic retention policy, purge, extra cloud requests or device writes.

## Beta test for existing installations

1. Install **v0.6.2b3** through HACS with beta versions enabled, then restart Core.
   Keep the existing integration entry.
2. Open **Settings → Devices & services → Hoymiles → Configure** and select
   **30 seconds** for History sampling. Check the new `(history)` sensors.
3. Initially keep originals and copies recorded for a 24-hour comparison,
   including midnight and a reload. This temporarily adds database rows.
4. Compare live responsiveness and daily energy totals. Then add targeted
   Recorder exclusions for the desired originals, preserving existing filters,
   and restart Core after YAML changes. Use copies for historical graphs.
5. Compare an equivalent subsequent 24-hour window. Share aggregate row counts
   and any energy mismatch; do not upload private databases or credentials.

[Setup guide, Recorder examples and optional separate retention automation](https://github.com/Phil-0805/hoymiles-home-assistant/blob/v0.6.2b3/docs/history-sampling-usage.md).

## Validation

Local validation: **1,297 HA tests on each of HA 2026.10.4 and 2026.11.0**, plus
**56 unit tests**, Python syntax, translation-key parity and whitespace checks.
The suite includes 30 history tests, real synthetic Recorder databases with and
without exclusions, and real statistics compilation across midnight with and
without final source updates. It covers all intervals/profiles, DST, availability,
reload/restoration, listener cleanup and unchanged client-call counts.

Required CI covers both supported HA versions, HACS and Hassfest. The existing
pytest anyio assertion-rewrite warning is unchanged. No real accounts, devices or
user databases were accessed. Installation-specific 24-hour savings and energy
comparisons still need beta feedback; row counts do not measure disk bytes.
