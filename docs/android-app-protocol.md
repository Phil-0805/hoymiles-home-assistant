# Android app protocol inspection — 2026-11-05

## Provenance and limits

The downloaded package identifies itself as `com.hm.balcony`, **V2.13.0**,
version code **2026101400**. The download page listed older releases, so the
version above comes from the actual archive manifest, not its cached web text.

Source: [APKPure download page](https://apkpure.net/s-miles-balcony/com.hm.balcony/download),
using its linked `d.apkpure.net/b/XAPK/com.hm.balcony?version=latest` download.
This is a third-party mirror. Publisher signature authenticity was not
independently established; the hashes identify the exact analyzed files:

- XAPK SHA-256: `1ef8c558938962a67deef80af108d89a0f649b6cc0610de26f25641364c10681`.
- Base APK SHA-256: `0b0e12fcc3bd14bbb10188a1055eed06bfac44e9e332f8d6b5597a5d69e9a633`.

The app was not installed or run. JADX 1.5.6 produced partial Java output; some
unrelated classes failed decompilation. The methods below were readable. No
credentials, live account requests, device writes or authentication bypass were
used. APK binaries and decompiled sources remain outside the repository; only
this protocol summary and synthetic tests are tracked.

## Separate charge/discharge cutoffs

`com.balcony.device.ui.DisChargeActivity` (classes2.dex):

- `f0()` reads **action 1537** via `CommandRequestHelper.K0` with empty `data`.
- `g0()` reads `sl` into the lower slider and `sh` into the upper slider.
  JADX displays `sh` via an inlined PercentLayout constant; that constant's
  declaration was checked and is literally `sh`.
- `c0()` writes both `sl` and `sh` via `CommandRequestHelper.e1`, action **1537**.
- The range is 10–100%, lower slider maximum 70%, upper slider minimum 50%,
  and a minimum interval of 10 percentage points. App defaults (20/95) are not
  treated as returned settings or permission to write.

`StationDeviceInfoUtil.h()` supplies the selected device's `sn`; `f()` supplies
its `dtu_sn`. `CommandRequestHelper.Z()` builds:

```text
read:  {action: 1537, dev_sn, dtu_sn, data: {}}
write: {action: 1537, dev_sn, dtu_sn, data: {sl, sh}}
```

When the selected device has no DTU address, `StringExtKt.c()` converts null to
an empty string. The implementation mirrors that empty `dtu_sn`; it does not
reuse the web lighting drawer's fallback to the device serial.

`K0`/`g1` use the READ_C/WRITE_C route keys, not the web client's device-settings
route. `assets/domain/online_domain.json` resolves them to:

- `/pvmc/api/0/station_ctl/read_c`
- `/pvmc/api/0/station_ctl/write_c`
- `/pvmc/api/0/station_ctl/setting_status_c` with `{id}` for polling.

No station `sid` is added to the action-1537 data. Status `data` may itself be
JSON text. This is separate from action 83's mode-level `soc_l`/`soc_h`.

## Output power

`StationSystemBmsBleSettingOutputPowerActivity` uses action **84** for its read
and write. The write data has `power` in watts; `HttpHelper.y()` adds the station
`sid`. Readback supplies `power` and `max_power`. The activity validates at least
100 W up to that returned maximum before writing. The current maximum is not
permission to raise the configured station upper limit.

`OutPutPowerActivity` delegates the newer phase controls to
`PhaseConstraintLayout`. That view uses **1532**, with `type` and
`power_total`/phase power fields. Its output readback names are
`out_power_total`/`out_power_a`/`out_power_b`/`out_power_c`.

The web client's separate upper-limit configuration **515** is documented in
[output power settings](output-power-settings.md). No new output-power HA entity
is added from these static findings alone. Station/phase capabilities and the
app result still need to be checked before shipping that control.

## Login redirects — b6 investigation

A v0.5.2b5 issue report shows `stage=login_challenge reason=redirect_rejected`.
This establishes that the request was redirected before password challenge
calculation; it does not identify the destination or prove all login reports
share this cause.

In the same archived V2.13.0 APK, `com.balcony.utils.RedirectInterceptor` handles
302 and 307 responses with an absolute Location by rebuilding the original
request with the new URL. `com.balcony.App` installs this interceptor while
turning automatic redirects off. Thus the inspected client preserves the
request method/body for these statuses. `DnsManager` lists production hosts
including `euapi.hoymiles.com`, `neapi.hoymiles.com` and `indapi.hoymiles.com`.
These are source observations, not a capture of the affected user's destination.

The b6 candidate allows one manual 302/307 redirect only for auth pre-inspection
or login, to the same operation path on those exact HTTPS API hosts. It rejects
queries, fragments, URL credentials, other ports, test/CDN hosts and second hops.
The original POST body is preserved; previous Authorization tokens are omitted
from both public auth requests. Other API redirects remain blocked. Every hop
uses the existing account budget and rate-limit handling. Logs record fixed
policy labels and HTTP status, never Location contents. This deliberately
restricts the Android client's broader behavior. Real affected-account testing
is required to confirm whether its redirect falls within this policy.

## Login redirects — follow-up inspection, 2026-11-06

The b6 report from gillesBdl still shows HTTP 307 with `blocked_target` at
`login_challenge`. The Germany/own-account statement in issue #16 belongs to
ElchCarlo, a different reporter; it does not establish gillesBdl's account region.
The French Home Assistant log labels do not establish a cloud region either.

The same archived APK was checked again; both archive hashes above still match.
The readable call chain is `LoginActivity.O0` → `Auth3PreManager.g` →
`EasyRequest.b/c` → `HttpUtils.h/i/b` → `HttpUrlManager.a` →
`DomainManager.g`. Pre-inspection sends only `{u: account}`. The bundled
`assets/domain/online_domain.json` maps both v3 auth operations to domain id 1,
`https://euapi.hoymiles.com`, with the same paths used by the integration.
`HttpUrlManager` concatenates the configured domain and URI for these operations;
its special station-AK handling does not apply to login.

`HttpUtils.k/l/n` supplies JSON/UTF-8, a language label and the app user agent.
The latter is built from the installed version, tenant and stored user DC, with
DC 0 when no user is stored. The inspected tenant constant resolves to 159.
The integration currently advertises app version 2.12.1; this differs from the
archived app's 2.13.0, but no evidence links that difference to this 307.
`Auth3PreManager` also supports legacy challenge versions; that is a separate
compatibility observation after successful pre-inspection, not an explanation
for an HTTP redirect rejected before reading a challenge.

The app can replace bundled routing through `AppConfigUtil.v` and
`DomainManager.m`. The exact public, unauthenticated configuration request was
verified from the APK: POST `/dict/pub/0/dyn/uri_s` on `euapi`, with
`{app_type: 1, h: "-1", dc: 1}` when no configuration/challenge is stored.
The inlined `PercentLayoutHelper` constant was resolved to the literal `h`.
One request without an account, password or token on 2026-11-06 returned status
0 and the same auth routes and domains as the archive. The additional `eud0`
domain is not mapped to auth by this result and is not evidence to enable it
as a login destination. Response SHA-256:
`dd8c03a30936c3a4890c1e2faa1d1d1cd6d6a5082c6870c0a4f7ddd4014ece32`.

The currently delivered public web entry was also fetched from
`https://global.hoymiles.com/website` on 2026-11-06. Its configuration names
`neapi` as `serviceHost`, `euapi` as `euHost`, and `indapi` as `indiaHost`.
The linked `https://static.hoymiles.com/cdncache/website/js/index-BTRAEMTt.js`
defaults Axios to `serviceHost`, uses the same v3 auth paths, and can override
the base for stored DC/OEM state. These are static defaults, not an observed
affected-account request. Entry SHA-256:
`76328c3b1e03e0a86e30d08fc91b5691262ac17812f275d9a1184ce50a9786eb`;
linked JavaScript SHA-256:
`093c693196cf7966d1565ee7cca170d65f7de28ba5d9078f911ec9e164b64164`.

Before the subsequent browser capture below, an account-free HEAD request to the documented euapi pre-inspection path returned
HTTP 200 without a redirect. It does not reproduce an account-bearing POST.
The maintainer reports successful browser login; the affected reporter's
redirect destination remains unknown. No real account or device was accessed
by the agent, no redirect restriction was relaxed, and no verified login fix
can yet be claimed. Private captures and vendor binaries/sources stay outside
the repository.

## Observed auth redirect marker — b7 fix, 2026-11-06

The maintainer supplied browser network screenshots from a successful login.
They show POST to `https://neapi.hoymiles.com/iam/pub/3/auth/pre-insp`, HTTP
307 with Location `https://euapi.hoymiles.com/iam/pub/3/auth/pre-insp?times=1`,
then HTTP 200 at the destination. The marker is observed server output;
its meaning is not inferred. The private screenshots are not stored in the repo.

B6 rejects this exact target because it rejects every nonempty query. The local
fix allows only the literal raw query `times=1`, alongside the existing empty
query, for a same-operation redirect between the three known HTTPS auth hosts.
The same check covers both auth operations, matching the APK's shared redirect
interceptor; only pre-inspection was captured in these screenshots. Other values,
encoded variants, duplicates and additional parameters stay blocked. The source
must still have no query. There is still only one hop, POST/body are preserved,
old Authorization tokens are omitted, and other API redirects stay blocked.
No change to start host, user agent, challenge calculation or polling is needed.

This reproduces a concrete b6 defect using synthetic responses. The screenshots
are from the maintainer's account, not gillesBdl's; confirmation that the same
marker causes that reporter's 307 remains outstanding. No real account was
accessed by the agent. This targeted change is included in b7.

## Light/display Never timeout — b7

`com.balcony.bean.enums.LedTimeType` in the archived V2.13.0 app defines times
60, 300, 900, 3600 and `NONE = 65535`. The settings activity writes `getTime()`
to both `slot` and `sot` and reads each via `findByTime`. This establishes the
Never sentinel independently of the screenshot. The app's fallback to MIN_15
for unknown values is not adopted as evidence of a real device setting.

## B8: authentication protocol versions

The reporter now reaches `stage=login`, with `cloud_status=1` and an
authentication rejection. That is later than the previous blocked redirect;
it does not establish that the password is wrong. The maintainer's separate
working web account returns `v=3`, `dc=1`, `f=0`, `t=159`. The affected reporter's
challenge version is still unknown.

The previously archived APK's `Auth3PreManager.e` selects Argon2 only for
`JgLoginUrlBean.v == 3`; otherwise it calls `ToolsUtil.e`. That helper constructs
`MD5(password UTF-8).hex_lower + "." + Base64(SHA256(password UTF-8))`.
`StringUtilsDawn.T` was followed through its leading-zero branch; the inlined
`TlbConst.TYPELIB_MINOR_VERSION_SHELL` resolves to the literal `"0"`.
`com.fuqianguoji.library.ali.Base64.encode` produces ordinary padded Base64.
`HttpHelper.B` sends `{u, ch, n}`, omitting a null nonce through JSONObject's
standard null handling. `Argon2IDUtil` and `Argon2KtResult.f(false)` confirm the
v3 parameters and lowercase raw hash already used by this integration.

The current web bundle archived above independently confirms this: `useLogin`
reads `{a,n,v,dc,f}`; `v=1` and `v=2` call `encryptPwd`, which builds the same
MD5/SHA-256 composite, whereas `v=3` calls `encryptPwdV3` with Argon2id,
iterations 3, memory 32768, parallelism 1 and hash length 32.

B8 requires an explicit supported challenge version. It keeps
v3 unchanged, supports the documented v1/v2 composite, preserves the original
password bytes including Unicode/whitespace, and never tries another algorithm
after rejection. Missing/unknown versions stop before login. A nonce is required
for v3; a missing/null legacy nonce is omitted, matching both clients' JSON
behavior. Diagnostic failures include only a known numeric `auth_version`, not
the challenge, nonce, salt, password or hashes. The authentication error text now
states rejection rather than asserting incorrect credentials.

Synthetic legacy vectors were independently calculated with Node's crypto API;
tests also cover unchanged v3 worker parameters, malformed challenges, no
fallback/downgrade attempts, redirect transport and privacy. This fixes a
source-proven compatibility gap, but does not yet prove the cause of the
reporter's authentication rejection. No real account was accessed by the agent.

## B9: account-selected authentication destination

The affected reporter supplied a redacted successful web pre-inspection response:
`v=3, dc=0, f=0, t=159`. This rules out the missing v1/v2 support as the cause of
that reporter's rejection. The maintainer's working account instead uses dc=1.
Neither DC value establishes a user's country of residence.

In the same archived web bundle, `useLogin` reads dc before login. The default
`serviceHost` is neapi; dc=1 selects euapi and dc=4 selects indapi. The APK's
`LoginActivity.R0` calls `AppConfigUtil.v` between pre-inspection and login,
passing the challenge's dc to the public dynamic route configuration lookup.
`HttpUrlManager.a` subsequently resolves the login through that configuration.

The exact public configuration read documented above was repeated without an
account/token for dc=0. It returned both auth operations with did=0, resolving
to `https://neapi.hoymiles.com`; SHA-256:
`44ea6f5c31dd3312a021bb843f19ba80a70122ec9e021da1cef6a6f5ca002163`.
The earlier dc=1 response maps the same operations to did=1/euapi; its hash is
recorded above. A separate dc=4 configuration read returned null auth did values,
so it does not independently confirm Android routing for dc=4. The explicit
dc=4→indapi rule is supported by the web client, not that configuration response.
DC=4 configuration response SHA-256:
`1b9e8e36467bdb81d7498a50a96c65dcf8cca93e3dbe9c6f365d34b7fc3db71c`.

B8 always starts both operations on euapi. B9 keeps the
app's initial euapi pre-inspection and selects only the subsequent login base
from the freshly returned dc: 0→neapi, 1→euapi, 4→indapi. Missing, malformed or
unknown codes stop before login; no server is tried as a fallback. No extra
configuration request is added to the integration. Telemetry routing remains
unchanged. The v3 hash, nonce and original password bytes remain unchanged.

All three exact auth hosts/paths are recognized as public auth requests, so
region-selected login omits previous tokens and preserves the existing bounded
redirect rules, TLS verification, account budget and rate handling. Failure logs
may add only the known numeric auth_dc. Synthetic tests cover exact destinations,
all protocol versions, fresh region changes, invalid codes, token omission,
redirects, privacy and no retries to a different host/algorithm.

The dc=0 mismatch is source-proven and consistent with the supplied report. It
does not yet establish a successful login at the affected account; no real
account requests were performed by the agent. The correction is included in b9.
On 2026-11-06 the affected reporter confirmed successful login and incoming
values with b9. Data accuracy and screen presentation remain under review;
this confirms that account's login/live connection, not every account or metric.
