# v0.6.1b5 — respect live-server waiting replies

**Prerelease for device testing. Latest stable remains v0.6.0.**

B4 diagnostics showed repeated live replies containing an integer `dly` field
but no flow, connection or power fields, followed by successful recovery inside
the same refresh. The previous client discarded the URI, looked it up again and
retried without using that delay. The current manufacturer web client instead
schedules another read of the same URI independently of whether new measurements
were returned.

B5 implements that waiting path. This targets the observed warning/recovery
pairs; it does not claim to repair the cloud service or every telemetry outage.
See [the evidence and implementation](live-data-investigation.md).

## What changes

- Recognize a waiting reply only after successful response handling, with an
  explicit nonnegative integer `dly` and absent `flow`, `con` and `power` fields.
  Malformed or conflicting telemetry is not silently reclassified as waiting.
- Keep the validated live URI and the existing request body. Wait outside
  HTTP/account locks, using at least the server delay and the existing
  three-second local minimum. A zero delay uses this minimum to avoid a loop.
- Keep at most two live reads per update. Wait up to 30 seconds inline; a longer
  delay or another waiting reply defers the read through HA. The complete
  per-client monotonic deadline is retained even when scheduler wake-ups are
  capped at one day. This is not an account-wide rate-limit pause.
- Preserve longer waits across initial setup retries and integration reloads
  within the same HA process, bound to the entry/account/profile/station.
  A full HA process restart does not persist this in-memory deadline.
- Cancel active and queued live reads when unloading. A changed target cannot
  inherit an old reply or resume a read against the old live URI.

A recognized waiting reply no longer creates the misleading
`invalid_live_data` warning/recovery pair. Genuine malformed replies, failed
authentication, rate limits and transport errors remain visible.

Waiting replies are **not measurements**. Deferred updates remain unavailable
under the existing HA error behavior, and energy samples are reset across a
failed update. No zero power or freshly timestamped old measurement is invented.
A short wait followed by a valid sample returns that sample normally.

No device-write operation, login/profile fallback, request flag or faster polling
is added. Installer retains its experimental, read-only monitoring scope; this
release does not add Installer charts or storage controls.

## Install and test

1. Enable prerelease versions in HACS and install **v0.6.1b5**. Download the
   complete version again if you previously edited integration files manually.
2. Restart **Home Assistant Core**. Keep the existing integration, entities,
   options and dashboards; do not delete/recreate the entry or change passwords.
3. Check that measurements continue to update and compare them with the official
   app. Observe whether the previous warning/recovery pairs recur and whether
   actual power entities become unavailable.
4. If waiting persists, HA may report **Live data is not ready; a later read is
   scheduled**. That reports missing telemetry and a deferred read, not an
   authentication failure or a proven rate limit. Report its timing and the
   corresponding app behavior separately from malformed-data warnings.

For failures, share only fresh fixed warning/recovery lines and the affected
entity behavior. B4's structural diagnostic fields remain available for malformed
responses. No debug logging, raw cloud capture, credentials, tokens, device
identifiers or HAR files are needed. An absence of warnings alone does not prove
new measurements are arriving; check the entities as well.

For manual installation, download `hoymiles_home.zip` from
[this release](https://github.com/Phil-0805/hoymiles-home-assistant/releases/tag/v0.6.1b5),
back up the installed integration, extract into `custom_components/hoymiles_home`
and restart HA. The archive has `manifest.json` at its root. Restore the backup
or reinstall b4 and restart to roll back.

## Validation

**985 HA tests on each of HA 2026.10.4 and 2026.11.0**, **56 unit tests**,
syntax, translation-key parity, documentation links, whitespace and the
deterministic 37-file HACS ZIP including LICENSE. The 49 additional HA tests cover
wait timing, exact bodies, no URI churn, bounded retries, long deadlines, target
changes, unload/cancellation, real HA setup/reload handling, availability and
energy resets. Required CI, HACS and Hassfest gate publication.

Tests use synthetic replies. No real account/device request or issue comment
was made by the agent. Confirmation on the maintainer's installation is pending.
