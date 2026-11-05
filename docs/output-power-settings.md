# Output power commands: manufacturer evidence

The public manufacturer web client was inspected on 2026-11-05. It exposes two
different operations. The screenshot's output-power **upper limit** must not be
silently substituted with the running output-power setting or grid-export limit.

## Configured output upper limit: configuration 515

`OutPowerLimitConfigDrawer` reads and writes station configuration type **515**:

- Read: `POST /pvm/api/0/station/setting/cfg_g_m`, body `{sid, type: 515}`.
- The returned data contains a `515` block with `max_power` and, where supplied,
  `power_a`, `power_b`, `power_c`.
- Write: `POST /pvm/api/0/station/setting/config`, body
  `{sid, type: 515, data: {max_power, power_a, power_b, power_c}}`.
  JavaScript omits undefined phase values when serializing the request.
- Values are watts; the drawer validates whole values starting at 100 W.
- Phase information is read from `POST /pvm/api/0/station/phase/type_s_c` with
  `{sid}`. The drawer also reads the station's inverter list.

The UI derives an upper range of 2000 W per phase, or 2500 W for series 2805/2806,
then multiplies by its phase count. These UI bounds and defaults are not evidence
of the permissions or hardware limits of any particular account. Do not infer
an allowed increase from a displayed device series or a default value.

## Running output setting: action 84 / 1532

`OutPowerConfigDrawer` uses device-settings **action 84** with `data.sid` and
`data.power` for a single-phase station. Its readback contains the current
`power` and an upper `max_power`. It defaults a missing upper bound to 2000 W;
that default is not a verified capability and must not become a HA control range.

If the phase endpoint returns phase entries, the drawer switches to **1532**.
Writes use `{type: 0, power_total, power_a, power_b, power_c, sid}` in `data`;
readback uses `out_power_total`, `out_power_a`, `out_power_b`, `out_power_c`.
Do not mix these read and write field names or select action 84 without checking
the station layout.

## Implementation status

The commands above are identified in manufacturer source, but are not new HA
entities yet. Station-specific readback, phase layout, permissions, limits and
app comparison remain unverified. This avoids repeating the b2 SOC mapping
mistake. No live account reads or output-limit writes were used in this research.
Grid-export power is a separate setting and remains outside these operations.

## Sources

- [Manufacturer settings drawers](https://static.hoymiles.com/cdncache/website/js/index-COaHho1l.js),
  SHA-256 `d932523a3183d7d24ad0ea26ae544eeaf63075b50189f3b5368974a9d0efd8f4`.
- [Manufacturer station transport](https://static.hoymiles.com/cdncache/website/js/index-CTUY73vV.js),
  fetched on 2026-11-05, SHA-256
  `a2790e4875668e9de1f8a3aacb0164bffbfe8cfb6ca4180e042330aac3240c98`.

These are public client implementation details, not a published API guarantee
or an authenticated device command capture.

## Android cross-check

Android V2.13.0 independently uses action 84 for the legacy output-power page
and 1532 for phase controls, through station_ctl routes. This confirms the
commands in that app implementation, not the settings of a live device. See
[APK provenance and method chain](android-app-protocol.md).
