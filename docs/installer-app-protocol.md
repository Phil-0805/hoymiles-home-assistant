# S-Miles Installer protocol inspection — 2026-11-10

## Provenance and limits

The official [Google Play listing](https://play.google.com/store/apps/details?id=com.hm.hemaiInstall1)
identifies Hoymiles' Installer app as **com.hm.hemaiInstall1**. The manufacturer's
old app page redirects to the public cloud website; no direct manufacturer APK
link was found in that entry or its loaded core bundle. This is not a claim
that no manufacturer download exists elsewhere.

The archive used here comes from the linked download on
[APKPure](https://apkpure.net/s-miles-installer/com.hm.hemaiInstall1/download):
`https://d.apkpure.net/b/XAPK/com.hm.hemaiInstall1?version=latest`.
The actual XAPK manifest **and base APK badging** both identify **V3.14.0**, code
**2026102718**, package **com.hm.hemaiInstall1**. Download-page version text was
not used as the sole version authority.

| Artifact | SHA-256 |
| --- | --- |
| XAPK | `16633c1aa3a5f3d202c794b0126684acc80d0320d66e8ab3d9e9dd3ac73b0199` |
| Base APK | `1b4b324d3638c6bbf4a5eff29c20bc0f0f9be7766ff9da383cb62f30bc56df9e` |
| Bundled `assets/domain/online_domain.json` | `839c773cb08a6e92b0bade03e8fce5f387cea96da9eda96f9830fd33fbcbcc46` |

`apksigner verify` verified archive signatures; the signing-certificate SHA-256
is `aa4c9154ef49696626261d7a3f391e3476faa6c89dd294de40958ecefd9bd909`.
This checks internal integrity, **not independently established publisher
identity**. This remains a third-party-mirror APK. No Play account was used.

The app was never installed or executed. JADX 1.5.6 produced partial Java
output with 309 errors across unrelated classes. The methods cited below are
readable. The Argon2 helper's synthetic-constructor warning was cross-checked
using single-class fallback instruction output before relying on its parameter
values. No manufacturer source, APK, private screenshots, credentials or real
account captures are added to the repository. Only our protocol summary and
synthetic tests belong here; archives/decompilation remain outside it.

## Login call chain

`com.hoymiles.activity.user.LoginActivity.L0()` clears cached DC before calling
`HttpUtils.v` with `IAM_PUB_3_AUTH_PRE_INSP`. `HttpHelper.w(account)` serializes
exactly `{u: account}`. The bundled route is
`/iam/pub/3/auth/pre-insp`, domain id 0, **https://neapi.hoymiles.com**.
This Installer path does not perform the Home/OEM `region_c` request first.

`HttpUtils.F/G` supplies JSON, UTF-8, language and `HttpUtils.H()`'s User-Agent:

```text
smc/ad/3.14.0/159/<dc>
```

This differs from the existing Home `sma/ad/...` identity. Values were resolved
through `BuildConfig` (`V3.14.0`), `ExifInterface.X4` (literal `V`, removed),
`EAboutUsKey.HOYMILES_COM` (159) and `TlbConst.TYPELIB_MINOR_VERSION_SHELL`
(literal `0`, used when no DC is stored). The pre-inspection callback caches
the returned DC and invokes `AppConfigUtil.t()` before login, loading routes
with app_type **2**, not Home app_type 1.

`LoginActivity.M0()` explicitly selects from the challenge's **v**:

| v | Installer calculation |
| --- | --- |
| 1 | Lowercase hexadecimal MD5 of the UTF-8 password |
| 2 | MD5 hex + dot + padded Base64 of SHA256(UTF-8 password) |
| 3 | Argon2id v19, UTF-8 password, hex-decoded salt, iterations 3, memory 32768 KiB, parallelism 1, length 32, lowercase hex |

The v1 rule differs from the existing Home v1 path. `StringUtilsDawn.b0/c0/e0`
and `ToolsUtil.d` establish the legacy calculations; the Base64 helper defines
`=` padding. `Argon2IDUtil` and `Argon2IDUtilKt` establish v3; its call operands
were separately checked in fallback output. `HttpHelper.x()` sends `{u,ch,n}`.
Missing/unknown versions are not a reason to try another hash.

The login response supplies `data.token`. A nonzero interactive account flag is
not supported by this integration; the app explicitly diverts flag 1 to password
change after authentication. Our candidate stops before password submission
when a nonzero/invalid flag is supplied and asks for completion in the official
app. It does not attempt account recovery or password changes.

This **proves protocol differences**, not that the UA difference is the precise
cause of rupacheco's rejection. His updated warning establishes successful DC0
region discovery followed by pre-inspection rejection with the Home profile;
it still does not expose the server's actual reason or auth version.

## Public routing verification

The following exact, account-free request is established by `AppConfigUtil.t`:
POST `https://neapi.hoymiles.com/dict/pub/0/dyn/uri_s` with
`{app_type:2,h:"-1",dc:"0"}` (and separately `dc:"1"`). The inlined percent-layout
constant was resolved to literal `h`; cached DC is read as a string.
No account/password/token or device operation was involved.

| Returned public configuration | SHA-256 |
| --- | --- |
| DC0 | `e6cecfd5123ed6e8c2e4f8d3787266930676f90d447fff4d453ea69669cd4d3e` |
| DC1 | `2a5285dd8c9ec3c1054c3cc109fcbff5692cc50d9ef985617505fff6fef4c500` |

Both responses map the Installer pre-inspection/login and the station routes
used below to domain id **0/neapi**. Do not substitute Home's DC1/euapi login
rule into this profile. `HttpUrlManager` resolves keys through `DomainManager`;
special station-AK handling is separate. These observations do not establish
Installer DC4/India support. The candidate accepts only explicit challenge DC0/1
for Installer, retaining the DC in the UA, and never tries another host after a
rejection. Existing one-hop, same-operation, explicit HTTPS auth redirects and
account budgets remain in force. Other API redirects remain blocked.

## Verified read-only data subset

| Operation | Manufacturer evidence / transport |
| --- | --- |
| Device tree | `EquipListActivity.X0` → `HttpHelper.y1` → `PVM_STATION_SELECT_DEVICE_OF_TREE`, POST `/pvm/api/0/station/select_device_of_tree` with `{id: sid}`; array of `StationTreeBean` with id/type/children; microinverter enum is 3 |
| Live server address | `PowerTab1FragmentV3Power.a1` → `HttpHelper.L2`, POST `/pvm/api/0/station/get_sd_uri` with `{sid}`; response has `uri` |
| Live sample | `i1` posts `{m:0,t:1}` to that URI; its callback unwraps `StationDataSecondPowerAndRefluxBean` with `con`, `flow`, `power`, `dly`; PV/grid/load fields are numeric strings in watts |
| Energy totals | Fragment read → `HttpHelper.P1(sid,true)`, POST `/pvm-data/api/0/station/data/count_station_real_data` with `{sid}`; `StationDataBean.today_eq/month_eq/year_eq/total_eq`; `Utils.L/N` formats input as Wh, scaling only its display |

The candidate uses the separately inspected manufacturer **web** station-list
operation `/pvm/api/0/station/select_by_page`, `{page,page_size}`, also included
in the Installer route table. Its rows use station `id`, not Home `sid` or nested
device IDs. The current APK's primary `PowerStationFragment` instead uses
`station_v3/next_p_a` and an `ntk` continuation token. We do not claim to clone
that full installer list/filter UI or make up its classification filters.
A rejected list does not select another profile; the established manual-ID
setup path is retained, with device-tree access validation before creation.

Installer station/device IDs and tree shape are validated before use; conflicting
duplicate identities and supplied mismatching station IDs are rejected. Only
explicit `children` nodes become inverter entities, rather than arbitrary
metadata objects. The live URI must pass the existing trusted-Hoymiles HTTPS
check. Missing/invalid/rejected URI replies do not trigger a Home fallback.
Numeric power/Wh values feed the existing read model without guessed scaling.
The existing minimum live interval, server-directed delay, energy freshness and
account-wide request pacing remain unchanged.

## Experimental implementation and test instructions

An optional **Account type** selector offers Home (the existing default) and
**Installer (experimental, read only)** at setup and reauthentication. Old
entries without the field retain Home behavior. A reauthentication profile
change updates the existing entry, preserving username/station identity and
entity IDs. No automatic profile guessing or alternate-profile retry follows
an arbitrary rejection. Choosing Installer is an explicit user decision.

Home and Installer keep separate tokens and DC state while sharing account
HTTP pacing, server pauses, login lock and retry cooldown. Known profile labels
may appear in sanitized diagnostics; raw server text, credentials, nonce, salt,
hashes, tokens, URLs and station identifiers are excluded.

Installer support is deliberately a **monitoring subset**: live readings,
energy totals and discovered inverter identity/model. Battery mode, cutoffs,
output control, heating/display controls, battery temperatures, module charts
and additional inverter telemetry are not enabled. Their Home routes/commands
are blocked at the HTTP boundary and their background readers are not scheduled;
unsupported option toggles are omitted. Even stored control permissions cannot
enable these operations in the Installer profile.

For testing v0.6.1b3: select the Installer
account type, sign in once, choose/validate the plant and compare live PV/grid/
load and energy totals against the official app. Report login, discovery,
validation and live data separately. For a failure, share only fixed diagnostic
warning lines; no raw capture or credentials are required. Real-account testing
is still needed: synthetic success does not prove server permissions or that
rupacheco's account is fixed.

This implementation is included in the authorized **v0.6.1b3** experimental
prerelease. No issue comment, authenticated request, device command or app
execution was performed by the agent.

## Follow-up — 2026-11-11

The account confirmation requested above has since arrived in issue #16:
rupacheco reports successful access with v0.6.1b3 after selecting Installer.
The maintainer requested an app comparison of readings and energy totals;
that further confirmation is still outstanding. Earlier statements about a
pending account fix describe the evidence at the time of b3 preparation.

A renewed static review of the identical APK and the current public web entry
found concrete extra monitoring routes, a float64 chart schema incompatible
with the existing Home float32 decoder, and a distinct action-1013 storage
settings path. See [capabilities, call chains and proposed b4 scope](installer-capability-review.md).
These are research findings; the existing runtime restrictions and version
remain unchanged.
