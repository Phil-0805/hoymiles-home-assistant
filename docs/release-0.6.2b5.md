# v0.6.2b5 — independently validated startup without Live measurements

This beta provides focused test candidates for [#59](https://github.com/Phil-0805/hoymiles-home-assistant/issues/59)
and [#61](https://github.com/Phil-0805/hoymiles-home-assistant/issues/61).
Neither the reporters' exact failing response nor a shared nighttime cause has
been confirmed. Stable remains **v0.6.1**; earlier beta features remain included.

## Changes from b4

### Independent Home startup when no measurement is supplied

- Keep the complete existing bounded Live → URI recovery → Live sequence.
  If it returns real telemetry, use that telemetry immediately as before.
- If both successful Home responses are either empty objects or objects
  containing only a valid nonnegative integer `dly`, report a distinct internal
  `live_no_measurements` condition. This is missing data, not a zero measurement
  or an inferred offline state.
- Require independent, exact account/station access validation before allowing
  setup to continue. Device discovery and station totals can then load while
  Live measurements remain unavailable. Retry Live on the existing one-minute
  partial-data cadence and resume fast updates automatically on a valid sample.
- Preserve missing-URI handling, malformed-response failures, authentication,
  access, HTTP/transport/redirect and rate-limit handling. A malformed response
  followed by an empty response does not qualify. Installer/Enduser behavior
  is unchanged. Energy integration does not bridge missing-data gaps.

Structural warnings can still describe replies without usable telemetry; this
beta separates those replies from a failure to load the independently accessible
station. It does not simply hide warnings or restore old data as fresh.

### Read-only PV-without-battery capability

- Follow the Home app's station-list fields: require explicit JSON integers
  `classify=1` (PV) and `bt=0`, with an unambiguous matching station identity.
  Missing fields, booleans, strings and conflicting/duplicate records do not
  establish this capability.
- Also require a valid PV-only device topology, with positive identities,
  no duplicates, no unknown device types and no conflicting storage/controller
  information. A missing model alone never proves there is no battery.
- With this evidence, skip automatic/manual work-mode and legacy battery-settings
  reads and automatic battery-temperature discovery, even if the HMS model is
  unresolved. Do not use this capability to authorize inverter output controls;
  their existing model, topology, permission and readback checks remain.
- Check the additional station metadata at most once per station/tree context,
  under a twelve-second budget and existing account pacing. Reuse the independent
  access-validation result when available. No new endpoint, periodic capability
  loop, persistently trusted model cache or faster Live polling is introduced.
  Unknown capability retains the existing battery path; this beta may therefore
  still show warnings if the required metadata is absent.

## Test instructions

Install **v0.6.2b5** with HACS beta versions enabled and restart Core. Keep the
existing integration entry/profile; no deletion or recreation is needed.

**For #59:** restart/reload when the inverter is inactive. Check whether setup
finishes while unavailable Live sensors remain honest. Check station/module data
separately. Leave HA running until production resumes and verify recovery without
another restart. Export diagnostics while the problem is present and afterwards.

**For #61:** compare startup at night and normal daytime operation. Check whether
the two work-mode/battery-settings warnings still occur, and export fresh
diagnostics. If the model remains unresolved, allow b4's existing five/fifteen-
minute recovery windows to complete (about twenty minutes plus request time).
Check output settings and inverter details separately; no new control target is
inferred from station capability.

Useful diagnostic fields under `polling`:

- `live_available`, `live_unavailable_reason`
- `battery_reads_applicable`, `battery_read_applicability_reason`
- `standalone_hms_recognized`, `standalone_hms_reason`
- `model_discovery_recovery_attempts`, `model_discovery_recovery_pending`

The battery suppression reason is either `standalone_hms` or
`station_pv_without_battery`; `not_excluded` means no suppression is established.
Share the complete fixed stage/reason/type warning lines if a failure remains,
plus integration/Core versions. No credentials, identifiers or raw replies.

## Validation and limits

Local validation: **1,389 HA tests on each of HA 2026.10.4 and 2026.11.0**, plus
**56 unit tests**, syntax and whitespace checks. Fifty-two new startup/capability
cases cover both missing-data shapes, rejection of malformed replies, exact
station validation, daylight recovery, integration gaps, cadence, strict field
types, duplicate/conflicting metadata, topology, target changes/unload and
auth/rate failures. Required release CI also runs HACS and Hassfest.

Source evidence: fresh public manufacturer Web assets and static Home Android
V2.14.0 inspection; the APK is from a third-party mirror without independently
confirmed publisher signature. No app was installed/run and no real account,
device or user database was accessed. Installation-specific success still needs
the reporters' tests. [Evidence and implementation limits](https://github.com/Phil-0805/hoymiles-home-assistant/blob/v0.6.2b5/docs/night-startup-investigation.md).
