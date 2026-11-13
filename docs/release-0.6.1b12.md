# v0.6.1b12 — experimental S-Miles Enduser monitoring

This beta adds a separate **S-Miles Enduser** account profile for testing with
the official Enduser app. Enduser, Home and Installer are distinct clients;
being a plant owner does not identify which profile is appropriate.
Stable remains **v0.6.0**.

## Changes from b11

- Add **S-Miles Enduser (experimental, read only)** at setup and reauthentication,
  with its evidenced `smo` client identity and a separate token/DC session.
  Authentication uses the explicit server challenge, without trying other
  profiles, hosts or password algorithms after an arbitrary rejection.
- Follow the Enduser app's plant-list request and bounded pagination. Validate
  the selected plant's identity and classification, including manual-ID setup.
  Unsupported plant types receive a specific setup message.
- Support station Live readings for the verified PV and storage/hybrid schemas.
  The hybrid adapter reads solar, load, grid, battery and SOC fields in their
  documented units. Grid import is positive/export negative; battery charging
  is positive/discharging negative. Nonzero directional readings need an
  unambiguous reported flow. Missing/invalid fields remain unavailable.
- Read explicitly returned standard generation totals in Wh. No storage or
  date-specific counter is substituted for a missing generation total.
- Preserve the existing station/entity identity when changing profiles through
  reauthentication. Enduser options expose station timezone only; a previously
  stored Home PV2 selection cannot override its power adapter.
- Add fixed profile/schema labels to privacy-preserving diagnostics and identify
  Enduser flow-derived battery activity separately from Home relay codes.

Enduser supports **station monitoring only** in this beta. Module charts,
individual inverter telemetry/temperature, battery settings, output controls,
heating and lighting are not enabled. Existing stored control permissions cannot
unlock those operations. Home and Installer keep their existing parsers and
feature scope; shared HTTP pacing, server pauses and poll intervals are retained.

## Test with S-Miles Enduser

1. Install **v0.6.1b12** through HACS prereleases and restart Home Assistant Core.
2. During setup, select **S-Miles Enduser (experimental, read only)** for an
   account that works in the official Enduser app. Do not select Home just
   because you own the plant. Existing working Home/Installer entries need no
   profile change.
3. Check plant discovery. If the list fails or is empty, use the known numeric
   station ID; its access and classification are still validated.
4. Compare same-time station PV, load, grid, battery and SOC readings with the
   app, where available. Check import/export and charging/discharging directions,
   and compare any available generation totals. Genuine zero remains zero;
   an offline connection does not manufacture zero measurements.
5. On failure, report the integration/HA version and fixed diagnostic
   `stage`/`reason` lines, or a privacy-checked integration diagnostic. Do not
   post credentials, tokens, identifiers, raw responses or unredacted captures.

The Android Enduser V3.14.0 APK and public app-type-3 route configuration were
inspected statically. This establishes the implemented protocol, not successful
access to every Enduser account or compatibility with the reporter's iOS/HIS
installation. The first real-device comparison remains pending.
See [sources, hashes, mappings and limits](enduser-app-protocol.md).

## Validation

Local validation uses HA **2026.11.0**: **1284 HA tests plus 134 subtests** and
**56 unit tests**, including exact Enduser requests, authentication variants,
session separation, shared server pauses, bounded discovery, identity and target
changes, profile changes, unsupported-operation denial and real HA entity
publication through missing/offline/recovered states. Syntax, translation-key
parity, whitespace and release packaging are checked. Required PR/release CI
tests HA 2026.10.4 and 2026.11.0, HACS and Hassfest before publication.
No real-account login, device command or app execution was performed by the agent.
