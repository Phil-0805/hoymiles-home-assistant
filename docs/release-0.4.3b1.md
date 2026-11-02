# v0.4.3b1 — battery settings fallback beta

Fix a reproducible `UnboundLocalError` when the app's work-mode settings request fails and the integration tries alternative battery settings endpoints. Preserve the original error text so a successful fallback can return its settings, or an unsuccessful fallback can report a normal connection error instead of crashing the background task.

This addresses the traceback reported in #9. It does not establish that every battery mode or maximum-power setting is available on the HiBattery 4020-X. PV field mapping and numeric status labels remain unchanged pending comparison with the S-Miles Home app. A cloud connection reset is separate from this Python error and may still occur.

## Testing

- Update to this prerelease through HACS (enable beta versions / show prereleases), then restart Home Assistant. Keep the existing integration configured; no removal or reinstallation is needed.
- Allow a battery settings refresh (normally within the first minute after setup), then check the battery settings entities and log for the reported `work_mode_error` traceback.
- Report the battery settings access state and whether mode/settings become available. A failed cloud request can still leave settings unavailable, but must no longer raise `UnboundLocalError`.

Regression coverage exercises successful station and device fallbacks, exhausted fallbacks with and without a compatible battery, background-refresh error handling, direct work-mode success and authentication failures. Device testing on the affected 4020-X installation is still pending. Stable v0.4.2 remains the latest stable release.
