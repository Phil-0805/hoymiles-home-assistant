# Independent station setup when live discovery has no URI

Prepared for v0.6.1b8, 2026-11-11. See the [release notes](release-0.6.1b8.md).

## Evidence and scope

The reporter in [issue #38](https://github.com/Phil-0805/hoymiles-home-assistant/issues/38)
reports the same initialization failure after rolling back to v0.6.0 and
restarting Core with the existing entry: both Home discovery routes return
successful status with an empty/null `uri`. This supports a preexisting setup
dependency, rather than a newly demonstrated b7 feature regression. The actual
reason the cloud omits its URI, including a possible nighttime/offline link,
remains unconfirmed. Station access and live-stream availability are separate.

Before b8, the setup first-refresh awaits `async_live` before loading the device
tree or station totals. Its failure therefore prevents all platforms from being
created, even when the account could still read the selected plant. The reporter
also confirms their earlier implementation had this dependency and may have
continued at night only because its live URI was already cached.

No new API route, device command or manufacturer timing is inferred. Existing
authentication, plant-list discovery, device tree and station totals readers are
reused. No real account/device was contacted during implementation or tests.

## B8 behavior

- Only a typed `CloudDiagnosticError(reason=missing_uri)` permits a partial
  refresh. The original mobile/web discovery and bounded attempt policy remain.
  Authentication, rate limits, blocked redirects, invalid URI types/hosts,
  invalid live telemetry, HTTP failures and generic connection errors retain
  their failure paths. A message merely containing `missing_uri` is insufficient.
- Before accepting partial startup, discover the account's plants afresh and
  require an exact positive integer match for the configured station ID. Do not
  select another plant, infer identity from a device or accept arbitrary JSON.
  This validation is cached only in this coordinator's memory and repeated after
  a reload/restart. It is not a substitute for authentication on later API calls.
- Load the device tree and use the existing independent station-totals schedule.
  Existing optional background readers retain their permissions, lifecycle and
  account budget. Station-total errors do not fabricate numbers; old totals
  expire with the existing timestamp/day/month/year rules. An inaccessible plant
  or failed device-tree request still fails setup.
- Expose `live_available=false` and an empty live payload while the URI is
  missing. Never reuse an old live sample as current or invent zero power,
  connection state, SOC or a battery activity state. Live-dependent station
  measurements and calculated-energy entities remain unavailable. The connected
  binary sensor is unavailable/unknown, rather than falsely reporting offline.
  Fresh independent chart/totals/settings data retain their own availability.
- Use the existing coordinator scheduler: while missing a URI, update once per
  minute and do not rediscover live earlier than one minute after the failed
  attempt finishes, including manual refreshes. This is a conservative local
  recovery policy, not a proven server quota or a darkness detector. No separate
  timer or sleeping setup task is added. Account pauses still apply.
- When discovery returns a URI and the client accepts an actual live sample,
  activate live telemetry on that refresh and restore the existing `dly`-based
  polling interval. Valid explicit offline samples (`con=0`) retain their
  existing semantics. Partial startup does not claim that an inverter is online.
- Reset energy integration samples on a missing-URI interval, so recovery never
  integrates across the gap. Preserve persisted daily counters and existing
  entity IDs/configuration. No write or automatic write retry is introduced.

## Tests and remaining validation

`tests/ha/test_setup_without_live_uri.py` uses the real API URI-discovery method,
real HA first-refresh/config-entry state, the actual setup function and mocked
cloud boundaries. Cases cover both profiles, exact station membership, live
sensor versus independent total availability, bounded retry/recovery, auth/rate
failure at each stage, other errors remaining fatal, valid offline samples,
discarding old samples, energy-gap handling, totals expiry and unload cancellation.

Existing tests continue covering successfully recovered b6 live requests and
terminal invalid live-data failures. A real test of cold start with the affected
inverter inactive, followed by automatic recovery when active, remains required.
This change addresses initialization resilience; it does not repair or explain
the cloud's missing URI.

Local checks passed: 1018 HA tests on each of 2026.10.4 and 2026.11.0,
56 unit tests, Python syntax, translation-key parity and git diff whitespace.
Publication is gated by the required PR and release checks.
