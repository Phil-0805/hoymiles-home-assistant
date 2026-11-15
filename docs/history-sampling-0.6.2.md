# Optional history sampling for v0.6.2

Status: original design proposal, 2026-11-13; local implementation started for
v0.6.2b3 on 2026-11-15 following the maintainer's request. This document retains
the design rationale. Current behavior and setup: [usage guide](history-sampling-usage.md).
The maintainer subsequently authorized the b3 release. No automatic Recorder
configuration change is included.
Tracking: [issue #51](https://github.com/Phil-0805/hoymiles-home-assistant/issues/51).
Baseline: stable v0.6.1, commit `33598495c864f1f18eee59df1a979ea1abb367e0`.

## Problem and Home Assistant constraints

The reporter wants responsive live dashboards and automations while reducing
Recorder rows. Their reported 24-hour counts are 10,569 for daily household
consumption and 6,967 each for PV and load power. These are installation-specific
observations, not a benchmark or a count of API requests.

Recorder normally stores state changes. Its documented entity filters can
exclude selected originals without disabling those entities in Home Assistant.
The supported configuration does not offer a per-entity sampling interval that
leaves all live state changes available but selectively records them.
Increasing `commit_interval` batches database commits; it does not select one
state per interval. Excluding attributes alone does not sample changing values.

Consequently, adding slower entities only saves rows when the user also excludes
the corresponding live entities from Recorder. Keeping both sets recorded can
increase storage. Excluding originals also stops their new Recorder-backed
history/statistics; existing dashboards with historical graphs must use the new
entities for those graphs. Current-value cards and automations can keep using
the originals. Existing rows are not migrated or deleted.

## Recommended user-facing design

Recommendation after comparing other integrations: keep all existing live
entities intact, add opt-in sampled copies, and document short retention as a
separate optional Home Assistant automation. Do not build a private Recorder
filter, direct database deletion or a replacement statistics engine.

Add one station option, available for Home, Installer and Enduser profiles:

| Option | Meaning |
| --- | --- |
| Off (default) | Existing entities and behavior only |
| 10 / 15 / 30 / 60 seconds | Enable separate sampled history entities |

Use 30 seconds as the documentation example. Existing configurations remain off;
no changes to current entity IDs, units, automation references or cloud polling.
The option controls local publication, not freshness of measurements at Hoymiles.

Suggested entity names: `PV power (history)` and `Load power (history)`, with
equivalent English/German names for the other supported measurements. Unique IDs
should use the existing config-entry prefix and a stable `_history` suffix.
Changing the interval must retain those identities and their historical series.
Turning the option off should unload the sampled entities without deleting their
registry entries or history; turning it on again should reuse them.

Explain the two steps together in the options description and README:

1. Enable history entities and choose an interval.
2. Exclude the desired original entities in the user's existing Recorder config,
   then use the corresponding history entities in historical charts.

Do not edit the user's YAML or Recorder internals automatically. Do not disable
live entities: disabling an entity also removes its live use.

## Short retention is a separate choice

Home Assistant already provides `recorder.purge_entities` with `keep_days`.
Its entity-specific purge path removes matching old states, linked events and
unused attributes; the inspected Core 2026.11.0/2026.11.1 path does not delete
statistics tables. This preserves already compiled long-term statistics, but
does not create missing statistics or guarantee that an existing sensor's
statistics were valid. Verify statistics before recommending deletion.

Use a user-owned, optional daily automation selecting exact sensor entities and
an explicit `keep_days: 2`. A later blueprint could make selection easier; do
not implement automatic deletion inside the integration. Leaving retention
unchanged remains the default. Do not use a domain-wide purge or change global
`purge_keep_days` to two days: that would affect unrelated integrations too.

The choices have different effects:

| Per-sensor choice | Live behavior | New rows | Retained detailed history |
| --- | --- | --- | --- |
| Original recorded, normal retention | Unchanged | Unchanged | Normal HA retention |
| Original recorded, targeted 2-day purge | Unchanged | Unchanged, plus cleanup work | Approximately 2–3 days with daily successful cleanup |
| Original excluded, sampled copy recorded | Original stays fast | Reduced to sampled publications | Sampled entity follows normal HA retention |
| Original excluded, sampled copy with targeted purge | Original stays fast | Reduced to sampled publications | Sampled history approximately 2–3 days |

An original excluded from Recorder cannot simultaneously retain two days of
raw history. Keeping originals recorded for two days plus slower copies for
longer history is possible, but increases initial writes and is not the
recommended write-reduction mode. Global purge can shorten any of these windows;
a targeted purge cannot extend the global retention.

Two days means a rolling age cutoff at each cleanup, not exactly two calendar
days or an immediate eviction at 48 hours. Missed automation runs retain more.
Deleting rows also need not immediately shrink SQLite's file: reusable free
pages and Home Assistant's separate repack behavior matter. Do not run a VACUUM
or force a repack after every cleanup.

## What other integrations do

| Reference | Verified behavior | Lesson for this integration |
| --- | --- | --- |
| HA Filter, `time_throttle` | A separate sensor accepts the first eligible source event after the window. Source entity remains independent. | Closest existing pattern for separate history copies; original still needs Recorder exclusion for fewer writes. |
| ESPHome sensor filters and Copy | Sensor values can be throttled or averaged; copies can have their own filters. Filtering before HA publication reduces what HA receives on that entity. | Reuse the separation concept, but do not throttle the only live stream or silently substitute an average. |
| Powercalc group power/energy sensors | Underlying changes are processed internally; publication of group sensors is throttled. Individual energy update intervals also exist, but are not a blanket Recorder sampling setting. | Separate internal calculation from publication; document that a throttled entity itself updates less often. |
| Native Recorder entity purge | Supports targeted entity selection and a retention age. | Reuse the supported user automation for retention instead of writing a custom database cleaner. |

Inspected HA Filter's installed 2026.11.0 `TimeThrottleFilter` and source-event
handler as well as its documentation. It is an event-based throttle, not an
exact wall-clock sample timer. A generic filter also has no knowledge of this
integration's daily-counter reset boundary; do not assume it preserves the final
unpublished old-cycle energy value. The comparison is not a claim that other
integrations solve the complete requirement automatically.

An alternative inspired by Powercalc would throttle publication of the existing
daily energy entities while still integrating every live power sample. This
would preserve energy entity/statistic identities and avoid a statistics-source
switch. However, it also delays energy-based dashboard values and automations.
It therefore needs explicit opt-in and is not equivalent to the issue's strict
request to keep original sensors fully responsive. Keep it as a documented
design alternative, not a silent optimization.

## Sensor scope

| Existing measurement key | Proposal |
| --- | --- |
| `pv_power`, `load_power`, `grid_power` | Sampled power copies |
| `battery_power`, `battery_charge_power`, `battery_discharge_power` | Sampled power copies, same source availability rules |
| `load_energy_today` | Sampled energy copy, subject to the reset/statistics gate below |
| `battery_charge_energy_today`, `battery_discharge_energy_today` | Same energy rules as daily consumption |
| Station PV day/month/year/lifetime energy | Keep existing roughly minute-based cloud reads; no duplicates initially |
| Module values, temperatures, settings and status codes | Outside initial scope |

The daily consumption counter must be addressed explicitly: it accounts for the
largest row count in the report, despite the issue title referring to power.
Battery history copies must never create measurements that the original source
cannot supply. Enduser remains station-only, experimental and read only.

## Sampling and availability semantics

Recommended implementation uses the existing coordinator notifications and a
monotonic publication deadline per sampled sensor. On the first eligible update
at or after the deadline, capture the latest valid source value. Intermediate
notifications do not change the history entity's value or attributes.

This is latest-value sampling, not an average, smoothing filter, maximum or a
recalculation of energy. Short peaks between samples can be absent from power
charts, and power statistics can differ from the full-resolution series.

The interval is a minimum spacing for ordinary value publications, not an exact
wall-clock schedule. For example, a 10-second setting with updates every three
seconds may publish every 12 seconds. If the server supplies data more slowly,
sampling cannot produce additional fresh measurements. No extra cloud requests,
poll-rate changes, independent catch-up requests or fabricated intermediate data.

Source unavailability and recovery should be published immediately, independently
of the deadline. Never retain a cached numeric sample as available after its
source becomes unavailable, and never replace missing values with zero. These
availability transitions, initial publication and energy-cycle boundaries are
explicit exceptions to the normal spacing limit.

Use the same source extraction, selected PV source, validity and connection rules
as the original entities. Refactor common evaluation only if required to avoid
two divergent sets of rules. Settings-only notifications must not make failed
live data healthy or bypass the publication deadline. No restored old history
value should be presented as a new measurement after restart.

History entities should retain the source unit, device class and applicable
state class. Do not force-update identical values or attach continuously changing
age/timestamp attributes: those would create unnecessary state changes. No raw
payloads, device identifiers or credentials in new diagnostics.

## Daily energy: implementation gate before inclusion

Keep the existing energy integrator processing every valid live sample. Sample
the accumulated counter, never integrate the sparse history power samples.
Changing the history interval must not change the calculated energy.

Simply copying the daily counter every 30 seconds is insufficient. For example,
the last published old-day value could be 1,000 Wh while the integrator has
already reached 1,005 Wh before its next reset. Publishing only the new day's
counter can lose the old day's unpublished 5 Wh from the sampled statistics.

The energy design therefore needs an explicit cycle-boundary path: retain the
last actually accumulated old-cycle counter, publish its final observed value
before publishing the new cycle, and preserve event order. The existing
`battery_energy.date` and the station timezone identify this cycle. A hook before
the coordinator resets its counters is a candidate; current sensor callbacks
alone see only the post-reset data. No guessed midnight value or integration
across missing-data gaps is allowed.

Verify the resulting sums with the real Recorder/statistics machinery on both
supported HA versions, including a reset within one statistics period. Restart,
unload and option changes near a reset also need coverage. Any proposed shutdown
flush must use an already observed counter, not extrapolate energy.

If this cannot be demonstrated safely for b1, release power sampling only and
explicitly document that the reported daily-consumption row volume is not yet
addressed. Do not recommend excluding the original energy counters or migrating
the Energy dashboard to sampled energy until this gate passes. Even afterward,
new history entities start separate statistics; no automatic historical merge
or Energy dashboard replacement is planned.

## Expected reduction and limits

The maintainer supplied another 24-hour count: daily consumption 27,312, load
power 25,016 and PV power 6,872, totaling 59,200 states. No account, station or
entity identifiers are retained here. This supports investigating both power
and energy, but does not establish database byte size, physical disk writes or
whether every row represents a numeric change rather than an attribute or
availability transition. Those distinctions need a read-only baseline analysis.

At a 30-second minimum spacing, ordinary publications are at most about 2,880
per continuously active sensor per day; at 60 seconds, about 1,440. Unchanged
values can produce fewer rows; initialization, availability transitions and
cycle boundaries can add rows. These are publication estimates, not promised
database sizes or measured savings. Existing retained rows and statistics remain.

For these three sensors, 30 seconds gives approximately 8,640 ordinary
publications/day and 60 seconds 4,320, before the documented exceptions.
These estimates only apply when all three have sampled replacements and their
originals are excluded. Merely purging the original daily counter after two
days leaves its roughly 27,000 new states/day unchanged.

## Proposed implementation order and beta acceptance

1. Establish the baseline: numeric versus attribute-only changes, unavailable
   periods and current statistics health. Use user-supplied aggregate results,
   not uploaded databases or private device data.
2. Build shared source evaluation and opt-in sampled power copies. Test exact
   publication behavior with the real HA state machine and Recorder.
3. Add daily energy only after proving unchanged internal integration and correct
   reset/statistics behavior. Do not call the whole issue solved with power alone.
4. Document exact Recorder exclusions and selection of history entities in charts.
   Provide a separate optional native retention automation example; no automatic
   history deletion on upgrade or when changing sampling settings.
5. Validate a complete local installation over daytime changes, midnight and
   restart, then compare an equivalent 24-hour window. Measure original live
   responsiveness, sampled rows and daily energy totals separately.

Keep the concept, implementation and publication as distinct steps. The original
request covered the concept; implementation for b3 was subsequently requested.
A beta is useful for installation feedback
after synthetic and real-Recorder tests, not a substitute for those checks.

## Validation plan for subsequent implementation

- Real HA state tests: original values update at every coordinator event while
  history values/attributes stay fixed until eligible; all four intervals.
- No-option regression, profile boundaries, multiple config entries, stable
  identities, disabled entities, interval changes and off/on reload lifecycle.
- Actual Recorder test: excluding an original preserves its live updates and
  records only eligible sampled changes; without exclusion, both are recorded.
- Missing measurements, failed polls, settings-only notifications, explicit zero,
  signed power, immediate unavailability/recovery and slower server intervals.
- Daily-counter totals unchanged; reset ordering, station timezone/DST, gaps,
  reload/restart and Recorder statistics sums tested before energy inclusion.
- Retention guidance: test the targeted native purge on a synthetic database,
  preserving unrelated entities and compiled statistics; never use a real user's
  database for deletion tests. Off/no-option paths must never issue a purge.
- Assert unchanged cloud request counts and intervals, no new writes, no leaked
  listeners after unload, then run the repository HA/unit/syntax/translation checks.

Implementation touchpoints: `const.py`, both options forms in `config_flow.py`,
`sensor.py` and a small sampling helper if useful. Daily-energy boundary handling
may also require a narrowly scoped change in `coordinator.py`. Add synthetic
tests and English/German usage documentation. Version/release notes and the
`beta/v0.6.2` workflow trigger belong to a separately authorized release step.

## Sources inspected

- [Issue #51](https://github.com/Phil-0805/hoymiles-home-assistant/issues/51)
- [Recorder configuration and entity filters](https://www.home-assistant.io/integrations/recorder/)
- [Sensor state classes and statistics](https://contributors.home-assistant.io/core/entities/sensor/)
- [Built-in Filter time throttle](https://www.home-assistant.io/integrations/filter/#time-throttle): an existing manual alternative, also requiring Recorder exclusion of the original for storage savings.
- [ESPHome sensor filters](https://esphome.io/components/sensor/#sensor-filters)
  and [Copy sensor](https://esphome.io/components/copy/#copy-sensor).
- [Powercalc update frequency and throttling](https://docs.powercalc.nl/configuration/update-frequency/).
- [Targeted Recorder purge and keep_days](https://www.home-assistant.io/actions/recorder.purge_entities/).
- [Core 2026.11.1 entity purge implementation](https://github.com/home-assistant/core/blob/2026.11.1/homeassistant/components/recorder/purge.py).
- [Recorder event filtering, Core 2026.10.4](https://github.com/home-assistant/core/blob/2026.10.4/homeassistant/components/recorder/core.py)
- Installed Core 2026.11.0: Recorder event filtering, `entity_options.py`,
  attribute exclusions and the sensor publication path; repository station
  sensors, options forms, coordinator polling and daily energy reset/integration.

No real accounts, devices or user Recorder databases were queried. The local
implementation uses synthetic HA state-machine, Recorder and statistics tests;
installation feedback and publication remain separate steps.
