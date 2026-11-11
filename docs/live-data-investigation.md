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

## B4 feedback and focused delay review — 2026-11-11

The maintainer's b4 screenshot now supplies the missing structural evidence:
14 displayed invalid-sample occurrences and 14 `same_refresh` recoveries.
The invalid sample has no `flow`, `con` or `power`, but is a nonempty object
with integer, nonnegative `dly`. The displayed first and last recoveries follow
the corresponding displayed failures by two seconds. These live calls returned
valid telemetry after the existing internal retry. This does not establish
uninterrupted availability of every other part of a coordinator update.

The screenshot does **not** establish that `dly` is the only key, disclose its
value, or distinguish zero from a positive delay. Do not call it a proven
rate-limit response or infer a particular number of milliseconds.

### Current web evidence: independent delay scheduling

The public website entry was fetched again. It still names `index-BTRAEMTt.js`;
that entry's `/plant/detail/:id` default route imports `index-BnyZCQvr.js`.
The latter was downloaded from
[the referenced manufacturer URL](https://static.hoymiles.com/cdncache/website/js/index-BnyZCQvr.js)
on 2026-11-11, SHA-256
`00f6af7ccc4ce167c4bafd372ad69274d0ce7d88f812b21ce5ecb49918e9c60d`.

Its overview polling function `m`:

1. Calls `getSecData(x.value, 0, !!h.value)` using its saved live URI.
2. On a successful response, updates the displayed sample only if `Y.flow`
   is present/truthy. An empty JavaScript array is truthy here.
3. Independently checks `Y.dly` and schedules **the same function** with
   `setTimeout(m, Y.dly)`. This condition is outside the `Y.flow` condition.
   Thus a truthy delay can schedule another read without updating measurements.
4. Obtains `x.value` once with `getSecDataUri` during mount; the no-flow/delay
   branch does not request another URI. Unmount clears its timer and sample.

The request wrapper is the already hashed `getSecData` in the entry module.
It posts `m`, `t:1`, `reflux` to the supplied URI. The website provides concrete
evidence for **wait and reread the same URI**, not for adding those web-specific
flags to the separate Home request. A JavaScript truthiness check is not a safe
numeric validator for HA; it is not adopted as one.

This is stronger evidence than the Home battery screen alone: the Home
`MainHomeSystemChildBmsV8Fragment.E` fallback instructions show no independent
no-flow scheduling branch. It would be incorrect to claim that that exact
mobile callback explicitly handles delay-only responses. The Installer power
callback also obtains `dly` outside its flow-update branch and rereads the same
URI, but belongs to a different profile. The current web client is the primary
reference for the proposed change.

### Synthetic reproduction of the current mismatch

Using the current b4 client with a cached synthetic URI, a successful
`data:{dly:5000}` reply followed by a valid flow/connection sample produces:

- two live reads;
- **one unnecessary intermediate URI lookup**, even when that lookup returns
  exactly the same URI;
- no wait based on the returned `dly`; only the existing account request-start
  spacing applies;
- a valid final result, explaining why a warning/recovery pair need not mean
  unavailable HA entities.

The live and URI methods were mocked; no network or device was accessed.
The 5000 ms value is synthetic and is **not** the maintainer's unknown value.
This demonstrates an integration mismatch, not why the server sometimes sends
the reduced reply or a guarantee that the correction will prevent every gap.

### Recommended bounded correction

This review recommends a dedicated **pending-live-data** path, not weakening
telemetry acceptance:

- Consider it only after successful transport/envelope processing, with a
  validated nonnegative integer delay and absent telemetry fields. Conflicting
  or malformed `flow`, `con` or `power` must not become a waiting response merely
  because a `dly` field is present. Zero is not evidence of a positive wait;
  avoid a tight loop and retain at least the existing live minimum interval.
- Keep the validated URI and repeat the same read after the delay. Do not
  request a new address, change login/profile/request flags or replay a write.
  Keep at most two live reads per update and the existing account budget.
- For a short bounded delay, wait outside HTTP/account locks. A possible
  30-second inline-wait cap would be an integration policy, not an established
  manufacturer limit. Wait at least the applicable server delay and local
  minimum; do not clamp a larger server delay down to this cap and read early.
- For a longer delay or another pending reply at the attempt cap, retain a
  per-live-client monotonic not-before deadline and defer through the HA
  scheduler. A scheduler wake-up cap must not shorten the actual deadline.
  Do not pause other plants/accounts or label it a rate limit without evidence.
- Never return the reduced reply as fresh telemetry, synthesize zero power,
  refresh an old sample's timestamp or integrate energy across a failed update.
  Repeated waiting needs an explicit missing-data/freshness policy rather than
  keeping an old sensor value fresh indefinitely.
- A recognized, successfully handled wait should be distinguished from
  malformed data in logs. Do not blanket-suppress `invalid_live_data`, HTTP,
  auth, JSON or transport failures. Keep fixed privacy-preserving labels.
- Test positive/zero/invalid/oversized delays, no early read, no URI lookup,
  repeated pending results, exact request count, server pauses, cancellation,
  unload, authentication/target changes, missing-data freshness, energy resets
  and Home/Installer isolation before enabling the behavior.

No runtime code, version, tag or release was changed for this focused review.
The proposed scheduling behavior is not yet included in b4. A real-device/app
comparison remains needed after a correction is implemented and authorized for
testing; no such test is claimed here.

## Implementation for v0.6.1b5

The maintainer subsequently requested implementation and then publication as
**v0.6.1b5** for testing. This release contains the correction below;
the historical b4 release is unchanged.

- Recognize a reduced live reply only after the existing successful response
  processing, when `flow`, `con` and `power` are absent and `dly` is a JSON
  integer in the signed-64-bit transport range. Booleans, strings, fractions,
  negative/oversized values and present-but-malformed telemetry fields do not
  qualify. Extra unknown fields are not copied into logs or HA measurements.
- Retain the validated live URI and request body. A short wait uses a monotonic
  deadline and releases HTTP/account locks before sleeping. It waits at least
  the returned delay and the existing three-second live minimum. A zero delay
  therefore uses three seconds as a conservative local policy; it is not
  interpreted as a rate limit or permission to loop immediately.
- Keep the two-live-read cap. Wait at most 30 seconds inline; this cap is a
  client policy, not a claimed cloud limit. A longer deadline or another
  pending result at the attempt cap raises `HoymilesLivePending`. The coordinator
  schedules a later read with `UpdateFailed.retry_after`, retains the complete
  monotonic deadline and never reads early just because scheduler wake-ups are
  capped at one day. Other station clients do not receive an account pause.
- When an update is deferred, it does not publish telemetry. Existing HA
  availability/error behavior applies, and energy-integration samples are reset
  rather than integrated across the failed update. A short wait followed by a
  valid sample returns that actual sample using the existing energy gap policy.
- A recognized waiting reply no longer creates the misleading
  `invalid_live_data` warning/recovery pair. A fixed debug label identifies it
  as pending. Malformed replies, failed envelopes, authentication, rate limits
  and transport failures retain their error handling; they are not reclassified
  merely because an error payload contains a delay field.
- Serialize live calls for one client. Track and cancel active/queued live
  calls on unload, including inline waits. Check URI/profile/station identity
  before attaching a delay and after sleeping; a changed target cannot inherit
  the old response or trigger a read against the old URI.

Both supported HA versions ignore `UpdateFailed.retry_after` during initial
config-entry setup. An in-memory setup guard therefore preserves the full wait
across setup retries and reloads. It is bound to that config entry's hashed
account identity, profile and station. It stores no password, token, raw
response or URI. Changed targets discard the old wait; removing an entry clears
it. This state deliberately does not persist across a full HA process restart.

Synthetic coverage includes exact Home/Installer bodies, no unnecessary URI
lookup, short/zero/long/multiday and repeated delays, early sleep wake-ups,
signed-long bounds, malformed data, genuine errors, account pauses, target
changes, cancellation/unload, HA availability, energy reset, setup/reload and
the actual HA first-refresh exception path. No real account/device was used.

Validation of this implementation: **985 HA tests on each of
HA 2026.10.4 and 2026.11.0**, **56 unit tests**, syntax, unchanged translation-key
parity, local documentation links, whitespace and a 37-file release ZIP
matching the working Python sources. No device-level success is claimed from
these synthetic tests.
