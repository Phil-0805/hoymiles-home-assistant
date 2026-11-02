# v0.5.0

Based on the tested v0.5.0b6 commit `1525a5231a600e9ea6bf592d7231691b7643d080`. On 2 November 2026 the maintainer explicitly approved stable publication with the outstanding device-evidence requirements recorded as known limitations. Those reports remain unconfirmed; the exception applies only to this release/candidate. Tests, HACS and Hassfest remain required.

## Changes since v0.4.2

- Add password reauthentication to the existing integration entry. Validate login and access to the configured station, then update credentials without recreating entities or losing existing identities/options.
- Fix the battery-settings fallback crash. Support Self-Consumption and an already configured supported TOU plan on the distinct action-83 protocol. Read current settings before every mode/reserve-SOC command, preserve saved settings and require matching readback. Never automatically repeat a write.
- Add an explicit per-station PV source choice (`auto`, `pv`, `pv2`), raw source attributes and allowlisted diagnostics. Automatic preserves the existing pv2-first behavior, including valid zero values.
- Add optional inverter temperature/frequency/AC voltage and battery/expansion-pack temperatures. Both are off by default and use five-minute background cycles. Keep battery temperature sensors on the existing station device and migrate b4 entities while preserving their identities, custom names and disabled state.
- Share authentication, request pacing and rate-limit pauses across configured stations using identical credentials. Bound responses/decoding, verify HTTPS certificates, reject redirects and sanitize transport/backend errors.
- Improve energy handling, response freshness and station-local day boundaries. Break energy integration across failed refreshes, retain valid zero readings, expire stale station totals and avoid retrying failed totals on every live refresh.

## Known limitations and unresolved reports

- **HiBattery 4020-X PV display remains unresolved (issue #9).** The affected user's HA PV sensor was mostly zero while the Hoymiles app showed generation. Switching the PV source was proposed; its result and the inverter model/connection details are still awaited. Do not interpret this release as a verified fix for that installation.
- Numeric EMS/charging/health codes and model-specific maximum-power meanings remain unverified. Unsupported control capabilities are not advertised as working features.
- Mode switching and battery temperatures were reported working on the maintainer's setup. Other models, firmware/account combinations, expansion packs and b6 setting-preservation behavior still require device/app evidence.
- Ordinary PV-input charts and battery temperatures rely on cloud response age; repeated old physical samples cannot always be detected. Additional inverter metrics retain their individual vendor sample timestamps.
- The unofficial API cannot make app and HA edits atomic. Avoid simultaneous app changes while an explicit HA command is running.
- The release-readiness record still contains nine unconfirmed device-evidence areas. Maintainer publication approval is distinct from verification of these claims.

## Updating and validation

Upgrade the existing integration and restart Home Assistant. Do not delete/re-add the integration or its entities. Optional telemetry stays off unless enabled in the entry options.

The underlying b6 code passed 34 unit tests, 247 Home Assistant tests, HACS and Hassfest. Its release CI is [recorded here](https://github.com/Phil-0805/hoymiles-home-assistant/actions/runs/40890566014). The stable preparation passes 39 unit tests and 247 Home Assistant tests, including five additional release-exception tests. Stable publication also requires successful HACS/Hassfest and CI checks. Automated tests do not replace actual device validation.

See the [device test plan](testing-0.5.0.de.md), [whole-repository review](review-0.5.0b6.de.md) and [current readiness record](release-readiness.json).
