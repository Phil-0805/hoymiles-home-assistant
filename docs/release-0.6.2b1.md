# v0.6.2b1 — six-input HMT monitoring

This first v0.6.2 beta addresses missing individual PV inputs on six-input HMT
microinverters. Stable remains **v0.6.1**.

## Changes from v0.6.1

- Recognize explicit **HMT-1800-6T** and **HMT-2250-6T** model metadata.
- Create power, voltage and current entities for all six physical PV inputs,
  including the previously omitted PV5 and PV6, and query their existing
  module-chart data. Existing PV1–PV4 entity identifiers remain unchanged.
- Keep the five-minute module-chart cadence, shared HTTP pacing, server pauses
  and field-freshness checks. These models now require six per-port chart reads
  per cycle instead of the previous four.

The former model parser recognized selected HMS models only, so the reported
HMT-2250-6T fell back to four inputs. Station total generation is read separately;
its agreement with the app does not demonstrate individual PV5/PV6 data access.

This is a monitoring change. It does not extend the HMS-only standalone output
control capability to HMT or infer write limits from a model name. Unknown
models retain their existing fallback. Enduser remains station-only and does
not gain module-chart entities.

## Test for issue #55

1. Enable beta versions in HACS and update to **v0.6.2b1**.
2. Restart Home Assistant Core; retain the existing integration entry.
3. Confirm the detected model and all six PV inputs appear. Each input has
   power, voltage and current sensors; existing entities should retain their IDs.
4. Allow a normal module-chart refresh, then compare PV5/PV6 with the official
   app during production. These are chart readings, not seconds-current Live data.
5. If the model remains generic or readings are unavailable, share a fresh,
   privacy-checked integration diagnostic and relevant fixed stage/reason lines.
   Do not share credentials, identifiers, tokens or raw API responses.

The code gap is reproduced synthetically. Confirmation on the reporter's
HMT-2250-6T/DTU-Pro-S installation remains pending. HA 2026.8.3 from that report
is not part of the automated test matrix; no successful test on it is claimed.

## Scope of the other investigations

- **Issue #54:** the supplied `login_region` warning is emitted by the Home
  profile in v0.6.1; the reporter's working official app is Enduser. Confirm the
  profile used by the affected entry before attributing this to a new API change.
  This beta makes no authentication change or automatic profile fallback.
- **Issue #51:** history sampling and optional shorter retention are documented
  design proposals only. No sampling option or automatic deletion is included.

## Validation

Local checks passed: **1,278 HA tests on HA 2026.11.0**, **56 unit tests**,
Python syntax, translation-key parity, whitespace, release workflow syntax and
release ZIP checks. The existing pytest anyio assertion-rewrite warning remains.
Required PR/release CI checks cover HA 2026.10.4 and HA 2026.11.0, HACS and
Hassfest. No real accounts or devices were accessed by the agent.

Source provenance, implementation boundaries and device-test limits:
[six-input HMT investigation](https://github.com/Phil-0805/hoymiles-home-assistant/blob/v0.6.2b1/docs/issue-55-six-input-hmt.md).
