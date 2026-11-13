# v0.6.1 — recovery, standalone HMS support and experimental account profiles

**v0.6.1 brings the final v0.6.1b14 runtime to Stable**, including the fixes
tested throughout the beta series. Existing Home installations can update
without recreating their integration. Installer and Enduser remain explicitly
**experimental and read only** within this stable integration release.

## Home login and automatic recovery

- Use the Home account's region discovery before pre-inspection, then follow
  the explicit challenge protocol and authentication routing. Treat expired
  sessions distinctly from invalid data. Do not try alternative profiles or
  password algorithms after an arbitrary rejection.
- Permit partial startup when no Live server address is available, after
  independent station-access validation. Retry under the existing account
  request budget and recover automatically when usable Live telemetry returns.
- Restore bounded Live URI refresh/retry and report successful recovery without
  the misleading warning pair for the observed delay-only first response.

## Standalone HMS and chart telemetry

- Correct Home DTU/device nesting and use matching, verified model metadata for
  standalone HMS recognition. Avoid battery readers on a positively identified
  standalone installation rather than treating missing storage as a failure.
- Correct chart time-axis handling and preserve each metric's original sample
  time. Distinguish source age from observed progress so delayed but advancing
  data remains usable between normal five-minute chart polls.
- Expire fields when source age reaches 20 minutes or no progress has been
  observed for 10 minutes, retaining the existing one-minute clock-lead tolerance.
  These are client freshness policies, not manufacturer quotas or a promise of
  seconds-current chart readings. Repeated identical replies do not renew them.
- Keep explicit valid zero power readings. Missing or stale measurements remain
  unavailable; a nighttime outage does not automatically manufacture zero.
- Keep the normal inverter temperature sensor subject to freshness checks.
  Remove the separate **Last inverter temperature** diagnostic entity through
  targeted cleanup of this integration entry's obsolete entity only.

A standalone HMS-2000-4WB tester confirmed daytime readings, overnight behaviour,
retention of the 2000 W output setting and automatic recovery after sunrise.
This validates that installation, not every device or firmware.

## Settings and output display

- Separate readable self-consumption/TOU mode from safe write capabilities.
  Display an explicitly returned mode even when incomplete SOC/plan data prevents
  changing it. Permit activation of a complete, supported existing basic plan,
  including the app's explicit custom-plan ID 0.
- TOU schedules are still configured in the official app. This is not a schedule
  editor; reserve SOC remains unavailable in TOU, whose thresholds belong to its
  plan. Missing or conflicting plan data blocks writing.
- Retain the last confirmed output-power setting during an overnight read
  failure while permission and the original target remain valid. Mark it as
  last confirmed rather than current. This retention is in memory only: after
  restarting HA, another successful cloud read is required.
- All writes still require permission, a fresh locked read, validated target and
  limits, one write and readback confirmation. A displayed setting is not proof
  of physical output; it does not override a lower reported write maximum.

## Installer and Enduser profiles — experimental

Choose the profile matching the **exact official app**, not merely whether you
own the plant. Each profile has separate token/DC state while sharing account
pacing, server pauses and the login lock. No automatic profile fallback is used.

| Profile | Supported scope |
| --- | --- |
| S-Miles Home | Existing supported Home monitoring and optional controls |
| S-Miles Installer | Station live readings, cloud energy totals and basic device identity/model; read only |
| S-Miles Enduser | Station PV/storage Live schemas and explicitly returned standard generation totals; read only |

Enduser validates authenticated metadata for the exact selected station and a
supported classification. Station monitoring does not depend on the optional
device tree. Known integer-string and JSON-text representations are accepted
within strict limits; invalid identities are not guessed. Nonzero directional
readings require unambiguous reported flow directions.

Installer account access and Enduser authentication, plant discovery and setup
have been confirmed by reporters. **Several entities remain unavailable on the
reported HIS-6L-G3 Enduser installation, and their cause is still under
investigation.** Full measurement coverage, directions and energy comparison
are not established for that installation. Missing values stay unavailable.
Home controls, module charts and additional inverter detail telemetry are not
enabled for either experimental profile. Existing stored permissions cannot
unlock those operations.

## Upgrade

1. Install **v0.6.1** through HACS/Marketplace and restart **Home Assistant Core**.
   Keep existing config entries, entity identities, options and dashboards.
2. Beta users can move directly to Stable and disable prereleases if desired.
   Existing working Home entries need no account-profile change.
3. Update any dashboards or automations referencing the removed **Last inverter
   temperature** diagnostic entity. The normal temperature sensor remains.
4. If updating from before v0.6.0, also review the
   [earlier migration notes](release-0.6.0.md#upgrade-notes--please-read).

## Limits, diagnostics and future work

Live reads follow the server interval with a minimum of three seconds; station
totals are requested about once per minute. Home chart/battery-temperature reads
remain about every five minutes. Cloud outages, missing fields and unsupported
features can leave entities unavailable without an authentication error.
Share affected entity names and privacy-checked diagnostics when reporting that
case. Fixed `stage`/`reason` logs contain no raw responses or account/device IDs.
Locally integrated energy may have gaps during outages and is not a billing meter.

Optional history sampling is planned for **v0.6.2** in
[issue #51](https://github.com/Phil-0805/hoymiles-home-assistant/issues/51); no such
option is included here. MQTT research remains separate for
[v0.7.0](roadmap-0.7.md). Public-client inspection and synthetic tests establish
protocol evidence, not universal hardware compatibility.

## Validation and thanks

The final runtime passed **1323 HA tests plus 134 subtests** on HA 2026.11.0 and
**56 unit tests** locally. PR/release CI tests HA **2026.10.4 and 2026.11.0**, HACS
and Hassfest. Syntax, translation-key parity, documentation links, whitespace,
the release package and runtime equivalence with b14 are checked. The HA test
matrix names tested versions, not a minimum supported version. No actual account
or device was accessed by the agent for release preparation.

Thanks to **@flo1990m** for the detailed standalone HMS day/night/sunrise tests,
**@jacksontploong** for the Enduser setup tests and precise logs, **@rupacheco**
for Installer feedback, and everyone who tested the betas and compared readings
with the official app.

[English README](../README.md) · [Deutsche README](../README.de.md) ·
[Account timing](api-request-timing.md) · [Chart freshness](chart-progress-freshness.md) ·
[Installer protocol](installer-app-protocol.md) · [Enduser protocol](enduser-app-protocol.md)
