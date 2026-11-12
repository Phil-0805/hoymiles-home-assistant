# API timing and bounded settings recovery

For the local correction after b10, see [chart progress and availability](chart-progress-freshness.md).
It preserves these request intervals and fixes availability assessment between
slow chart polls; no new manufacturer quota is inferred.

This records the existing timing controls and the local preparation for the
v0.6.0 prerelease, replacing the previously planned b10.
Manufacturer UI polling is evidence for a command workflow, not a published
account-wide request quota. No real account or device requests were made by the
agent to test these changes.

## Existing limits retained

| Operation | Timing / bound |
| --- | --- |
| Shared account HTTP budget | At least 1 second between starts, at most 2 requests in flight across entries sharing credentials |
| Live telemetry | Server-provided delay, at least 3 seconds |
| Station totals | At most once per minute, including failed attempts |
| Temperatures and module details | Existing 5-minute cadence |
| Successful settings reads | Existing 30-minute cadence |
| Manual settings refresh | At least 30 seconds between attempts; concurrent refreshes coalesce |
| Device/station command status | 1 second before each poll, at most 10 polls for the same job |
| HTTP request timeout | 30 seconds |
| Settings read/write operation timeout | Existing 120-second bound inside the settings lock |
| Device-setting write readback | At most 3 reads, 3 seconds between attempts, never resubmit the write |
| Battery-mode write confirmation | Existing 8 attempts, 3 seconds between attempts, never resubmit the write |

Every HTTP request, including command submission, status polls, fresh-read
preflight and readback, uses the shared account budget. TLS, redirect restrictions
and server pauses are unchanged. HTTP 429 uses Retry-After; the account runtime
retains its complete deadline even when scheduler wake-up delays are capped.
An arbitrary cloud rejection with status 1 is not evidence of a rate limit.

## Live-wait correction in v0.6.1b5

**Regression update:** the maintainer reports persistent unavailable entities
with b5. B6 removes this waiting policy and restores b4's bounded URI lookup/retry.
See [the b6 instructions](release-0.6.1b6.md); b4 remains a rollback option.
The description below records b5's historical behavior, not the repaired code.

An explicit reduced live response with integer `dly` and no flow/connection/
power fields is handled as pending data in v0.6.1b5.
Short delays reuse the same URI after the server delay (at least three seconds),
outside account/HTTP locks, with at most two live reads per update. More than
30 seconds of inline waiting is deferred to the HA scheduler; repeated pending
replies are also deferred. The full per-client monotonic deadline is preserved,
including across in-process setup retries/reloads; a capped scheduler wake-up
never permits an early live request. This is not an account-wide rate pause.

Deferred updates remain missing data and reset energy-integration samples.
Unknown/malformed replies retain existing bounded URI recovery and warnings.
These changes are introduced in b5; b4 is unchanged. See the
[evidence, implementation and limits](live-data-investigation.md).

## What the inspected Android app establishes

The archived V2.13.0 package and hashes are documented in
[the protocol notes](android-app-protocol.md). `CommandRequestHelper.U0` reads
`PVMC_STATION_CTL_SETTING_STATUS_C` with the existing command ID via
`HttpHelper.C`. `Y0` maps the numeric result through `ECommandStatus`:
0 success, 1 failed, 2 executing, 3 timeout, 4 stopped.

For executing jobs, `Y0` schedules another status read after `1000L` milliseconds.
For failed status requests, `a1` schedules the same status read after `1000L`,
bounded by `f8125c=3` and the `f8126f` counter; `c1` resets that counter for a new
operation. This does not establish permission to resend a write. It also does
not establish a permanent one-second Home Assistant settings refresh interval.
The integration retains its existing ten-poll cap rather than adopting indefinite
executing-status polling from a foreground screen.

## Local read-only recovery policy

The previous settings scheduler reserved the next 30-minute interval when a
read started, even if that read failed. Boot-time optional settings could remain
unavailable until a manual refresh or the next normal cycle. The maintainer
reported a manual refresh recovering them, with a generic cloud rejection in
the log; the cause of that rejection is still unknown.

The local correction allows at most **two additional read attempts**, after
**1 minute** and then **3 minutes**, measured from each failure's completion.
These longer delays are a conservative integration policy, not an APK-derived
quota. After those attempts, the ordinary 30-minute cycle resumes. Successful
settings keep their existing cadence; only failed heating/lighting/cutoff/output
features participate in a recovery attempt. Mode/reserve settings use the same
bounded read-recovery policy in their background reader.

Authentication failures, rate limits, known malformed/unsupported settings,
unsafe redirects, and HTTP 4xx rejections do not get accelerated retries. Generic
connection failures, timeouts, server failures and unclassified cloud rejections
can receive the bounded attempts. An unclassified rejection is not thereby
declared temporary or rate-limited. Server pauses still take precedence.

There is no extra timer or busy loop: recovery is checked on the existing live
coordinator tick. Disabled controls, unload and ambiguous controller addresses
prevent further optional settings reads. Target selection is checked again;
stored addresses are not replayed blindly. Manual refresh can explicitly start
a new full cycle after its cooldown and shares an already running task. No write
failure schedules a write retry. A whole-read timeout no longer marks a feature
that already succeeded in that batch unavailable.

## Fixed diagnostic stages

Known settings read/write endpoints now identify fixed operation names such as
`heating_read`, `lighting_read`, `cutoffs_read`, `output_power_read`,
`work_mode_read` and `battery_settings_read` (and their write equivalents).
Status polls are labelled `device_settings_status` or `station_settings_status`;
phase lookup is `output_phase_lookup`. Unknown actions receive a generic fixed
settings stage. Neither URLs, job IDs, payload values nor arbitrary action strings
become log labels. This improves attribution without exposing raw responses.
