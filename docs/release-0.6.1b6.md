# v0.6.1b6 — restore live recovery after the b5 regression

**Prerelease for testing. Latest stable remains v0.6.0.**

B5 introduced a regression on the maintainer's installation: its scheduled-wait
handling produced **Live data is not ready; a later read is scheduled** and
persistent unavailable live entities. B6 removes that waiting policy and restores
the bounded URI recovery that previously returned valid data with b4.

This repairs the integration behavior introduced in b5. It does not claim to
repair the cloud service or guarantee that every interruption disappears.

## What changes

- Restore b4's live read path: when the initial reply contains no usable
  telemetry, clear the cached live URI, obtain it again and retry once under
  the existing shared account budget. Request bodies and the two-live-attempt
  cap are unchanged.
- Remove b5's inline delay, pending deadline, setup/reload waiting cache and
  special scheduled-wait failure path. The returned `dly` in a reduced reply
  is no longer treated as a mandatory Retry-After for the Home recovery path.
- For the specifically observed first reply (integer `dly`, no `flow`, `con`
  or `power`), hold the warning decision until the existing recovery finishes.
  If the retry returns valid telemetry, record only the fixed info message
  **Cloud live retry recovered: stage=live_data first_sample=delay_without_telemetry**.
  The coordinator returns that actual sample and the live update stays successful.
- If recovery still returns no usable telemetry, the normal warning/failure
  path remains and the update is unavailable. Other malformed replies, URI,
  authentication, HTTP, rate-limit and transport failures retain their existing
  handling. A genuine earlier failed-refresh episode still reports recovery.

No old measurement is presented as fresh, no zero power is invented, and no
new sleep/timer, login fallback or device write is introduced. Existing account
pacing, server pauses and TLS/redirect limits remain in place. Valid offline
responses remain accepted as before. Diagnostics
retain fixed structural labels without raw payloads, delay values, credentials,
tokens, URLs or device identifiers. Installer scope is unchanged.

## Upgrade from b5 and test

1. In HACS, enable prereleases and download **v0.6.1b6** completely. Use
   **Redownload** if integration files were edited manually.
2. Restart **Home Assistant Core**, not only an add-on. Keep the existing
   integration, entities, options and dashboards; no password change or
   recreation is required. Restarting also discards b5's in-memory waits.
3. Confirm that live solar, house, grid and battery entities update again.
   Compare readings with the official app. Normal successful internal retries
   no longer produce the old warning/recovery pair for the observed delay hint.
4. If values stay unavailable, report the fresh error lines and whether the
   official app is updating. A lack of warnings alone is not proof of new
   measurements. No debug logging or raw cloud capture is required; omit
   credentials, tokens, identifiers and HAR files.

For manual installation, download `hoymiles_home.zip` from
[this release](https://github.com/Phil-0805/hoymiles-home-assistant/releases/tag/v0.6.1b6),
back up the installed integration, extract into `custom_components/hoymiles_home`
and restart HA. `manifest.json` is at the ZIP root. For rollback use **b4** or
your pre-b5 backup and restart; b5 is the version with the reported regression.

## Validation and limits

**956 HA tests on each of HA 2026.10.4 and 2026.11.0**, **56 unit tests**,
syntax, translation-key parity, documentation links, whitespace and the
deterministic 37-file HACS ZIP including LICENSE. Required CI, HACS and Hassfest
gate publication.

The 20 real-coordinator/API regression cases cover successful URI recovery and
availability after zero/short/long delay hints, recurring replies without stuck
deadlines, genuine missing telemetry after both attempts, retained warnings for
other malformed replies and recovery after a real earlier failure. B5-only tests
that accepted the new unavailable waiting policy are removed with that feature.

The exact delay value and cloud-side reason for the maintainer's reduced replies
remain unknown. Manufacturer web polling was insufficient evidence to change
the Home recovery policy safely. The protocol evidence and regression analysis
are in [the live-data investigation](live-data-investigation.md).

Tests use synthetic data. B6 still needs confirmation on the maintainer's
installation. No real account/device request or issue comment was made by the
agent. Historical tags and releases are unchanged.
