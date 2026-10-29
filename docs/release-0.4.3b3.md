# v0.4.3b3 — preventive fixes and manual settings refresh

Includes the v0.4.3b1 fallback fix and v0.4.3b2 PV/source diagnostics, plus:

- Recover a failed live URL with one bounded read retry, and distinguish temporary rate limits from rejected credentials. Concurrent automatic login checks share a refresh; password hashing no longer blocks HA's event loop. Writes are not automatically retried.
- Stop integrating energy through offline/missing/invalid samples. Explicitly disconnected live sensors and module readings without a successful response for ten minutes become unavailable; daily counters remain visible.
- Cancel/coalesce background settings reads, publish results immediately, and preserve the latest settings block for queued control changes.
- Fix the `k_1`/`k_10` reserve-SOC evidence mismatch, validate upper SOC limits, handle malformed charts and reject explicit device/port mismatches and nonfinite readings.
- Add **Refresh battery settings**, a read-only diagnostic button. It does not send a control command.

## Test

Install this prerelease in HACS and restart HA; keep the existing integration configured. Check normal readings and energy accumulation, then compare availability overnight and after morning recovery. Use **Refresh battery settings** after changing settings in the S-Miles Home app and confirm they appear without waiting 30 minutes. Share the diagnostic download and logs if readings fail to recover.

Existing entity IDs/history and the saved energy format are retained. Energy estimated during unknown/offline periods is deliberately not invented, so counters may differ from the app. Module freshness measures the age of the last successful response, not the vendor chart's underlying sample timestamp.

Validation: 29 unit + 129 HA tests locally; HACS/Hassfest and tests run before publication. Device validation is still pending. Stable remains v0.4.2.

The Node-RED client was cross-checked for protocol behavior; see [review findings and future telemetry candidates](review-2026-10-29.md). The Android APK download was blocked (HTTP 403), so no direct APK analysis is claimed. EMS/charge enums, battery maximum-power availability and additional writable modes remain unverified. Extra inverter temperature/frequency/voltage via the bulk endpoint is documented for a separately tested follow-up, not shipped as a working feature here.
