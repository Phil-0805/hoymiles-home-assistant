# v0.5.0b2

- Keep a verified single battery mode visible instead of displaying `unavailable`. Selecting the current mode sends no command. The `mode_change_available` attribute distinguishes current-mode display from an actual choice; unsupported modes remain blocked.
- Explicitly use Home Assistant's certificate-verified HTTPS session for setup and configuration. Token-bearing requests still reject redirects and non-Hoymiles destinations; URL validation additionally rejects controls, whitespace, malformed host labels and fragments.
- Confirm writes only from a readable response using the original API method, with renewed reserve-SOC evidence where applicable. Compare complete requested values, including nested settings, without confusing booleans with numbers. A failed readback never retries the device write automatically.
- Request intervals, concurrency limits, settings-refresh cooldowns and optional telemetry cadence are unchanged.

Maintainer feedback: temperature was reported working on b1, but another screenshot shows temperature/frequency/voltage unavailable. Missing or expired cloud samples must remain unavailable, not zero. These screenshots do not establish a cause or complete hardware verification. Two-port inverters do not gain PV3/PV4 values. Keep optional telemetry and the other release-readiness reports pending until affected users confirm the b2 candidate.

After installing this prerelease, restart Home Assistant. Check that the battery mode displays Self-Consumption and reserve SOC still reads correctly. With only one verified mode, no mode change is offered. Verify any deliberate SOC change against the Hoymiles app. No reinstall or entity deletion is required.
