# v0.6.1b13 — Enduser setup response compatibility

This beta addresses an app-compatibility gap in Enduser station validation and
adds precise failure reasons for the remaining device test. Stable remains
**v0.6.0**. Enduser and Installer remain experimental, read-only profiles.

## Changes from b12

- Accept short decimal integer strings in the known Enduser station and device
  identity/classification fields, matching the inspected app parser. Boolean,
  floating-point, malformed, oversized, missing and mismatched identities remain
  rejected. No station or device identifier is manufactured.
- Accept a single bounded JSON-text representation of Enduser station metadata
  and device trees. The existing JSON byte/depth limits remain enforced;
  malformed or repeatedly encoded data is not accepted.
- Normalize copied device nodes while retaining child validation, tree size
  limits and conflicting-identity rejection. The original response is not
  mutated. Home and Installer keep their existing parsing behavior.
- Distinguish `invalid_enduser_metadata`, `invalid_enduser_station_id`,
  `invalid_enduser_classification` and `invalid_enduser_tree` in setup logs.
  These fixed reasons contain no identifiers, credentials or raw responses.
- Display a plant-data-format error for these validation failures instead of
  the generic connection error. Unsupported plant classifications retain their
  specific unsupported-plant message.

No endpoint fallback, authentication change, faster polling, permission change
or additional control is introduced. B12's station-monitoring scope is retained.

## Reporter feedback and limits

The b12 reporter confirms successful Enduser authentication and plant discovery,
followed by `stage=station_validation reason=unexpected_response` on submission.
That line does not identify the rejected response or prove its field types.
The app-compatible parsing gap is verified in source and corrected in tests;
its role in the reporter's actual failure still needs confirmation.

## Test

1. Update through HACS to **v0.6.1b13** and restart Home Assistant Core.
2. Select **S-Miles Enduser (experimental, read only)** during setup, select the
   discovered plant and submit it again.
3. If setup succeeds, compare the available station readings with the app as
   described in [the b12 test scope](release-0.6.1b12.md).
4. If it fails, share the new **Cloud setup failed** line with its complete
   fixed `stage` and `reason`. Do not post credentials, identifiers, tokens or
   raw API responses.

## Validation

The runtime correction passed **1312 HA tests plus 134 subtests** on HA
**2026.11.0**, and **56 unit tests**, locally. Added tests cover object/text
representations, decimal integer strings, invalid and mismatched identities,
conflicting devices, input immutability, JSON size/decoding limits, private-data
exclusion and the setup error presentation. Syntax, translation-key parity,
whitespace and release packaging are checked. Required PR/release CI tests HA
2026.10.4 and 2026.11.0, HACS and Hassfest before publication.

See [the protocol follow-up](enduser-app-protocol.md#local-follow-up-after-b12-feedback)
for evidence and limits. No real-account or device requests were made by the agent.
