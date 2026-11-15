# Issue #54: authentication routing and client profile

Investigation updated 2026-11-15; v0.6.2b2 implementation described at the end.
[Issue](https://github.com/Phil-0805/hoymiles-home-assistant/issues/54).
Baseline: v0.6.1.

**Updated conclusion:** the new same-installation v0.6.0/v0.6.1 comparison and
the normal Home APK login path make the unconditional region-before-challenge
dependency the primary regression candidate. The original profile-mismatch
assessment below is historical and is no longer a sufficient explanation.

## What the report establishes

The reporter says the integration worked the previous day, then failed with
`stage=login_region reason=invalid_auth_routing cloud_status=0 data_type=object`.
They confirm the official S-Miles Enduser app and the global website still work.
This does not establish a password error, rate limit, changed server routing or
the exact contents of the rejected response.

## Important distinction in the current code

`HoymilesHomeClient._async_login_unlocked` invokes Home's `region_c` only when
`supports_home_features` is true, which is set from `profile == "home"`.
The reported validation reason occurs exclusively in that branch, before the
password challenge or hash calculation. A successful response wrapper alone
does not satisfy the trusted-host/DC routing checks.

Enduser and Installer do not invoke `region_c`; they start at their documented
pre-inspection endpoint. In particular, Enduser uses its own `smo` identity,
session and app-type-3 route evidence. Existing regression tests verify its
actual mocked transport has pre-inspection/login only, no Home region request.
Missing `client_profile` in an old config entry intentionally defaults to Home.

Therefore, if the log belongs to the stated v0.6.1 code and the affected entry,
that request ran through the Home profile. The reporter's working app being
Enduser makes an account-profile mismatch the first thing to check. It does
not prove which profile they selected, whether they have another entry, or why
the previous day worked. The actual rejected routing fields remain unknown.

## Next useful reporter check

Confirm the account type selected for the affected integration entry. If unsure,
a fresh setup flow explicitly selecting **S-Miles Enduser (experimental, read
only)** can test authentication/discovery; it can be cancelled before creating
an entry, so no existing configuration needs to be deleted. Do not suggest
trying each profile or repeatedly submitting credentials. If their existing
entry already says Enduser, identify which entry produced the log and compare
the new fixed stage/reason line before making a routing change.

Do not request a password, token, raw region response, account address, full
station URL or unredacted config entry. A new diagnostic after successful setup
already includes only the allowlisted `client_profile` label for this question.

## Implementation boundary

No justification currently exists to relax trusted authentication hosts, guess
another DC, skip Home validation, auto-switch profiles or retry password/hash
algorithms. Enduser is already supported in v0.6.1; no beta is required merely
to select it. Any remaining failure needs to be classified from that explicit
profile's result. No fix success is claimed for the reporter.

Protocol references and source provenance are in
[enduser-app-protocol.md](enduser-app-protocol.md) and
[android-app-protocol.md](android-app-protocol.md). This investigation uses the
existing source-backed login paths and synthetic tests, not real account calls.

## Follow-up: successful v0.6.0 comparison (2026-11-15)

The reporter subsequently tested v0.6.0. Their initially attached log has fixed
`missing_uri` warnings on both existing Live-URI routes, not `invalid_auth_routing`.
The log was read privately and is not copied into the repository. It describes
a later station-data failure, not a demonstrated authentication failure.

Their latest comment says v0.6.0 now works in the morning, while upgrading to
v0.6.1 fails again. Treat this as reporter-observed version-dependent behavior,
not an independently observed account test. It strengthens the regression case;
it does not reveal which routing field was rejected, establish all data quality,
or prove why the earlier Live URI was absent. Do not label that absence a night
shutdown or a rate limit without evidence.

The separate Enduser setup reportedly creates a station device without individual
HMS/module devices. That matches the current station-only feature boundary and
does not establish that the previously working Home path should be abandoned.

### Rechecked manufacturer evidence

The archived Home V2.13.0 APK's readable normal-login chain is:

`LoginActivity.O0` -> `Auth3PreManager.g` -> `EasyRequest.b` ->
`IAM_PUB_3_AUTH_PRE_INSP` with `{u:account}` -> callback `R0` ->
`AppConfigUtil.v` -> `LoginActivity.B0` -> `IAM_PUB_3_AUTH_LOGIN`.

Bundled route metadata maps pre-inspection to domain ID 1 (euapi). The normal
activity does not introduce `IAM_C_REGION_C` before that challenge. By contrast,
`OemLoginActivity.s0` explicitly sends `{email:account}` through `IAM_C_REGION_C`
and stores returned user-center data in its callback. The OEM request's presence
does not establish a mandatory precondition for the normal Home login.

The public manufacturer entry and its actually linked main script were retrieved
again without an account on 2026-11-15:

| Source | SHA-256 |
| --- | --- |
| `https://global.hoymiles.com/website` | `dc0ec5022780bd53c8a4cd819d41bcfef62be58e6c9b3c2d26cce4d4cef88b1d` |
| `https://static.hoymiles.com/cdncache/website/js/index-BTRAEMTt.js` | `093c693196cf7966d1565ee7cca170d65f7de28ba5d9078f911ec9e164b64164` |

Both are byte-identical to the 2026-11-09 sources in
[login-routing-0.6.1.md](login-routing-0.6.1.md). The main script still defines
`loginPreInsp` and `loginV3`, with no `region_c` string. This is corroborating
web evidence, not a captured request from the reporter's account.

Rechecked archived JADX source hashes, paths relative to `sources/`:

| Source | SHA-256 |
| --- | --- |
| `com/balcony/host/ui/LoginActivity.java` | `d197eab7dfb115e6633426a5e2b7dfd2e25091faae95b06e3fa70d68619108d3` |
| `com/balcony/utils/mmkv/Auth3PreManager.java` | `489be9c394cbe390a14529a6eec4e08e779356673e22566a781a6af9cee17f1d` |
| `com/balcony/host/ui/OemLoginActivity.java` | `85eb74b019f9cf0efe01c66ed2fa4129df64ea27736f0c70acebb53e74e58483` |

APK provenance/signature limits remain those recorded in android-app-protocol.md.
No app was installed or executed and no real account or device was called.

### Candidate correction and regression checks

The narrowly justified candidate is to restore the direct, documented normal
Home pre-inspection entry, then continue selecting the login host from the
fresh validated challenge DC. This removes the new prerequisite rather than
adding a fallback after arbitrary region errors. Preserve explicit hash-version
selection, challenge/nonce validation, trusted hosts, the one-hop redirect policy,
previous-token omission, account pacing/pauses and the v0.6.1 session-expiry fixes.
Do not revert the entire client or switch accounts automatically to Enduser.

An isolated synthetic comparison using the repository's v0.6.0 login method and
the current client confirmed: current Home login rejects a success envelope with
an empty region-data object, while the older direct path accepts a valid v2/DC0
challenge and synthetic token without any region request. HTTP was mocked. The
empty object is only a reproducible example of the extra dependency, not the
reporter's captured response.

Before implementation/release, test direct initial pre-inspection; DC0/1/4
challenge-selected login; unknown/missing DC/version; regional auth redirects;
no password/host/profile trials; shared sessions; expired tokens and rate pauses;
and unchanged Installer/Enduser transport. Actual recovery of the original entry
still requires the reporter's test. No runtime change or new beta was prepared
as part of this investigation.

## v0.6.2b2 implementation

The separately authorized b2 change removes the unconditional `region_c`
prerequisite from normal Home login. It starts directly at the previously used
euapi pre-inspection endpoint and still requires a supported explicit version,
valid challenge data and known DC before deriving the subsequent login target
from local constants. No response URL field selects the password destination.

This is a single normal-login sequence, not a fallback after a failed region
operation or a sequence of profile/host/hash trials. Installer and Enduser retain
their original direct neapi entry and separate sessions. Existing token clearing,
TLS, authentication redirect limits, expiry handling, account request budget,
login cooldown and server pauses remain intact. Live/data endpoints and missing-
URI handling are unchanged. Current Home logins no longer request `region_c`.

Local tests: 1,267 HA tests on HA 2026.11.0 and 56 unit tests pass. Obsolete
region-prerequisite fixtures were replaced with direct-entry/challenge-DC checks;
existing expiry, redirect, algorithm, profile and privacy checks remain. The
transport tests include stale cached DC/token, DC0/1/4, invalid challenge DC,
an unrelated untrusted URL field, authentication rejection, HTTP 429 and timeout,
single reauthentication after expiry, and no automatic command/write replay.

Successful operation on the affected account remains unconfirmed. Test b2 with
the original Home entry that works under v0.6.0, without changing its profile or
recreating it. If login progresses to `missing_uri`, report it separately instead
of assuming the removed routing prerequisite still failed. No real account or
device requests were made by the agent.
