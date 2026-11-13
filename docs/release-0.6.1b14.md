# v0.6.1b14 — Enduser station monitoring without a device-tree dependency

This beta removes an unnecessary startup dependency from the experimental,
read-only Enduser profile. Stable remains **v0.6.0**.

## Changes from b13

- Validate Enduser setup through authenticated station metadata, requiring the
  exact requested station ID and a supported station classification.
- Do not request a device tree during Enduser setup or station monitoring.
  The existing Enduser scope uses station-addressed Live and energy requests;
  it does not expose device-specific entities or controls that need that tree.
- Apply the same exact station validation when the initial Live server address
  is missing. Preserve the existing retry cooldown and automatic Live recovery;
  station totals can remain usable without a plant-list fallback.
- Add the fixed diagnostic flag `device_tree_required:false` for Enduser.

The direct device-tree reader and its strict identity checks remain intact.
Home and Installer retain their existing device-tree setup/runtime paths.
No device is invented, no arbitrary plant is selected, and no control is
enabled. Authentication, account request pacing and poll intervals are unchanged.

## Why this change

The b13 reporter confirms `stage=station_validation reason=invalid_enduser_tree`.
In the actual setup sequence, the requested station's metadata and supported
classification have already been accepted before that error. Requiring a
fully valid device tree then blocks a station-only feature unnecessarily.

The official app's station Live/energy calls address the plant by station ID,
separately from its device-tree operations. This correction follows that
separation. The reporter's actual tree format is still unknown; b14 does not
claim to repair it or establish complete HIS compatibility before device testing.

## Test

1. Update through HACS to **v0.6.1b14** and restart Home Assistant Core.
2. Retry setup with **S-Miles Enduser (experimental, read only)**, select the
   discovered plant and submit it.
3. If setup succeeds, compare the available station PV/load/grid/battery/SOC
   and generation totals with the official app. Enduser remains station
   monitoring only; controls, module charts and inverter detail telemetry are
   not included.
4. If a new error occurs, share only the fixed `stage`/`reason` warning lines
   or privacy-checked integration diagnostics, without identifiers, credentials,
   tokens or raw API responses.

## Validation

Local validation: **1323 HA tests plus 134 subtests** on **HA 2026.11.0** and
**56 unit tests** passed. New tests cover actual HA setup using mocked HTTP,
exact/mismatched/unsupported metadata, repeated station monitoring without tree
requests, missing-Live startup and automatic recovery, failed metadata access,
and rejection of the station-only validation method by other profiles.
Syntax, translation-key parity, whitespace, documentation links and release
packaging are checked. Required PR/release CI tests both HA 2026.10.4 and
2026.11.0, HACS and Hassfest before publication.

No real-account or device requests were performed by the agent. The reporter's
successful setup and same-time app comparison remain pending. See the
[protocol follow-up](enduser-app-protocol.md#follow-up-after-b13-tree-failure).
