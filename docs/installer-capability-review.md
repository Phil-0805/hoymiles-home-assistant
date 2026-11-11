# Installer capabilities and possible b4 scope — 2026-11-11

## Outcome

Installer is a separate client/device family, not a Home token with every Home
endpoint unlocked. The inspected manufacturer clients establish useful next
steps for monitoring and a separate storage-settings protocol. They do not
establish feature parity with the Home profile for any particular installation.

This is a research result, not an implementation or release approval for extra
Installer features. It was completed against **0.6.1b3**. The subsequent b4
release preparation retains its existing Installer restrictions.
No authenticated account request, device command, app installation or app
execution was performed. Only public website assets and the APK were downloaded.

Current feedback in [issue #16](https://github.com/Phil-0805/hoymiles-home-assistant/issues/16)
confirms that rupacheco successfully used b3 after selecting Installer. The
requested comparison of measurements and energy totals is still outstanding.
This confirms access on that account, not every supported data field or control.
Separately, the maintainer reports the Home TOU fix working in their own test;
that does not validate Installer storage settings.

## Sources and reproducibility

The documented APKPure XAPK URL was downloaded again on 2026-11-11. The XAPK
manifest and base-APK `com.hoymiles.BuildConfig` independently report package
`com.hm.hemaiInstall1`, version **V3.14.0**, version code **2026102718**.
XAPK and base-APK SHA-256 match the previous inspection exactly:

| Artifact | SHA-256 |
| --- | --- |
| XAPK | `16633c1aa3a5f3d202c794b0126684acc80d0320d66e8ab3d9e9dd3ac73b0199` |
| Base APK | `1b4b324d3638c6bbf4a5eff29c20bc0f0f9be7766ff9da383cb62f30bc56df9e` |
| Bundled domain table | `839c773cb08a6e92b0bade03e8fce5f387cea96da9eda96f9830fd33fbcbcc46` |

This remains a third-party mirror; publisher-signature authenticity has not
been independently established. See [the original provenance](installer-app-protocol.md).
JADX 1.5.6 again reports 309 errors overall. The request-building and generated
protobuf methods used below are readable; errors elsewhere are not treated as
evidence. No complete manufacturer sources or binaries are copied into the repo.
Research files reside outside it under `/private/tmp/hoymiles-installer-research-20261111`.

The public [website entry](https://global.hoymiles.com/website/) currently names
`index-BTRAEMTt.js`. Its dependency map and plant-settings/device routes reference
the modules below. This follows the current entry, rather than assuming that
an older settings-bundle filename is still loaded.

All JS URLs below are relative to
`https://static.hoymiles.com/cdncache/website/js/`, fetched 2026-11-11:

| File | SHA-256 |
| --- | --- |
| `index-BTRAEMTt.js` | `093c693196cf7966d1565ee7cca170d65f7de28ba5d9078f911ec9e164b64164` |
| `device-DU7qlH58.js` | `353fddcd380825c43c0e1ab98d843f9042cf3270d1ecb3910e13053b2681b479` |
| `CommandState-DhO5z2hn.js` | `68a24af73c2ac5b73cdac3be06e5736d4e8e3070a4f68cd3732b54efa9e9fe51` |
| `index-BTtyDjvp.js` | `0dbee0b0276b1447bae2137a82d31843c1691cb0cfb49bbe00139289874e93d9` |
| `index-DiWwxkFC.js` | `bdb5aa290264f4dc5bb386bdcb9d9b1f67393b2edb7a3f3cb8b1e97085bf28df` |

Public client code demonstrates protocol and UI behavior, not the permissions
or supported hardware of a specific account. No endpoint or action was probed.

## Capability assessment

| Capability | Evidence | Implication for our integration |
| --- | --- | --- |
| Login, plant access, live power, energy totals | Existing b3 implementation and earlier call-chain inspection; successful b3 access reported | Keep working b3 behavior; obtain a same-time app comparison before declaring all readings verified |
| Module power, voltage, current | `MicroDetailActivity.x0` → `HttpHelper.s1` → module day-chart route → `ChartPB.LineChart` | Concrete implementation candidate, with a separate Installer binary decoder |
| Microinverter power, grid voltage/frequency, temperature | `MicroDetailActivity.w0` → `HttpHelper.q1` → micro day-chart route → `ChartPB.LineChart` | Concrete implementation candidate; chart samples need timestamps/freshness, not a live-data label |
| Storage mode and reserve SOC | `PowerTab4FragmentrEs.M0` → `EsBmsSmartControlRealActivity` → action 1013 device-settings read/write/status; current web battery settings also use 1013 | Separate model/capability work; do not enable Home action 83 or reuse its mode numbering |
| Battery-pack detail measurements | `BMSPacketRealDataListActivity.b0` → typed indicators request → `EsRealdataListBean.list` | Read path exists, but exact stable temperature keys, units and device association still need resolution |
| Home cutoffs 1537, running output 84/1532, heating 1518, light/display 1529 | No equivalent complete Installer UI → request → addressing → parser chain established in this review | Remain blocked; similar names or a shared settings wrapper are insufficient |
| Other device operations | Current web device view checks operation permissions and requests device functions | A device-specific function list is not permission to expose arbitrary commands in HA |

### Module and microinverter charts

`MicroDetailActivity` receives the station ID, selected microinverter ID and
module port; `MicroDetailBean.layout_list` supplies actual module ports. Never
invent a device or port when this information is missing.

`x0(date)` requests `MODULE_V`, `MODULE_I`, `MODULE_POWER` through
`HttpHelper.s1(sid, date, microIds, quotas, port)`. The helper constructs:

```json
{
  "pb_ver": 1,
  "sid": 123,
  "date": "2026-11-11",
  "mi_list": [{"id": 7, "port": 1}],
  "quota": ["MODULE_V", "MODULE_I", "MODULE_POWER"]
}
```

All IDs/dates here are synthetic examples. `LdAutoCardSettingEsActivity.k1`
resolves to literal `id`. The bundled route key
`PVM_DATA_API_0_MODULE_DATA_COUNT_BY_DAY` resolves to
`/pvm-data/api/0/module/data/count_by_day`, domain ID 0/neapi in that table.

`w0(date)` requests `MI_POWER`, `MI_NET_V`, `MI_NET_RATE`, `MI_TEMPERATURE`;
for explicitly three-phase devices it substitutes `MI_NET_V_A/B/C` for the
single voltage. The helper `q1` constructs the same envelope with an integer
`mi_list` such as `[7]`, rather than module `{id,port}` objects. The route key
`PVM-DATA_DATA_COUNT_BY_DAY` resolves to
`/pvm-data/api/0/micro/data/count_by_day`, also bundled domain ID 0.
The activity labels these values W, V, Hz and degrees Celsius; module labels
are V, A and W. These charts must not replace station live power.

Both callbacks parse `com.hoymiles.proto.bean.net.ChartPB.LineChart`, with
axis labels and typed series. Generated `LineSeries` fields are:

- 1: string `type`;
- 2: repeated **double** `data` (packed and unpacked fixed64 are supported);
- 3: integer `did`;
- 4: integer `port`.

`LineSeries.writeTo` explicitly calls `writeDoubleNoTag`; its parser calls
`readDouble`. The existing Home `protobuf.py` decoder instead decodes packed
field 2 as **float32** and unpacked values as fixed32. Therefore changing only
the route would corrupt Installer charts. A synthetic packed-double series
with `MODULE_POWER=123.5`, device 7, port 1 currently produces **3.482** through
the Home `latest_values` decoder. This was reproduced locally without network
or account data. It is a compatibility blocker for a future feature, not a
claim that b3's existing live/energy readings are wrong: b3 blocks these charts.

A future implementation must explicitly select the evidenced schema/version;
payload length alone cannot distinguish packed float32 from float64. Keep
finite-number, identity, size, date and sample-age checks. Do not copy the app's
missing-sample-to-zero display behavior into HA measurements. Do not enable the
Home `dmdd_c` snapshot route as an Installer fallback.

### Storage mode and reserve SOC

The ES settings fragment opens `EsBmsSmartControlRealActivity` for storage
plants. `x1()` submits an action-**1013** read with `data.sid`; `W1(job, true)`
polls `PVM-CTL_SETTING_STATUS` using `HttpHelper.J2(job)` and parses successful
`CmdStatusBean.data` into `EsBmsAndRelayBean`. That read model has `bms_mode`
and `bms_data.k1...`, not the Home action-83 `mode/k_3` model.

The app's write path uses `HttpHelper.Z2(sid, mode, value, otherValue)` wrapped
by `v2(1013, data)`. `Z2` builds station data with `sid`, `type:1` and nested
`data:{mode,data:...}`. Some branches use a reserve-SOC block, others serialize
whole economic/TOU settings from cached structures. The settings action is not
the similarly named `ECommandAction.ES_USER_SETTING` command-put operation.
`LdAutoCardSettingEsActivity.r1` resolves to literal `data`.

Bundled route resolution and current web confirmation:

- `PVM-CTL_SETTING_READ` → `/pvm-ctl/api/0/dev/setting/read`;
- `PVM-CTL_SETTING_WRITE` → `/pvm-ctl/api/0/dev/setting/write`;
- `PVM-CTL_SETTING_STATUS` → `/pvm-ctl/api/0/dev/setting/status`.

The current web battery module sets action 1013, reads `data:{sid}`, and writes
`data:{sid,data:{mode,data:settings}}` through the device-settings wrapper.
Its mode numbers and branches differ from Home action 83. Web and Android
serialization also differ (for example Android's `type:1` and string SOC
values), so a chosen implementation must trace and test one coherent path.
The command-status store polls the returned job identifier; a submitted write
is not itself a successful readback.

This establishes a real storage-control path, but not safe automatic parity.
Before enabling it: resolve the station/device capability checks and per-mode
ranges, read the entire current settings, preserve returned counterparts and
plans under a lock, and require complete readback after one write. Missing
settings/unknown modes must stop the operation. Do not send different action
IDs as fallbacks. Existing Home legacy-1013 code alone is not validation for
Installer devices, and Home action-83 TOU success does not validate this model.

### Battery detail measurements

`BMSPacketRealDataListActivity.b0` normally uses `HttpHelper.Z0` to build
`{sid,type,dev_sn}` and calls `PVM-DATA_DATA_SELECT_REAL_INDICATORS_DATA`, mapped
to `/pvm-data/api/0/indicators/data/select_real_indicators_data`. Battery-pack
type 22 has a separate addressed branch using `HttpHelper.L`, inverter
identity and its parent/tree extension; it must not be collapsed into the
normal branch. The success parser returns `last_data_time`, `invalid` and
rows with `key`, `val`, `fmt_val`, `unit`, `name`.

This is evidence for detail measurements, not yet an allowlist of temperature
keys or their scale. Display names and formatted values must not be used as
stable API keys. Further mapping is needed before enabling automatic battery
temperatures through this route. The Home `au_s_c` temperature reader is not
thereby confirmed for Installer.

## Recommended next implementation step

For a useful b4, prioritize Installer module charts and optional microinverter
details with the explicit float64 schema, actual device/port discovery and
existing slow polling/account budgets. Preserve Home decoding and behavior.
Cover exact requests, malformed/finite values, identities, packed/unpacked
doubles, stale/future timestamps, profile changes and unload with synthetic
tests. Compare resulting values against the official app on a real Installer
installation before removing the experimental designation for that scope.

Storage controls should be a separately validated capability, after their
mode/range/permission mapping is complete and a storage-equipped Installer
tester is available. Do not unlock every Home reader/writer by changing the
global `supports_home_features` flag. Keep unsupported operations denied at
the API boundary, even if old options contain control permissions.

No version bump, release, commit, push or runtime change is part of this review.
