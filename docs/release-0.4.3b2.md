# v0.4.3b2 — PV display and battery diagnostics beta

Includes the battery-settings fallback crash fix from v0.4.3b1, plus:

- Select the PV power source per station in the integration's Configure dialog: automatic (existing behavior), `pv`, or `pv2`. Both raw values and the actual selected source appear as PV power sensor attributes. This makes a confirmed field mismatch correctable without changing device settings or recreating the integration.
- Add a translated **Battery activity** diagnostic sensor: Idle / Charging / Discharging from `brs` 0 / 1 / 2, with an explicit unrecognized state for other numeric codes. This uses the direction mapping already tested on the maintainer's HMS-2000-4WB setup and used for energy calculations; confirmation on the HiBattery 4020-X is still pending. Existing numeric status entities and their IDs remain unchanged.
- Extend downloaded diagnostics with allowlisted PV/battery numbers, raw status codes, the PV selection and battery-settings availability/read path. Credentials, identifiers, error strings and raw API payloads are excluded from this integration's diagnostic data.

## Test on the affected installation

1. Install v0.4.3b2 through HACS with prereleases enabled, then restart Home Assistant. Keep the existing integration configured.
2. In daylight, compare `pv` and `pv2` in the PV power sensor attributes with the S-Miles Home app at the same time. Automatic still prefers an available `pv2`, even when zero. If `pv` matches the app instead, open **Settings → Devices & services → Hoymiles S-Miles Home → Configure** for that station and select **Cloud field pv**. The integration reloads to apply the choice, retaining entity IDs and saved energy counters.
3. Check Battery activity against actual charging, discharging and idle operation in the app. Send the downloaded diagnostics and the simultaneous app/HA readings if values disagree.
4. Confirm that battery settings no longer log the `work_mode_error` UnboundLocalError reported in #9.

PV fields are not added together, their names are not treated as physical input numbers, and missing values are not replaced with invented zero readings. Explicit selection of a missing field displays unknown. EMS, charge and health codes remain raw because their device-specific meanings are not verified. Battery maximum-power availability, additional writable modes and cloud connection resets are not fixed by this beta.

Related: #9 and draft PR #10. Stable v0.4.2 remains the latest stable release; device verification is required before promoting this beta.
