# S-Miles Enduser feasibility review — 2026-11-13

## Result and scope

An explicit Enduser monitoring profile is a useful extension of the existing
Installer infrastructure. It must retain its own client identity and session;
renaming Installer or treating every owner as a Home account is incorrect.
Shared transport does not establish identical account permissions.

Issue #47 identifies the working iOS app as S-Miles Enduser, App Store ID
1544760866, version 3.14.0. The reporter confirms the same login, live readings,
an originally owned plant and a checked station ID. Their Home-profile login
succeeds but discovery and manual validation return no entries; the Installer
attempt is described only as unable to communicate. Its exact failure stage is
not yet established. Client differences below are candidates, not proof of the
server-side cause of that failure.

The reported HIS-6L-G3 is a hybrid inverter, not an HMS microinverter. See the
[manufacturer's hybrid installation guide](https://www.hoymiles.com/uploadfile/1/202603/77352ce108.pdf).
Supporting its monitoring requires checking the storage/hybrid data schema as
well as login. The initial review was research only. The subsequently authorized
b12 implementation is described below. No real-account request or device
command was performed by the agent.

## Provenance

The official [Google Play listing](https://play.google.com/store/apps/details?id=com.hm.hemaiClient1)
identifies Enduser as `com.hm.hemaiClient1`. The manufacturer's legacy app page
does not expose a direct APK through the retrieved HTML. The archive inspected
here is therefore a third-party-mirror download, not a manufacturer binary
whose publisher identity has been independently verified:

- Listing: <https://apkpure.net/s-miles-enduser/com.hm.hemaiClient1/download>
- Download: `https://d.apkpure.net/b/XAPK/com.hm.hemaiClient1?version=latest`
- Retrieved: 2026-11-13. XAPK manifest, APK badging and `BuildConfig` all report
  **V3.14.0**, code **2026102718**, package **com.hm.hemaiClient1**. Indexed page
  text advertising 3.13.0 is not the version of the delivered archive.

| Artifact | SHA-256 |
| --- | --- |
| XAPK | `600fb7421fc86e472b7c9b075fe39a722a58c5a518a6de14b8ca98cf705d0778` |
| Base APK | `4e6e176aa4f16ef1c0bfb60532d765f97a8dd9c7b0b268871ce6f42363c886bb` |
| `assets/domain/online_domain.json` | `839c773cb08a6e92b0bade03e8fce5f387cea96da9eda96f9830fd33fbcbcc46` |

`apksigner verify --print-certs` succeeds. Certificate SHA-256 is
`ee95aac0876547774f49e136ccc3af3983abca499b827c3fd297dbdcf2031f17`.
This verifies internal signature integrity, not independently confirmed publisher
identity. The app was not installed or executed. Android evidence does not
prove that the iOS implementation is byte-for-byte equivalent.

JADX reports 309 errors overall. Only readable call chains are used here;
the Argon2 helper's constructor warning was separately checked against fallback
instruction output. Binaries and decompiled sources remain outside the repo,
under `/private/tmp/hoymiles-enduser-research-20261113`.

## Authentication and routing

| Property | Enduser | Existing Installer |
| --- | --- | --- |
| HTTP client identity | `smo/ad/3.14.0/159/<dc>` | `smc/ad/3.14.0/159/<dc>` |
| Dynamic route app type | **3** | **2** |
| Initial pre-inspection | neapi, no Home `region_c` request | Same basic sequence |
| Challenge v1 | MD5 of UTF-8 password, lowercase hex | Same |
| Challenge v2 | MD5 hex + dot + padded Base64(SHA256 UTF-8 password) | Same |
| Challenge v3 | Argon2id v19, iterations 3, memory 32768 KiB, parallelism 1, length 32, hex salt | Same |

Enduser `LoginActivity.L0` clears cached DC and calls
`IAM_PUB_3_AUTH_PRE_INSP` with `HttpHelper.w` (`{u}`). Callback
`AnonymousClass12.b` saves the returned DC and loads configuration through
`AppConfigUtil.t`. `M0` explicitly selects the challenge's v; `HttpHelper.x`
serializes `{u,ch,n}` for `IAM_PUB_3_AUTH_LOGIN`. The successful login supplies
`data.token`. Interactive flag branches exist and must not become password
reset/change automation in HA. Unknown versions must not trigger hash trials.

`HttpUtils.H` constructs the **smo** User-Agent. `AppConfigUtil.t` supplies
`app_type:3`, `h:"-1"` without cached configuration, and the stored DC string.
The bundled domain table is byte-identical to the Installer table, but this
does not justify substituting Installer's app type or UA.

The APK-established public, account-free operation was read with no token:
POST `https://neapi.hoymiles.com/dict/pub/0/dyn/uri_s`, JSON
`{app_type:3,h:"-1",dc:"0"}` and separately `dc:"1"`.

| Public response | SHA-256 |
| --- | --- |
| DC0 | `63590643a82b49c66c015a137742a02db4770fd3eb777ecaf0262926d1596bde` |
| DC1 | `9a5a7d51ff92f146737c80196917f7731272c65f590e683676ce10a60d1d86e6` |

Both map the cited pre-inspection/login, tree, station list, live-URI and energy
routes to domain ID **0**, resolving to **https://neapi.hoymiles.com**.
This does not establish Enduser DC4 support. Do not inherit Home's DC1-to-euapi
login rule or infer account geography from the Malaysian App Store link.

## Plant/device discovery

`PowerStationFragment.L1` normally uses `PVM_STATION_V3_NEXT_P_A`, resolved to
`/pvm/api/0/station_v3/next_p_a`. `HttpHelper.W1` serializes optional name/status/
type/classification filters, page/page_size and the returned `ntk` continuation
token. The callback parses the station page. A separate business-system branch
uses BESM; neither its filters nor its pagination may be guessed.

Our Installer code instead uses the manufacturer-web
`/pvm/api/0/station/select_by_page` operation, which is also in Enduser's route
table. Route-table presence alone does not prove equivalent Enduser list access.
A complete implementation should trace the actual list filter defaults and
continuation contract before claiming app-equivalent discovery. Manual station
validation remains a useful bounded first compatibility test.

`EquipListActivity.X0` calls `PVM_STATION_SELECT_DEVICE_OF_TREE` through
`HttpHelper.y1`, which sends `{id:sid}`; the inlined key is resolved through
`LdAutoCardSettingEsActivity.k1 = "id"`. Route:
`/pvm/api/0/station/select_device_of_tree`. This matches the current Installer
tree request. Tree identities and `children` must remain strictly validated.
Enduser's enum distinguishes microinverters (3), inverters (6), batteries (10)
and other inverter families. A hybrid must not be represented as a fabricated
type-3 device or assigned invented PV ports.

## Live and energy: shared requests, distinct schemas

`PowerTab1FragmentV3Power.b1` and `PowerTab1FragmentV3Es.E1` use
`PVM_STATION_GET_SD_URI` with `HttpHelper.L2` (`{sid}`). Their live readers
`j1` (original name `a1`) and `W1` (original name `D1`) respectively post
**`{m:0,t:1}`** to the returned URI. The route is
`/pvm/api/0/station/get_sd_uri`. Existing HTTPS URI validation remains required.
Callbacks honor server `dly`; there is no basis for faster HA polling.

- Micro-generation view parses `StationDataSecondPowerAndRefluxBean`, including
  `power`, `con`, `flow` and `dly`.
- Storage/hybrid view parses **`StationDataSecondEsBean`**: `es:{pp,gp,lp,bp,sp}`,
  top-level `soc`, `con`, `flow`, `icon`, `t` and `dly`. The activity selects
  the ES view from station classification, not a guessed model prefix.
  `PowerTab1FragmentV3Es.w1` reads those numerical strings, displays powers
  through `Utils.L` and uses flow information for direction graphics.
- `PowerStationActivity` selects ES behavior for classifications 4 (ES),
  5 (power plus ES), and 100 (Qing He). These classes are protocol metadata,
  not proof of the reporter's actual returned classification.

The current HA `telemetry.live_power` only reads **`live.power`**. A local,
synthetic sample with `con:1`, `es.pp:"123.5"` and no `power` block produces
`pv_power_details(...).value == None`. This demonstrates a real implementation
gap for ES-format data, not the reporter's captured server response.
Simply adding `smo` login would leave this gap intact. Fields, units, signed
directions and PV composition need an explicit adapter; do not map `pp/sp` by
name alone, take absolute values indiscriminately, or reuse Home `brs` meanings.

Energy uses `PVM-DATA_DATA_COUNT_STATION_REAL_DATA`, resolving to
`/pvm-data/api/0/station/data/count_station_real_data`. `HttpHelper.P1` sends
`{sid}` for its true branch and adds **`off_real:1`** for false. The power view
uses true; the ES view uses false and also has dated `G1` requests. The current
Installer implementation's plain `{sid}` request is therefore not an exact
clone of the ES view. ES response fields and units require separate tracing
before enabling its energy mapping or derived energy accumulation.

## Recommended implementation boundary

1. Add an explicit **Enduser (experimental, read only)** profile. Share account
   pacing, HTTPS/redirect checks and low-level Cloud transport with Installer;
   keep independent token/DC state and the evidenced Enduser UA. No automatic
   Home/Installer/Enduser retry sequence after a rejection.
2. Cover challenge versions and exact requests, token separation, changed
   profile/unload, malformed responses and empty discovery using synthetic tests.
3. Implement station classification and an explicit ES live adapter with proven
   units/directions, finite-value checks, freshness and no missing-to-zero policy.
   Verify energy response mapping separately. Keep unknown devices/fields absent.
4. Start device testing with login, plant validation and station monitoring.
   Compare readings against the actual Enduser app before declaring HIS support.
5. Keep Home battery/output/heating/display commands and unsupported chart
   readers blocked. Controls require their own complete request/address/range/
   readback analysis; this review is not a basis to enable them.

The result supports building the profile, but not promising that changing a
User-Agent alone will fix issue #47.

## B12 implementation and tester scope

The separately authorized implementation adds `client_profile=enduser` to setup
and reauthentication. Identity and entity IDs remain unchanged on a profile
switch. Enduser keeps a separate token/DC session, sharing only account pacing,
server pauses, login lock and cooldown with Home/Installer. Runtime uses the
fixed routes verified against the public app-type-3 configuration, without an
extra dynamic-configuration request or alternate-profile retries.

Discovery follows `station_v3/next_p_a` with the app's unfiltered defaults:
`{classify:0,page:1,page_size:10}`. An optional, bounded `ntk` is passed on when
present; empty/absent tokens are omitted as in the app. Page numbers advance;
nonadvancing nonempty pages and the 20-page cap fail rather than silently
truncating the list. No device ID is substituted for a station ID.

`station/find` with `{id}` supplies the selected station's classification,
checked against its exact ID and cached per client session under a lock.
Only classifications 1 and 4/5/100 currently have an adapter. Other types
produce a specific unsupported-plant setup message. Manual-ID setup performs
the same check. A new login invalidates cached classification; a target change
invalidates the previous station's signed Live URI.

Additional static tracing establishes the ES mapping through
`FragmentPowerTab1V3EsBinding`: `pp` -> `tvSolarKw`, `gp` -> `tvGridKw`,
`lp` -> `tvLoadKw`, `bp` -> `tvBmsKw`. `Utils.L/N` formats the raw values as W
or Wh (scaling only for display). `w1`'s flow branches identify `o` as source,
`i` as destination, and grid=1/battery=2/solar=4/load=10/charger=50.
The adapter uses the app's absolute power magnitudes, with canonical grid
import positive/export negative and battery charge positive/discharge negative.
Missing, malformed, unknown-node or simultaneous opposing flow directions
leave the affected nonzero directional measurement absent. An explicit zero
remains zero without needing a direction. SOC must be finite and in 0..100.
No Home `brs` code is copied or synthesized.

The ES request uses `{sid,off_real:1}` for station totals. Only explicitly
supplied finite, nonnegative `today_eq/month_eq/year_eq/total_eq` are exposed in
Wh. Missing standard generation totals remain unavailable; `pv_eq` and other
period/storage counters are not substituted. Their availability on the HIS
installation still requires a device test.

Enduser sensors are station-level monitoring only. Module entities, Home
status-code/settings sensors and unsupported control options are omitted.
The options page exposes only station timezone; an old stored PV2 selection
cannot override the Enduser adapter. Existing stored control permissions cannot
enable Home readers or writers. No periodic metadata reader is introduced;
Live/totals intervals and shared HTTP limits remain unchanged.

Synthetic tests cover exact login/body/headers, all three supported challenge
versions, profile session isolation and shared pause, pagination, metadata
identity/coalescing/cache reset, target changes, HTTP operation denial,
partial/invalid fields and ambiguous directions, setup/reauthentication, options,
entity selection and actual HA state publication/recovery. Before release,
run the full HA runner, unit suite, syntax and translation-key/diff checks.

The first device test should select Enduser, verify login/discovery/manual
validation separately, then compare same-time PV/load/grid/battery/SOC and
available generation totals against the official Enduser app. Confirm both
import/export and charging/discharging directions. Report fixed diagnostic
stage/reason labels only on failure. An Android static comparison and synthetic
tests do not establish iOS/server compatibility or physical device behavior.

## Local follow-up after b12 feedback

The reporter confirms successful Enduser authentication and plant discovery in
b12, followed by setup failure `stage=station_validation reason=unexpected_response`.
This establishes a failure after selection, but does not identify whether
station metadata or the device tree failed validation. No raw reply or field
types were supplied; the actual cause remains unconfirmed.

The b12 code requires JSON integers for metadata/device identity and assumes
already decoded `data` objects/arrays. The APK instead parses
`StationInfoBean` with `JSON.parseObject` and `StationTreeBean` with
`JSON.parseArray` from `BaseDataResponse.data`; its bundled FastJSON
`TypeUtils.castToInt` explicitly accepts decimal strings via
`Integer.parseInt`. This is a source-proven compatibility gap, not evidence
that the reporter received that particular representation.

The b13 correction accepts bounded embedded JSON once, and canonicalizes
only known Enduser `id/type/station_id/classify` integer fields using the
existing strict decimal-string parser. Boolean, float, nondecimal, oversized,
missing, nonpositive and mismatched identities remain rejected. Device nodes
are copied, not mutated; duplicate/conflicting identities, invalid children
and tree size limits remain enforced. Home/Installer behavior, requests,
permissions and polling are unchanged.

Setup reasons now distinguish `invalid_enduser_metadata`,
`invalid_enduser_station_id`, `invalid_enduser_classification` and
`invalid_enduser_tree`; they contain no server text, identifiers or values.
Malformed embedded JSON still fails, and no repeated decoding is attempted.
No alternate API operation, manufactured ID, arbitrary device choice or
permission bypass is introduced. Synthetic tests exercise object/text
representations, numeric strings, identity rejection and log privacy. Local validation: 1312 HA tests plus 134 subtests on HA 2026.11.0 and 56
unit tests pass; syntax, translation-key parity and whitespace checks pass. A
new device test remains necessary before calling this the reporter's confirmed fix.

## Follow-up after b13 tree failure

The reporter now supplies `stage=station_validation reason=invalid_enduser_tree`.
In b13's actual setup sequence this occurs after exact station metadata and
supported classification have been accepted. It narrows the failure to optional
device data; it does not establish the rejected field or actual tree structure.
No shape-specific tree exception or guessed device identity is justified.

The current Enduser feature scope is station monitoring only. The APK's
`PowerStationActivity` station metadata path and
`PowerTab1FragmentV3Es.E1/W1` station Live path address the plant by station ID;
the Live and energy requests do not need a device-tree identity. Device-tree
parsing is a distinct capability used by device views such as
`EquipListActivity.X0`. Requiring that whole tree for our station-only profile
was an unnecessary startup dependency, independently of which field failed.

The b14 correction validates Enduser setup through authenticated
`station/find` metadata, still requiring the exact requested station ID and a
supported classification. It does not create placeholder devices or fall back
to an arbitrary plant. Neither setup nor runtime station monitoring requests a
device tree. A missing initial Live URI uses the same exact metadata validation,
retains the existing retry cooldown and permits station totals/recovery without
depending on plant-list discovery. A failed or mismatched metadata response
still blocks setup/recovery.

The direct device-tree API and its strict validation remain intact for future
device-specific work. No device or control feature is enabled, and Home/Installer
retain their existing tree validation and discovery. Diagnostics explicitly
state `device_tree_required:false` for Enduser. Account pacing, authentication,
poll intervals and write boundaries are unchanged.

Local validation: **1323 HA tests plus 134 subtests** on HA 2026.11.0 and
**56 unit tests** pass. New tests exercise real HA setup with the mocked HTTP
boundary, matching/mismatched/unsupported metadata, runtime Live/totals without
tree requests, absent-Live startup and recovery, failed metadata authorization,
and rejection of the station-only method for other profiles. The reporter's
actual tree format remains unknown; this correction removes an irrelevant
dependency rather than claiming to repair that unknown format.

## Selected source hashes

Paths below are relative to the archived JADX `sources` directory.

| Source | SHA-256 |
| --- | --- |
| `com/hoymiles/http/HttpUtils.java` | `acc8ba2c8ef7d3b403ff39a9d9f4d121343fa6a9d55154f6353f7faf85c34b7d` |
| `com/hoymiles/v1/util/AppConfigUtil.java` | `04eac6d858090ae4dc9348f942ce542313c24b6492888079ec49e3e744b683e9` |
| `com/hoymiles/activity/user/LoginActivity.java` | `ffdb1f061f68f371e7e865effebfdad23816cbbfd0dc4272edbbb539d23da908` |
| `com/hoymiles/http/HttpHelper.java` | `a63c9eac57c2bef87db3e3cc63f09e33bf8920ecaba29c22d5656b8c6ee5225f` |
| `com/hoymiles/fragment/PowerTab1FragmentV3Es.java` | `f2489e70d1f3bfdc3e703c1d13cc794cdbbc52ffa3c4b50178a638a3d69508f1` |
| `com/hoymiles/bean/StationDataSecondEsBean.java` | `067da93bde29d79775f79f3a34366745996410a369f7dc766b03bbf7e1cd47b7` |
| `com/alibaba/fastjson/util/TypeUtils.java` | `5ecb4f06073314968443a9b450bc2f8f2783e9313bffd8911003d2cbc3f4bf8d` |
