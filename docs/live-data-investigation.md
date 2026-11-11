# Live sample interruptions: issue #34 — 2026-11-11

## Current evidence

The latest [reporter comment](https://github.com/Phil-0805/hoymiles-home-assistant/issues/34#issuecomment-6792550840)
confirms restored mode display/select availability. It does not report a completed
mode write. The maintainer separately confirms their own TOU test succeeded.
These observations concern Home mode handling, not Installer controls.

The reporter also shows 74 occurrences each of `invalid_live_data` and recovery
between 06:55 and 10:40 in their displayed log. The reported invalid payload is
an object lacking `flow`, `con` and `power`. These labels cannot establish whether
the object was empty, contained a server delay or contained other fields. They
do not establish a rate limit, an expired URI, a login failure or a TOU cause.

The two log lists show first failure/recovery timestamps two seconds apart and
last failure/recovery timestamps two seconds apart. Those align with the
client's bounded recovery, but aggregate log timestamps do not pair every
occurrence or prove that all of them recovered within the same HA refresh.
There is no confirmed measurement of entity-unavailability duration here.

## Code path and interpretation

`HoymilesHomeClient.async_live` has at most two attempts. A sample is accepted
when its unwrapped payload has a flow list or an explicitly numeric connection
state 0/1. This deliberately accepts valid offline responses. A rejected first
sample clears the cached URI, refreshes it and tries again using the existing
account budget. If the second response is valid, this same call returns success
to the coordinator, despite an earlier warning. That warning/recovery pair is
not by itself a failed coordinator refresh or unavailable HA entity.

If both samples remain invalid, the call raises and the coordinator reports
`UpdateFailed` and resets energy-integration samples. A later accepted refresh
logs recovery. Even a successful live call does not guarantee that an unrelated
request later in the same coordinator update succeeds.

The old exception text, **Live URI expired**, also covered two malformed live
samples after refreshing the URI. It therefore asserted a cause that was not
established. The new text describes missing usable telemetry after the retry.

## Current manufacturer comparison

The public website source followed for the parallel Installer review still
provides its seconds-data wrapper in `index-BTRAEMTt.js`; provenance and SHA-256
are recorded in [that review](installer-capability-review.md). Its web request
uses `m`, `t:1` and a reflux flag. This alone is not evidence to add these flags
to the separate Home mobile battery request.

The documented APKPure Home XAPK download was fetched again on 2026-11-11.
The actual XAPK manifest and APK `com.hoymiles.BuildConfig` identify
`com.hm.balcony`, **V2.14.0**, version code **2026110903**. This is newer than the
V2.13.0 used in [the earlier protocol notes](android-app-protocol.md); the old
artifact hashes are not overwritten.

Source: `https://d.apkpure.net/b/XAPK/com.hm.balcony?version=latest`, linked by
[the APKPure package page](https://apkpure.net/s-miles-balcony/com.hm.balcony/download).
This is still a third-party mirror. Publisher-signature identity has not been
independently confirmed for this download.

| Artifact | SHA-256 |
| --- | --- |
| XAPK | `939c6ba7f56a494ef4bb39453616a57ac3a09b828274f0638ace5a2e0f4d5392` |
| Base APK | `d3f39915b8164045ae4a7107aed3232f6fe8fe201c9f1d7543e5919b26127650` |
| Bundled `online_domain.json` | `8f876438eeaffd6264816b98fc8f62fdcb57cedecdfcea775ab48cc763677f3b` |

APK/assets were inspected statically; nothing was installed or run. JADX 1.5.6
reports 314 errors overall. The request method is readable. The battery callback
has reconstruction errors, so its relevant control flow was independently
checked with single-class **fallback instruction output**. The broken Java
locals in the normal decompilation are not treated as source evidence.
Artifacts stay outside the repo under `/private/tmp/hoymiles-live-research-20261111`.

Specific call chain:

- `MainHomeSystemChildBmsV8Fragment.r0` requests
  `PVMC_STATION_GET_SD_URI_C` with `{sid}`. The bundled route table maps it to
  `/pvmc/api/0/station/get_sd_uri_c`.
- `q0` posts **`{sid,m:0}`** to the returned URI through `EasyRequest.b`.
  This matches the integration's Home live body; no missing `t:1` is demonstrated.
- Its success callback `E` parses the response data and enters its data-update
  branch only when `flow` is present. In that branch it schedules the next read
  using `dly`. Fallback instructions confirm that the no-flow branch jumps past
  that scheduling block. The exception path schedules a same-URI read after
  5000 ms. This is foreground-screen code, not a cloud-service guarantee.
- The WBPv page `MainHomeSystemChildWBPvV1Fragment` similarly requests `{sid,m:0}`
  and handles flow plus `dly`. The Installer power page has a different request
  and no-flow/delay handling; it must not be substituted for Home behavior.

This does not establish that an empty or delay-only object should be accepted
as Home telemetry, nor a manufacturer quota or a cause for the reporter's
responses. No request parameter or retry policy was changed from this evidence.

## Local diagnostic change

Existing warning severity and deduplication are retained. No warning is hidden
merely because a later attempt recovers. The fixed summary additionally records:

- `object_state=empty/nonempty/not_object`;
- `dly_type`: a fixed type/presence label;
- `dly_state=missing/invalid/negative/nonnegative`, using the existing finite
  number parser. This describes shape, not a new validity or rate-limit policy.

Recovery logs additionally distinguish:

- `recovery_scope=same_refresh`: the invalid-data episode began and recovered
  inside this live call; a valid sample was returned to its caller;
- `recovery_scope=later_refresh`: an invalid-data episode already existed when
  this live call started, even if this call also needs its own retry.

No arbitrary keys, raw data, measurement values, delays, URLs, identifiers,
tokens or server messages are logged. Missing fields stay missing. JSON/TLS
bounds, accepted samples, URI refreshes, two-attempt cap, requests, account
pauses, polling and energy behavior remain unchanged. The exception reason
stays `invalid_live_data`; only its explanatory text is corrected.

These are diagnostic improvements, **not a demonstrated fix for the cloud
response or physical telemetry interruptions**. Synthetic tests cover summary
privacy and delay types, same/later-call recovery, later-call retries and
unchanged exact requests/rejection of delay-only replies. The targeted tests
and full HA/unit suites are run before handing back the change.

## Minimal next feedback

After a version containing this change is explicitly published and installed,
ask for the fresh fixed warning/recovery lines and whether the actual power
entities became unavailable at the same time. A same-time official-app
comparison helps distinguish cloud/device silence from an integration-specific
problem. No raw capture, credentials, password change or device command is
needed. Do not ask users to install an unpublished local change as if it were
already included in b3.

Do not suppress the failure, synthesize zero power or retain old measurements
as freshly updated simply to remove the warnings. A delay-only response can
be investigated once established; the existing report does not establish it.

No real account/device was accessed, no issue comment was sent, and no version
bump, commit, push or release was performed for this investigation.
