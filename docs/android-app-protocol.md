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
