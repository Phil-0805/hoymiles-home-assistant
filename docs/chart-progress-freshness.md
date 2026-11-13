# Chart progress and availability — 2026-11-12

Correction prepared for **v0.6.1b11** after v0.6.1b10; see the
[release notes and test instructions](release-0.6.1b11.md). The installed b10
release does not contain this change.

## Reproduced availability regression

The maintainer supplied three consecutive private b10 exports and matching
frontend observations. The relevant allowlisted observations are:

| Export | PV1–3 and inverter details: sample age | Frontend |
| --- | --- | --- |
| First | 491 seconds | Available |
| Second, 150 seconds later | 641 seconds | Unavailable |
| Third, about 151 seconds later | 492 seconds | Available again |

Requests report success, Live stays available and station PV power continues
to update. The last transition advances the chart sample by roughly five
minutes. The 600-second source-age cutoff explains why displayed values expire
between ordinary five-minute chart polls. This does not establish a rate limit
or prove that every missing field has this cause.

PV4 is different: its age increases 791 → 941 → 1092 seconds without a newer
sample. The maintainer explicitly confirms that PV4 is unoccupied. This does
not permit hardcoding port 4 as unused for other installations, converting
missing telemetry to zero, or renewing that old sample on each successful read.
The private exports/screenshots and identities are not copied into the repo.

## Earlier implementation

The maintainer explicitly requested stable **v0.6.0** as the earlier baseline,
not only b8. Its tag resolves locally to
`fdb120f34fc9f5ef8ba1e25321a02ba756d738b7`. Direct AST comparison against b8
confirms identical `ModulePoller.is_fresh`, `detail_is_fresh`, `_async_poll`,
`HoymilesHomeClient.async_module_values`, and the complete module/detail sensor
classes. `MODULE_INTERVAL` is five minutes in both. Thus the PV input read,
last-value decoding, successful-request timestamp and entity availability path
really were the same in 0.6.0 and b8, rather than merely assumed to be similar.

In 0.6.0, PV ports remain usable for ten minutes after a successful chart read;
zero is accepted like any other finite measurement. Temperature/frequency/AC
voltage already expire by the snapshot source time, within ten minutes and the
one-minute future tolerance. B8 adds a micro-chart supplement for missing/stale
HMS detail fields and a more precise aggregate detail status. It does not change
that underlying detail freshness bound. No faster per-input live path or changed
PV polling cadence is established by the historical comparison.

Published b8, commit `077281c297e579b59daf50a23db2014d3b0e4f4b`, also used a
five-minute module interval. It decoded the last finite module value and set
the port's age from the successful request time. B9 switched PV input freshness
to each chart timestamp and thereby introduced the new expiry behaviour.
Inverter detail fields already used source timestamps before b9, so it would
be incorrect to attribute every temperature-age problem to a new b9 check.

Reverting to request-time freshness unconditionally would make identical old
zero values fresh indefinitely. The correction instead keeps the original
source time and a separate, field-specific progress clock.

## Local policy

- Source time remains the aligned point time in the requested station-local day.
  It is never replaced with HTTP receipt time or another field's label.
- Progress time changes only for a newer accepted source timestamp, or for a
  changed finite value within the same accepted time bucket. A genuinely new
  timestamp counts even when its value remains zero.
- Re-reading an identical `(timestamp, value)` pair, missing/nonfinite data,
  earlier replacements, future/DST-invalid samples, failed requests and exporting
  diagnostics never renew progress. Each metric retains its own clock.
- A sample is usable while source age is **less than 20 minutes** and progress
  age is **less than 10 minutes**, retaining the existing one-minute allowance
  for clock lead. The source cap prevents ancient buckets from staying usable
  through changing revisions. Ten minutes without progress expires a frozen
  series even if requests keep succeeding. Stopped readers remain unavailable.
- These are explicit conservative client policies, **not** manufacturer-defined
  quotas or a guarantee of physical real-time measurement. They accommodate the
  observed roughly eight-minute chart lag and intervening five-minute poll.
  Other chart delivery delays may still require assessment.
- Module batch values and their source/progress clocks are published together,
  including partial success on timeout. A concurrent Live tick cannot attach a
  replacement batch's new metadata to the previous published values.
- Diagnostics retain the real source `age_seconds` and additionally expose
  bounded `progress_age_seconds` and both policy bounds. The aggregate
  `details_status` is evaluated against current field usability, so it no longer
  remains `readable` after all its fields expire between polls.

The five-minute cadence, account start spacing/concurrency, server pauses,
settings requests, Live transport and energy calculations are unchanged. There
is no additional timer, write, account request, endpoint or automatic retry.
No unused-port inference or new standalone last-temperature entity is added.

## Android source comparison

