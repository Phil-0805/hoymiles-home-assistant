# B9 daylight follow-up — 2026-11-12

Follow-up prepared for **v0.6.1b10** on top of published v0.6.1b9; see the
[release notes and test instructions](release-0.6.1b10.md). The private attachments
are not copied into the repository.

## What the two exports establish

Both supplied files declare 0.6.1b9 internally. At night, Live is unavailable and
PV power is absent. The active export has Live available and station PV power
7.4 W. Both report `details_status=no_data`, `standalone_hms_recognized=false`,
zero decoded battery devices and output `no_unique_target`. The reporter also
reports automatic daylight recovery and a successful b8 daylight rollback.

The maintainer's separate battery-equipped installation has readable output
settings and `details_status=readable`, despite unavailable input/temperature
entities. The summary only requires one fresh detail field; it does not promise
that temperature or any individual PV input is fresh. These are different
installations and their exports must not be treated as a same-device A/B test.

Neither export includes the original device tree, chart axes or field ages.
They establish symptoms but cannot identify the exact rejected topology or
sample on either installation. No rate restriction is established.

## Corrections implemented locally

### Home topology

The existing selector accepted type 2/3 nodes and traversed only `children`.
The inspected Home APK explicitly defines DTU=1, repeater=2, microinverter=3;
`JgSystemListPageBean.DevicesDTO` nests physical devices in `devices`.
`JgMicroinverterNetStatusActivity.f0/V` requests `select_device_c` with `sid`
and parses a list of that class. Its `Z` method reads nested `devices` for
integrated units. Thus the former description of type 2 as the DTU code was
incorrect for this Home protocol, and the selector omitted a documented tree
representation that general inverter discovery already traversed.

The selector now accepts type 1 alongside the existing types and follows both
`devices` and `children`. It still requires a single explicitly identified HMS,
positive integer identities, verified matching model enrichment where needed,
no duplicates, no storage and no unknown device types. Conflicting representations
are rejected rather than collapsed. Metadata is not promoted to topology.
No IDs, serials or raw trees are changed. The same recognition controls battery
reader applicability and selection of the existing station-output path.

This reproduces and repairs a concrete mismatch against the manufacturer's
representation. It is not proof that the reporter's unexported tree has exactly
that representation or that their station accepts action 84/1532.

### Chart acceptance and cutoff

B9 made module charts depend on an aligned sample time rather than request time.
The shared validator required zero-padded HH:MM on every axis label. It rejected
an entire otherwise usable daily chart containing H:MM or an ending `24:00`.
The inspected app does not impose that regex on ChartPB labels. Its numeric
minute conversion `DateUtil.b0` parses hour/minute components and explicitly
uses `24:00` as a day-end representation. The local parser now normalizes H:MM
to HH:MM and accepts `24:00` as an axis boundary. That boundary is never selected
as midnight or as a current measurement. Earlier correctly aligned finite
samples retain their own times; no value receives request time.

A separate reproduced edge regression affected both module and micro charts:
the existing stamp/freshness checks accept up to one minute of clock lead, but
the new b9 chart cutoff stopped at the current minute. For example, at 10:04:30
a sample labelled 10:05 was formerly acceptable, but b9 could discard it and
select a stale 09:50 value instead. The runtime cutoff now uses the same existing
one-minute tolerance, clamped to 23:59 at the requested day's end. It does not
increase the freshness lifetime or allow later future points.

These are tested parser/selection defects. H:MM/24:00 and the edge timing have
not been observed in the private reporter exports, which do not contain axes.
They must not be presented as a proven complete explanation of that hardware's
persistent unavailability. In particular, temperature already had per-field
ten-minute expiry in b8; its absence cannot be explained merely by saying that
all freshness checking was introduced in b9. B8 module availability, conversely,
renewed at request time and did not itself establish sample freshness.

## Entity behaviour and scope

- Genuine finite zero values remain valid, including all twelve PV input
  measurements and 0 degrees Celsius. HA state publication is tested, including
  subsequent expiry. Explicit station PV zero from a valid Live sample remains
  available even with `con=0`; a fresh explicit chart power zero is likewise
  visible for each PV input. Missing Live data still disables the station Live
  sensor; absent/nonfinite/stale chart samples do not become fabricated zeros.
  Connectivity loss alone supplies no substitute measurement.
- Output settings remain independent of current PV production. Recognition lets
  the existing read run; it does not manufacture an allowed 2000 W setting from
  an HMS model number. A previously read snapshot now remains displayable beyond
  the normal read freshness window or after a failed read, while its original
  target and permissions remain valid. The number exposes `value_status` and
  `last_confirmed_at`; diagnostics expose `value_status` and a bounded numeric
  age separately from the latest read status/error. Retention does not renew the
  confirmation time or make the old range authoritative for a new write. Every
  change still needs a successful locked fresh read, limits, one write and full
  confirmation. A failed fresh read sends no write. The snapshot is explicitly
  bound to the target of the last successful read, so a failed attempt on a new
  target cannot inherit another device's values. Values are retained only in
  RAM, not restored across reload/restart. A new coordinator needs its own read.
