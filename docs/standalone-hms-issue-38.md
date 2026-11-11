# Standalone HMS review against v0.6.1b6 — 2026-11-11

The report and follow-up in [issue #38](https://github.com/Phil-0805/hoymiles-home-assistant/issues/38)
describe Home profile v0.6.0 on an HMS-2000-4WB without a battery. The relevant
paths were compared with published **v0.6.1b6**, commit
`2edad0511c943e599bb958ce5007d22516df7c45`.

| Reported statement | Finding in b6 / evidence | b7 treatment |
| --- | --- | --- |
| Four PV inputs work | Existing per-port module charts and explicit HMS model input counts are present; the user's device observation is not an independent agent measurement | Preserve these charts and identities |
| Temperature, AC voltage and frequency stay unavailable | B6 requests `module_data/dmdd_c`; field availability uses per-metric timestamps. A successful response with an inverter record but no usable fields can still say `details_status=readable` | Only say readable when a fresh metric exists; supplement missing/stale HMS metrics from the Home chart |
| `micro_data/count_by_day_c` can supply these metrics | Home APK V2.14.0 directly implements this route, integer `mi_list`, and the named quotas with float32 ChartPB. The reporter's successful hardware use is their observation | Add this read-only path behind the existing extra-telemetry option, once per existing five-minute poll when needed |
| Output control fails with `no_unique_target` without an AC battery | Confirmed: OutputPowerSettings inherits DeviceSettings' type-12 controller selector before its station-level read | Allow an explicitly recognized single-HMS/optional-DTU topology; retain controller selection for other trees |
| Station action 84 uses `sid`, `power`, returned `max_power` and status polling | This transport already exists in b6. The Home APK and earlier manufacturer web investigation establish station addressing. Actual phase selection and limits still need fresh responses | Reuse the existing phase lookup, 84/1532 selection, bounds, lock, one write and full readback; never force 84 after an invalid phase response |
| Battery readers run without battery hardware | Confirmed for the mode/SOC reader: b6 checks Home profile, not device topology. Battery-temperature polling is also independent of topology | Skip these readers for the same narrow recognized topology, including manual mode/SOC refresh. Other trees retain existing behavior |
| `cloud_status=1` proves the hardware cannot support a request | Not established: the rejection is generic and contains no specific cause | Do not label a proven API restriction, authentication failure or rate limit |
| Live invalid/recovered pairs mean a complete outage | Not established; reporter says PV remains available. B6 already makes a successful reduced `dly` response/retry an INFO event | No further live behavior change in b7; real failures still warn |

## Recognition and controls

The standalone path requires a nonempty list tree, exactly one explicit HMS
model on a type-3 device with a positive integer ID, and only optional type-2
DTU nodes with positive integer IDs. Duplicate identities, additional inverter
devices, unknown types/models, malformed child lists and any type-12 controller
block this recognition. Metadata outside `children` never supplies an inverter.
The tree must actually contain this evidence; an enriched display name alone
does not prove the topology. A future diagnostic export may reveal a different
valid layout needing separate support. No serial-prefix/model guessing is added.

Output remains opt-in under the existing control permission explicitly naming
output power. Its target binds the station, inverter ID/model and recognized
device identities, which are rechecked after the fresh settings read. No new
command, retry write, default 2000 W maximum or configuration-515 change exists.
The original battery-controller path remains available and ambiguous controllers
remain blocked. This does not equate a battery's output setting with an inverter
setting on every hardware family.

## Telemetry and freshness

Keep `dmdd_c` first. Only a successful decoded response leaving missing or stale
metrics on explicitly identified HMS devices enables one batched micro-chart
read. Auth, rate, transport, rejected redirects and failed snapshot responses
do not trigger another endpoint. Requests retain account pacing, response-byte
bounds, HTTPS/redirect restrictions and the five-minute poll schedule. Installer
is unchanged: its separate float64 charts are not decoded as Home float32.

Only the requested positive device IDs, port zero, known metric types and finite
values are accepted. Duplicate metric/device series and malformed/nonascending
HH:MM axes are rejected. Each value keeps its aligned label from the requested
local station day; a shorter series never acquires the last axis label. Missing
or nonfinite values are not replaced with zero. Future samples are rejected and
older samples cannot replace newer ones. Request time does not refresh sample
age. Existing ten-minute freshness and entity IDs are retained. No chart data
replaces live PV or energy totals.

## Manufacturer source verification

The current public [website entry](https://global.hoymiles.com/website/) was read
on 2026-11-11 and still references `index-BTRAEMTt.js`. Its settings route loads
`index-CYgZbGAt.js`, fetched SHA-256
`b76b5eabb79fcea196d1c4bd0e3c2e955ccac89330f9db8d00fc36e916dcc18f`.
That general settings page does not itself establish standalone action-84
eligibility. The previously inspected output drawers are documented in
[output power evidence](output-power-settings.md); no new endpoint was guessed.

The actual Home APK archive is **com.hm.balcony V2.14.0**, version code
**2026110903**, from the third-party mirror documented in
[the live investigation](live-data-investigation.md#current-manufacturer-comparison).
Publisher-signature authenticity has not independently been established.
Rechecked base-APK SHA-256:
`d3f39915b8164045ae4a7107aed3232f6fe8fe201c9f1d7543e5919b26127650`;
bundled domain-table SHA-256:
`8f876438eeaffd6264816b98fc8f62fdcb57cedecdfcea775ab48cc763677f3b`.

Readable static call chain:

- `MicroCloudDetailActivity.C0(date)` → `HttpHelper.p(sid,date,ids,quotas)` →
  `PVMC_MICRO_DATA_COUNT_BY_DAY_C` → bundled
  `/pvmc/api/0/micro_data/count_by_day_c`, domain 0/neapi.
- The activity requests `MI_POWER`, `MI_NET_V` (or separate three-phase voltage
  quotas), `MI_NET_RATE`, `MI_TEMPERATURE`. B7 uses only the three known metrics
  for existing sensor meanings, without combining phase voltages.
- Callback `a0` parses `com.hoymiles.proto.bean.net.ChartPB.LineChart`, associates
  values with the X axis, and uses `List<Float>`. Generated LineSeries methods
  explicitly read/write float32, including packed values. The Celsius value is
  used directly; the activity's local unit conversion is display formatting.
- `StationSystemBmsBleSettingOutputPowerActivity` invokes action 84 and uses
  `HttpHelper.y(StationDeviceInfoUtil.m(), action, data)` for station addressing.
  This confirms the already implemented transport, not universal device eligibility.

JADX has unrelated reconstruction errors as documented in the earlier review;
the methods used here are readable. No app was installed/run, and no real
account or device was contacted. Full manufacturer sources/APKs stay outside
the repository. Hardware/app comparison by the reporter remains required.