Rechecked statically on 2026-11-12 against the pinned Home APK
`com.hm.balcony` **V2.14.0**, version code **2026110903**. It comes from the
third-party mirror documented in [the original investigation](live-data-investigation.md#current-manufacturer-comparison);
publisher signature authenticity has not independently been established.
Nothing was installed or executed.

- `MicroCloudDetailActivity.C0` requests `MI_POWER`, voltage/frequency and
  `MI_TEMPERATURE` through `HttpHelper.p`; `D0` requests `MODULE_V`, `MODULE_I`
  and `MODULE_POWER` through `HttpHelper.q`. The former uses integer micro IDs;
  the latter sends `{id, port}` entries. Existing Home chart routes/float32
  parsing remain the relevant protocol, not the web/Installer float64 format.
- Callbacks `a0/q0` align values with the ChartPB axis and populate chart entries.
  `H0` draws those arrays. This inspected chart path does not implement HA's
  ten-minute entity-expiry check. It is entered on opening, selection/date
  changes and manual refresh; no periodic background chart-poll quota is
  established by that activity. Zero-padding in a chart is not proof of a
  measured missing input value and is not copied into HA.
- `CommonMicroCloudHomePageActivity.G1/J1` is a **different live display path**:
  it sends `{sid, m:3}` to the obtained live URI, parses `mis`, and schedules the
  next request using returned `dly` (5000 ms recovery on its error paths).
  `F2` matches a device serial before drawing `p1..p4`; the bean defines these
  fields as nullable per-input powers. This is not voltage/current/temperature.
- The same activity's `x1/A1` uses the separately resolved
  `/pvmc/api/0/micro_data/real_c`, body `{sid, mid}`, on the Wi-Fi-integrated
  device branch after its connection check. Its response bean has `gp`,
  `pv_1..pv_4` and `last_data_time`. That branch does not establish support for
  every account/model or permission to use its route on arbitrary profiles.
- HA currently sends `m:0` for station Live. Replacing that request with `m:3`
  would change its payload contract and is not a safe polling-interval edit.
  Neither new live route is enabled by this availability correction. A genuine
  faster per-input live feature requires separate guarded implementation and
  account/device verification. No endpoint was probed.

Thus the APK distinguishes historical charts from live per-input powers.
Its foreground `dly` loop does **not** establish an account-wide request quota
or a valid fixed interval for all historical chart reads.

## Current public web client

Fetched the actual [website entry](https://global.hoymiles.com/website/) on
2026-11-12 and followed its referenced scripts, not guessed filenames:

1. [Main bundle](https://static.hoymiles.com/cdncache/website/js/index-BTRAEMTt.js)
   references the device-detail route's `index-BchebEBX.js` module and defines
   the chart request wrappers.
2. [Device-detail view](https://static.hoymiles.com/cdncache/website/js/index-BchebEBX.js)
   calls `getMicroGenPowerStats` or `getComponentGenPowerStats` for selected
   devices/ports and indicators. It retains the returned chart in its local
   `qe` handler, builds data arrays from the supplied `xAxis`/series, and
   reloads on date/type/device selection or refresh. No corresponding
   ten-minute removal of individual measurement entities is present in this
   inspected chart path. This is not a claim about every web screen/cache.
3. The wrappers use the **separate web** `/pvm-data/api/0/micro/data/count_by_day`
   and `/pvm-data/api/0/module/data/count_by_day` routes with `pb_ver:1`.
   They are not substituted for the Home `/pvmc/...` endpoints. There is no
   supported fixed account-wide quota in these inspected methods.

All downloads were public static files; no login/account/device request was
made. This establishes client code paths, not measured backend refresh latency
or an official API allowance.

## Source hashes

Only summaries and synthetic tests are tracked; downloaded/decompiled sources
remain outside the repository.

| Source | SHA-256 |
| --- | --- |
| Base APK | `d3f39915b8164045ae4a7107aed3232f6fe8fe201c9f1d7543e5919b26127650` |
| MicroCloudDetailActivity.java | `9480d1b94cf939d996fc46fb94cc6be6abf499a83a11c19512111f11708ab191` |
| CommonMicroCloudHomePageActivity.java | `1bfc2d213a21c132f32ddd2c557f1dab20450a090339de885b17738c5795b570` |
| StationSecondFlowBean.java | `ec18698108f5c112b6eca8beb83c0f8da08020c553018c7fb8a5a1f1fb8c7fa5` |
| MicroRealData.java | `a5a1799c5bcb0139f3d8b74027a92bfe5e81dcab389476edb7b9d2eeef89da75` |
| HttpHelper.java | `320a355801ae716c42cdd5f97ddb00ab27e47339f2517d294a4fceb5e7f2e921` |
| online_domain.json | `8f876438eeaffd6264816b98fc8f62fdcb57cedecdfcea775ab48cc763677f3b` |
| Current web entry | `76328c3b1e03e0a86e30d08fc91b5691262ac17812f275d9a1184ce50a9786eb` |
| index-BTRAEMTt.js | `093c693196cf7966d1565ee7cca170d65f7de28ba5d9078f911ec9e164b64164` |
| index-BchebEBX.js | `ed7407cf401050bb6e475c27f22e64c73fc02015f1936e5297fffae72e4bee6d` |

The relevant methods are readable JADX reconstructions; reconstruction errors
elsewhere are not treated as evidence. Static UI behaviour and automated tests
still need a comparison with the maintainer's actual installation.


## Verification

The final local code passed **1213 HA tests plus 134 subtests on each of
HA 2026.10.4 and 2026.11.0**, and **56 unit tests**. The known anyio
assertion-rewrite warning appeared under 2026.11.0. Syntax, translation key
parity, document links, whitespace and a 38-file development ZIP passed.
Tests include the actual reported 491/641/492-second cycle through real HA
state publication; ordinary five-minute requests; advanced/changed versus
identical zero/nonzero samples; independent metric clocks; old/future/older
replacements; failed reads; aggregate-status expiry; concurrent batch publication;
target pruning and shutdown. The original sample times remain intact.

The runtime investigation used no actual account/device requests. Publication
follows the existing gated beta workflow; no issue comment is part of the
investigation. The test environment is on HA 2026.11.0. Hardware confirmation
of the policy change is still pending.
