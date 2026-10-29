# v0.5.0b6

This prerelease follows a whole-repository review of b5. Stable remains v0.4.2; PR #10 stays draft and unmerged.

- Read current cloud settings before **every** control write, including reserve SOC. Preserve the app's current upper SOC limit and reject a reserve change when the freshly read mode does not support it. A write is still sent only once and must be confirmed by matching mode/configuration readback. Concurrent edits in the app during the read/write window cannot be made atomic by this unofficial API.
- Bound JSON responses to 8 MiB of decoded HTTP body and 32 container levels; validate authentication challenge/token shapes. Keep certificate verification, trusted HTTPS destinations and redirect rejection. Sanitize backend error text and suppress sensitive transport exception chains in displayed tracebacks. Handle corrupt gzip/deflate responses as connection failures.
- Add a password-only reauthentication flow for the existing account/station entry, preserving entry/unique/entity IDs, options and history. Other entries retain their own configured credentials.
- Stop integrating energy across failed live refreshes. Do not truncate fractional relay codes into known charging/discharging codes; retain the existing signed-power fallback for unrecognized direction values.
- Keep failed station-total reads at the one-minute cadence instead of retrying on every live refresh. Expire cloud totals after two minutes without success and reject previous-day/month/year totals at the station-local boundary. Stored readings and locally calculated daily counters are not erased.
- Pause automatic account login retries for one minute after a transport failure, shared by configured station entries using identical credentials. Keep the full server-directed HTTP 429/Retry-After pause even when it exceeds one day; bound only scheduler wake-up delays.
- Document real request counts, residual freshness/protocol limitations and device checks. Add distinct mode-switch and battery-temperature evidence requirements to the stable gate; no hardware confirmations were inferred from tests.

Validation: 34 unit tests and 247 Home Assistant tests pass locally, plus compileall, diff/translation checks and the checksum-pinned Node-RED comparison with synthetic data. Seventeen targeted cases were observed failing before their corresponding fixes. The existing readback tests retain their negative assertions and now provide a separate fresh pre-write snapshot. HACS, Hassfest and the release workflow must also pass before publication.

Install b6 with HACS prereleases enabled and restart Home Assistant **without deleting the integration**. See the [German test plan](testing-0.5.0.de.md) and [review report](review-0.5.0b6.de.md).

Maintainer reports confirm mode switching and battery temperatures on their setup only. Affected-device/app checks remain open, particularly the 4020-X, PV source and status interpretation, optional telemetry accuracy, night/day recovery and b6 preservation of app settings. No real-device control or authenticated polling was performed in this review. Normal per-input charts and battery temperatures still have documented cloud-response-age limitations; software tests do not establish physical measurement freshness.
