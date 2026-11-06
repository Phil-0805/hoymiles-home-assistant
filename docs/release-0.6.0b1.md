# v0.6.0b1 — settings recovery and code cleanup

The changes developed during the v0.5.2 beta series will ship as **v0.6.0**
because of their scope. This prerelease replaces the planned v0.5.2b10;
the latest stable remains v0.5.1. MQTT research is planned for v0.7.0.

## Changes since v0.5.2b9

- Failed settings reads can recover automatically on the existing update tick:
  at most two additional attempts, one minute and then three minutes after the
  preceding failure completes. Successful features are kept and are not read
  again just because another feature failed. After the retry limit, the normal
  30-minute schedule applies.
- Authentication errors, rate limits, rejected redirects, HTTP 4xx responses and
  structurally invalid settings do not receive accelerated retries. Existing
  account pacing, server pauses and command-status polling remain unchanged.
  Writes are never automatically resent.
- Settings logs identify the feature and read/write/status stage using fixed,
  privacy-preserving labels. The reported startup rejection has no confirmed
  cloud-side cause; these changes do not establish a rate limit as its cause.
- Remove the obsolete **Maximum power setting (raw)** diagnostic sensor.
  The configurable output-power entity remains. Only the exact obsolete sensor
  owned by this configuration entry is removed, including renamed or disabled
  instances. Dashboards or automations referencing it need manual adjustment;
  the raw field is not treated as equivalent to the output-power control.
- Consolidate settings-state updates, permission checks, registry cleanup and
  request-stage classification without intended behavior changes.

## Included from the earlier betas

Account-selected authentication servers, bounded authentication redirects,
server-selected login protocol versions, a web-route fallback for missing live
server addresses, automatic battery temperatures, separate charge/discharge
cutoffs, heating permission, light/display settings including **Never** timers,
and output-power controls with freshly read limits are included.

Issue #16 reporters have confirmed successful login. Reports also confirm
matching readings on their setups; this does not establish compatibility with
every device or firmware. One reporter separately reports stale values in both
the official app and Home Assistant; its cause remains unconfirmed.

Special thanks to @gillesBdl for his patience, repeated beta testing and detailed
troubleshooting feedback during the login investigation.

## Testing and remaining checks

1. Install **v0.6.0b1** through HACS and restart Home Assistant. Existing entries
   can be retained; deleting and recreating them is unnecessary.
2. Check login, live readings and settings after startup. A transient settings
   failure may take several minutes to recover automatically. Invalid settings
   or authentication failures intentionally do not use the faster read retries.
3. Check dashboards after removal of the raw diagnostic sensor. Keep control
   permissions enabled only for features you intend to use.
4. If a problem remains, share only the fixed `hoymiles_home.cloud_logging`
   warnings and the affected entity. Do not share credentials, tokens, device
   identifiers, complete URLs or raw responses.

The new recovery schedule and cleanup still need startup testing on real setups.
Source-backed settings readback does not prove physical output behavior across
all hardware; output-power device validation remains limited. Stable v0.6.0
depends on the remaining checks, rather than a fixed release time.

Local validation: **740 Home Assistant tests and 35 unit tests**,
plus Python syntax, translation-key parity and whitespace checks. Publication
requires CI on HA 2026.10.4 and 2026.11.0, HACS and Hassfest. The release includes
the HACS ZIP package and LICENSE. No real account or device was accessed by the
agent for these changes.

See [API timing](api-request-timing.md), [device settings](device-settings.md)
and [output-power protocol details](output-power-settings.md).
