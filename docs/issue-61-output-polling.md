# Issue #61: optional output-read pause candidate — 2026-11-19

Status: prepared for v0.6.2b6 following the maintainer's release request on
November 20. This remains a candidate fix pending the reporters' device tests.

## Reporter evidence

[The b5 report](https://github.com/Phil-0805/hoymiles-home-assistant/issues/61#issuecomment-6985876679)
describes normal daytime operation and an `output_power_read/cloud_rejected`
warning after production stopped, without restarting HA. The private diagnostic
was read outside the repository; no raw export, identities or private snapshots
are included here. Relevant fixed/numeric observations:

- Standalone HMS-2000-4WB recognized through the web tree.
- Battery reads not applicable, reason `standalone_hms`.
- Live unavailable, reason `missing_uri`.
- Temperature, frequency and AC-voltage samples stale.
- Output status unavailable, but target-bound last-confirmed power and maximum
  remain 2000 W. The last read is not refreshed merely by displaying that value.

This isolates a different request from the original work-mode/battery-settings
warnings. Generic cloud status 1 does not establish inverter sleep, a network
failure or a new b5 regression. Missing URI is not explicit physical offline.

## Regression boundary

B5's output manager can attempt a scheduled read regardless of current Live
availability. However, merely skipping every read without a Live address would
break an existing supported case: `test_issue38_followup.py` explicitly verifies
successful independent output reads after model enrichment while Live URI is
missing. That test is retained unchanged. Settings availability and Live
availability must not be treated as equivalent.

## Local policy

The candidate uses current coordinator results, not local time, weather,
PV power equal to zero, old statistics or a guessed sunrise time. Only the
existing explicitly verified standalone-HMS target is eligible:

1. Explicit valid `con=0`: defer optional output-setting reads.
2. Live unavailable: keep an initial independent settings read possible. Only
   an actual read rejection with fixed reason `cloud_rejected`, bound to the
   same unchanged verified target, defers subsequent optional reads.
3. Current Live data returns: resume the existing schedule, preserving the
   normal deadline/account pauses rather than accelerating cloud polling.

An earlier rejection cannot pause a different station/inverter. Target changes
during an in-flight read cannot attribute that old rejection to the new target.
A successful settings read clears the rejection marker. Storage/hybrid targets,
unknown models and legacy callers without a Live-state source keep their prior
read behavior. Unload, permissions and original control guards remain.

Read eligibility is checked before scheduling and again under the existing
settings lock. Pausing clears scheduled short read-retries, without changing the
last-confirmed value, range or timestamp. Diagnostics show `waiting_for_live`
and `polling_paused`; the retained value remains `last_confirmed`, not fresh.
The read-refresh button is unavailable during the pause so a click does not
misreport a thirty-second cooldown as the cause.

The gate applies to read-only refreshes, not the write preflight/readback path.
An explicit write still needs a fresh cloud read, the freshly reported bounds,
target/permission rechecks and complete confirmation. A stale retained maximum
never authorizes a write. No automatic write retry or alternate action is added.

The first real cloud rejection is still logged, and an already-running network
request can still complete/fail after availability changes. This policy cannot
promise that no sunset warning will ever occur; it prevents unnecessary repeated
optional reads after the defined conditions are established. Genuine failures
while Live remains available are not muted.

## #59: graphs versus current entity availability

The reporter's screenshot shows current numeric zero values for all six PV
inputs. The maintainer's screenshot shows five-minute voltage statistics of
zero during a period when the current entity was unavailable. Those are different
observations; a historical zero does not establish current availability.

Existing module sensors use independently dated chart samples and connection
rules. `live_connected` tolerates a missing `con` field for legacy replies;
an explicit offline flag blocks voltage/current, while a fresh explicit zero
power sample has a separate existing availability exception. The current
screenshot does not identify which rule applies. Obtain the reporter's fresh
diagnostic and current connection-sensor state before changing availability.
This candidate does not alter sensor availability, chart decoding or statistics.

## Validation

Synthetic tests cover explicit offline, absent Live with/without a real settings
rejection, preserved independent reads, recovery/deadlines, a read queued on the
lock, retained values/ages, storage/legacy cases, permissions, unload, station/
inverter changes, in-flight target replacement and fresh-write failures/bounds.
No real account, device command or user database access is involved.

## New b5 diagnostic, 2026-11-20

[The new report](https://github.com/Phil-0805/hoymiles-home-assistant/issues/61#issuecomment-7031899307)
returns to unresolved recognition: both source reasons are `model_missing`, both
bounded recovery attempts are exhausted, Live is `missing_uri`, battery reads
are `not_excluded` and output has `no_unique_target`. No current action/maximum
is confirmed. This is different from the previously recognized-HMS export.
The output-pause candidate intentionally does not bypass that identity/model
requirement and therefore does not solve this unresolved state.

Known model metadata is retained during ordinary updates; the new discovery
state alone does not prove that an earlier recognized model was lost
spontaneously. The attached anonymized JSON supplied on November 20 matches
this issue export. The module chart source is about nineteen minutes old and
its observed progress about sixteen minutes old; detail sources are about
thirteen hours old. They must not be described as current telemetry. The fixed
`model_missing` labels establish missing metadata, not why the manufacturer
omitted it or whether the inverter physically slept.

## Local bounded recovery after measurements return

The exhausted startup schedule previously remained exhausted for the entire
coordinator lifetime. The candidate adds one second cycle for retryable missing
models, tied to the unchanged station/device tree:

- Observe a period without connected Live data or fresh module chart samples.
- Connected Live returns, or a previously observed module source timestamp
  advances and passes the existing source/progress freshness checks. Chart
  recovery works even while the station's Live address remains missing.
- After the two startup retries are exhausted, schedule at most two additional
  reads: five minutes after the activity observation, then fifteen minutes
  after completion of the first additional failure. If activity returned
  earlier, arm only while measurements are still fresh/connected.

The first chart sample establishes a baseline. Duplicate timestamps, merely
fetching old data, stale/future samples and other devices do not count. No
request is made by the chart callback; existing coordinator ticks start the
background task. Repeated Live flapping and later chart progress cannot create
further cycles. No new timers, endpoint guesses, model guesses, persistent
identity caches, write retries or relaxed control checks are introduced.
Already identified devices and nonretryable identity/model/authentication/rate
failures do not get an additional metadata retry. Existing in-flight result
checks discard results after unload, station/tree or inverter changes.
Diagnostics add only a boolean activity-cycle flag and a bounded attempt count.

This addresses the permanently exhausted recovery path. It cannot guarantee
recognition when the manufacturer continues returning no model. The reporter
must still test the actual night-to-day transition without reloading. No live
account/device commands were executed during development.
