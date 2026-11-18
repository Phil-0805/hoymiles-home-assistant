# Inactive-inverter startup: manufacturer-client review, 2026-11-18

Investigates [#59](https://github.com/Phil-0805/hoymiles-home-assistant/issues/59)
and [#61](https://github.com/Phil-0805/hoymiles-home-assistant/issues/61).
The source investigation below preceded the b5 candidate described at the end.
It is not a reproduction of either reporter's failing cloud response or a
claim that either account is fixed.
No authenticated manufacturer request, account access or device command was made.

## Fresh public web sources

The public entry `https://global.hoymiles.com/website/` was fetched on 2026-11-18,
SHA-256 `93bbbd0369c3f74298459667b38491cf3f747aa04f1d1e198387048a7024aa33`.
It now references `index-C3u2f9MM.js`, rather than the earlier reviewed build.
Every module below was followed from this entry or its actual imports/routes,
not discovered by guessing filenames or API actions. Public JavaScript was
downloaded and read as text, without authenticating or running the application.

Files under `https://static.hoymiles.com/cdncache/website/js/`:

| File | SHA-256 |
| --- | --- |
| `index-C3u2f9MM.js` | `0a5f7e4b9083ed3ff04b63a171eebec7df721c73a963efc8b1f4dd3f984023b4` |
| `index-BWzfS-Sj.js` (plant overview route) | `e04ac6431f87c14dfc9704e8c63bfac2c6c3b77bf96a682f6fd10f0aca6646e1` |
| `index-CsphftcM.js` (devices route) | `e3297f56ca88d2dd5db60cf3b1e718151152ce6f3a1e2a076a614be228369fb1` |
| `index-CC_v82Wy.js` (battery-settings route) | `b8e90c4b0f536d111121e6e5cccbc1d5b674fc715dbc230b9e9c39b5ee4dde40` |
| `plant-BD3PkUfp.js` (imported plant store) | `38612edbe728faea7bd7bc0cda712b071c6d86c03ed6908accba307200215f7e` |

The entry's request wrapper accepts successful HTTP replies with cloud status
`"0"`, then exposes their `data` to callers. `getSecDataUri(sid)` uses the
existing `/pvm/api/0/station/get_sd_uri` request. `getSecData(uri, ...)` posts
`m`, `t:1` and `reflux` to that URI. These web flags must not be transplanted
into the different Home mobile request without evidence.

In the overview's local `m` polling function, a successful data object updates
displayed measurements only when `W.flow` is truthy. Its `W.dly` timer is checked
separately and invokes the same function using the saved URI. This can continue
polling without publishing a new measurement. An empty JS array is truthy; the
test is not a strict HA schema or numeric validator. There is no demonstrated
general conversion of an empty reply into valid zero-power telemetry.

The devices route calls `getDeviceTree` after plant-detail access and on device
filter changes. It does not require a successful `getSecData` callback first.
The tree and micro-detail wrappers remain the existing
`/pvm/api/0/station/select_device_of_tree` and `/pvm/api/0/dev/micro/find`.
This establishes separate UI data paths, not the reporter's nighttime metadata.

The battery settings page reads action 1013 when that page mounts. It is not
evidence that every ordinary PV overview performs that battery-settings read.

## Home Android source and limitations

The previously documented APKPure mirror URL was downloaded again:
`https://d.apkpure.net/b/XAPK/com.hm.balcony?version=latest` (third-party mirror,
publisher-signature authenticity not independently confirmed).
Actual archive manifest identifies `com.hm.balcony`, **V2.14.0**, version code
**2026110903**, not an assumed version from a download page.

- XAPK SHA-256: `939c6ba7f56a494ef4bb39453616a57ac3a09b828274f0638ace5a2e0f4d5392`.
- Base APK SHA-256: `d3f39915b8164045ae4a7107aed3232f6fe8fe201c9f1d7543e5919b26127650`.

These match the earlier inspected archive. Nothing was installed or executed.
Artifacts and single-class decompilations remain outside the repository under
`/private/tmp/hoymiles-night-20261118-*`; only this original protocol summary is
tracked. JADX reported errors in some classes; relevant main-system branch and
BMS/WBPV callback control flow were checked against separate fallback output.
The pure-PV and DTU-owner classes decompiled without reported errors.

Relevant call chains:

- `com.balcony.host.fragment.MainHomeSystemFragment.r0` selects BMS/PV/DTU-owner/
  WBPV child screens from the station bean's `classify`, `is_creator`, `reflux`
  and `StationDeviceAppendUtil.z(bean)`. The latter checks PV classification
  and nonzero `bt`; this is not an HMS model-name test.
- Its settings-click handler `G` likewise branches on PV classification and
  `bt`; for the PV/`bt==0` branch it opens PV or DTU-owner settings. It does not
  unconditionally open battery settings. Station fields select UI capabilities;
  their presence/absence cannot be invented from an empty live response.
- `MainHomeSystemChildPvV1Fragment.b0` and
  `com.installer.system.ui.MainHomeSystemChildDtuOwnerFragment.h0` send
  `{sid,m:0}` to the returned URI. Their URI lookup uses the existing mobile
  `PVMC_STATION_GET_SD_URI_C` key, as documented previously.
- The PV callback `S` and DTU callback `J` parse connection/power. If power is
  missing and the parsed connection is not 1, they display `--`, rather than
  failing creation of the entire parent screen. The connected/missing-power
  UI branch can display `0 W`; that is not proof of an actual zero measurement
  and must not be copied into HA energy integration.
- `getIntValue("con")` also defaults an absent primitive value; it is not
  evidence that missing `con` means the cloud explicitly reported offline.
- BMS/WBPV callbacks have different flow/delay branches. Their exception paths
  schedule a same-URI request after 5000 ms. No universal nighttime response
  schema or account-wide timing quota follows from these foreground UI paths.

## Consequences for the HA implementation

The current coordinator awaits validated Live data before initial device-tree
and enrichment work. A final `invalid_live_data` exception prevents those later
steps in that update. Its existing `missing_uri` partial-start path separately
validates station access and leaves Live unavailable, so it is already a model
for separating station existence from current measurements.

**#59 candidate:** preserve the known working bounded URI retry first. If the
actual failing response is established as a supported no-measurement/pending
state, validate station access and allow independent metadata/setup with Live
unavailable. Do not call arbitrary malformed replies offline, fabricate zeros,
mark old samples fresh, or suppress auth/access failures. Preserve recovery,
account pacing and resets of energy integration across missing data.
The earlier v0.6.1b5 scheduled-wait regression is documented in
[the live investigation](live-data-investigation.md): simply copying the web
same-URI timer previously degraded the maintainer's working setup.

**#61 candidate:** investigate a separate read-only station-capability assessment
based on fresh manufacturer station metadata, rather than using a successfully
parsed HMS model as the only reason to suppress battery reads. The app provides
a source-backed path to investigate `classify`/`bt`, but we still need to follow
the exact HA-used response mapping, types and valid combinations before coding.
The current Home station-list normalizer keeps only station ID/name, so the
app's capability fields are not yet available from that normalized list.
Missing metadata is unknown, not evidence of no battery. This must not weaken
output/write target selection or turn cached model data into fresh control
authorization. Keeping verified metadata across reloads would likewise need
identity/topology/age safeguards and separate treatment for writes.

Neither finding establishes that #59 and #61 have the same cloud cause.
Required next observations remain the fixed Live type/reason line for #59 and
b4 model-discovery/capability diagnostics at night and after recovery for #61.
No real account or raw private capture is required for this source investigation.

## B5 candidate implementation, 2026-11-18

The Home main-system request chain was followed further: `j0` calls
`PVMC_STATION_SELECT_BY_PAGE_C` with `page/page_size`; callback `V` parses
`com.hoymiles.bean.JgSystemListBean`. `fixSystemData(false)` rearranges device
lists, not `classify` or `bt`; fallback instructions were inspected because
normal JADX output contains a duplicated-local reconstruction issue.
`com.balcony.bean.enums.StationType.PV` resolves explicitly to **1**.

B5 keeps optional normalized `battery_capability=pv_without_battery` only from
Home list rows with explicit JSON integers `classify=1,bt=0`. It never defaults
missing fields to zero, converts bool/string fields, or copies other private
row data into diagnostics. Repeated station identities cannot establish the
capability. A separate valid PV-only topology is also required; controller
information anywhere in the tree vetoes suppression. Fresh evidence is bound
to the station/tree context and discarded after concurrent changes or unload.
The optional list read has a twelve-second budget, reuses partial-start access
validation where possible, and runs at most once per context; no faster or
periodic capability loop is added. Unknown capability keeps the legacy path.

For Live, **both** bounded attempts must contain a successful empty object or
an object with only strict nonnegative signed-long integer `dly` to raise the
new fixed `live_no_measurements` condition. Existing URI recovery runs first;
real telemetry always wins. Other malformed replies, unexpected fields or
request errors do not become an offline/zero sample. The coordinator handles
this missing-measurement condition like its existing independently validated
missing-URI partial startup: unavailable Live, separate device data and normal
one-minute recovery, restoring fast polling on real data. No earlier b5-style
same-URI waiting/deadline replaces the known working retry sequence.

This is not new write authorization. Output selection still requires the
existing HMS model/topology and permission checks; battery mode/SOC writes are
blocked when battery reads are explicitly not applicable. Histories, timestamps
and energy gaps retain their existing missing-data behavior. No optimistic
values or API/device commands were added. Fresh diagnostics expose only fixed
Live/applicability labels and booleans, never raw station metadata.

See [b5 test instructions](release-0.6.2b5.md). The manufacturer-client evidence
justifies a narrow missing-data/capability candidate, not a claim that an empty
object is the exact response seen in #59 or that #61's flags are available.