- The normal temperature sensor still expires. The maintainer subsequently
  requested removal of the separate last-known entity. It is no longer created;
  registry cleanup removes only owned sensor entries on this integration with
  the exact canonical `<entry>_<positive inverter ID>_inverter_last_temperature`
  identity. Renamed/disabled copies are included; other domains, integrations,
  owners, IDs, current/battery sensors and devices are preserved. No stale
  temperature is promoted to current.
- Existing phase lookup, explicit reported maxima, permissions, fresh reads,
  target rechecks, one write and full confirmation remain. No route, command,
  retry write, faster polling or additional runtime request is introduced.
- The APK also has a distinct microinverter power-regulation UI using `power_limit`
  with a 2..100 input range and different command dispatch. That is not evidence
  that a model-rated 2000 W is an action-84 limit. No automatic command fallback
  or conversion between these settings has been added.

## Narrow diagnostics for unresolved hardware differences

`polling.standalone_hms_reason` comes from the same assessment that selects the
target. It distinguishes unsupported tree shape/types, invalid IDs/children,
duplicates, storage, missing/unverified metadata and multiple inverters without
exporting identities or the original tree.

Each inverter's `telemetry` contains fixed read outcomes for its known PV ports,
snapshot/micro-chart reads, and fresh/stale/missing field states with bounded
numeric ages. A successful request can therefore be distinguished from an
unsupported axis, malformed protobuf, misaligned series or old samples.
Decoder exceptions cross the API boundary as fixed reasons without source text
or chained raw decoding exceptions. Exporting diagnostics makes no HTTP request
and does not refresh sample age. No raw chart, label, URL, account field, device
ID, serial or exception text is added to the diagnostic fields.

## Static source provenance

Rechecked 2026-11-12 against the same Home APK documented in
[the original investigation](live-data-investigation.md#current-manufacturer-comparison):
`com.hm.balcony`, V2.14.0, version code 2026110903, from a third-party mirror.
Publisher signature authenticity has not independently been established.
APK SHA-256:
`d3f39915b8164045ae4a7107aed3232f6fe8fe201c9f1d7543e5919b26127650`.
No APK was installed/executed and no actual account/device was queried.

SHA-256 of the locally inspected JADX source files, kept outside the repository:

| File | SHA-256 |
| --- | --- |
| DeviceType.java | `08fd853665f00d91473d4adb08f9c116e1619b303abbd83473c4940e8d01f419` |
| JgSystemListPageBean.java | `3e3a6f1e398fa7173fd5b5e22fd4bdf530737c14dec003dbd7641c54872e1116` |
| JgMicroinverterNetStatusActivity.java | `b83da0660b29b62b040a70e38f93dbad169b99ac11f7a6d81cd0a1ce748fc04e` |
| MicroCloudDetailActivity.java | `9480d1b94cf939d996fc46fb94cc6be6abf499a83a11c19512111f11708ab191` |
| DateUtil.java | `db1560e6d3ae863e049d8b152c47f6bf21d5db48a50ff2b1bdc545355102a290` |
| MicroCloudPowerRegulationActivity.java | `8c7ad4ee439b4a9aa6dade9a5a815e33cca5ea12ac9c8a7fd6868cb69f8e5492` |

The listed methods are readable static reconstructions; unrelated JADX errors
are not treated as evidence. Only these protocol summaries and synthetic tests
are included here. The real chart format, output-read support and settings
confirmation at the reporter's station remain hardware validation tasks.


## Final local verification

The final code passed 1203 HA tests plus 134 subtests on **each** of
2026.10.4 and 2026.11.0, plus 56 dependency-free unit tests. The known
already-imported-anyio assertion-rewrite warning appeared on 2026.11.0.
Python syntax, translation key parity, review-document links, whitespace and
all 38 files of a development packaging smoke test passed. The development ZIP
keeps the b9 manifest and is not a new release/install recommendation.
The local test environment was left on 2026.10.4.

Tests exercise real API-to-poller decoding, Home enrichment/coordinator target
selection, strict invalid/mixed/duplicate trees, original data preservation,
normalization/axis boundaries/future tails, independent sample ages, HA numeric
state publication for all four ports, explicit offline zeros versus missing
Live data, old-temperature expiry, overnight output display with unchanged
confirmation age, failed/successful fresh-write preflight, changed target and
permission/unload guards, and exact owned registry removal including disabled
and renamed entities. Existing command transport/readback tests still pass.

The runtime review and tests used no real account/device requests. Publication
follows the existing gated beta workflow; no issue comment is part of this
investigation. Reporter confirmation is still needed before claiming that these
source-backed fixes resolve their specific chart/tree variants.
