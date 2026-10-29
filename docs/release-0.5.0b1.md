# v0.5.0b1 — larger release candidate, beta only

Carries the v0.4.3b1–b3 fixes and adds:

- Shared in-memory authentication/request budgets for identical credentials: one token/login lock, at least one second between HTTP starts, at most two HTTP requests in flight and shared Retry-After pauses. Existing per-station server-directed live cadence, five-minute module polling and thirty-minute settings polling remain. Manual settings refresh has a thirty-second cooldown.
- Independent background module polling, cancelled on unload. Slow chart requests no longer run inside the live refresh. Network-budget contention can still delay requests; concurrency remains bounded.
- Optional read-only inverter temperature, grid frequency and AC voltage, disabled by default. Reads a single additional station snapshot at most every five minutes. The independent parser was cross-checked against pinned Node-RED code with a synthetic fixture; real-device validation is pending.
- Per-station timezone selection for daily counters and chart dates.
- Clearer capability reporting: single-mode systems have no actionable mode dropdown, unverified codes are labelled raw, and unavailable maximum-power fields are not shown as usable measurements. The legacy maximum-power setting no longer claims an unverified percent unit. No new battery control modes/commands were enabled.
- Nested setting readback must match before a write is considered confirmed. SOC probes export only numeric candidates.
- A stable release gate requiring documented user/device confirmations and maintainer approval before 0.5.0 can be published. Every actual confirmation remains pending; automated tests do not populate it.

## Test

Install this prerelease through HACS and restart HA; retain the existing integration. Use the read-only settings refresh and compare PV/source and battery activity with the app. Optional additional telemetry can be enabled in Configure; check its readings in daylight. Observe overnight recovery and normal daily energy/history preservation.

Follow the [German test and release plan](testing-0.5.0.de.md). Stable remains **v0.4.2**. Issue #9 remains open: numeric EMS/charge meanings, maximum-power availability and affected-user confirmation are not claimed resolved by this candidate. Extra telemetry is optional and unverified on real hardware. The Android APK was not available for direct analysis; the Node-RED reference check uses no live account or device commands.
