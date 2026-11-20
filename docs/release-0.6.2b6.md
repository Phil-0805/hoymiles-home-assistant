# v0.6.2b6 — bounded model recovery and optional output-read pause

This beta addresses two observed paths in [#61](https://github.com/Phil-0805/hoymiles-home-assistant/issues/61).
The nighttime setup handling from b5 remains included for [#59](https://github.com/Phil-0805/hoymiles-home-assistant/issues/59).
Device confirmation is still needed; these changes do not prove that the two
reports have the same underlying manufacturer-side cause.

## Model discovery after inactive startup

Previously, missing model discovery stopped permanently after two startup
retries. If connected Live measurements return, or previously observed PV-chart
source timestamps advance and satisfy the existing freshness checks, the
integration can now schedule one additional bounded recovery cycle.

- At most two additional reads: five minutes after observing recovery, then
  fifteen minutes after completion of the first additional unsuccessful read.
- Chart-based recovery works even while the station Live URI remains missing.
  The first chart sample establishes a baseline; duplicate, stale, future or
  unrelated-device samples do not trigger recovery.
- Existing coordinator ticks start background reads. No periodic metadata loop,
  new timer or faster Live/chart polling is introduced. Repeated availability
  changes cannot restart further cycles in the same coordinator lifetime.
- The station/tree must remain unchanged. Existing model/identity validation,
  unload guards and nonretryable authentication/rate/identity failure handling
  remain in place. A missing model never grants output-control permission.

Diagnostics add `model_discovery_activity_rearmed` and
`model_discovery_activity_attempts` (0–2), alongside the existing startup retry
fields. If the cloud continues omitting model metadata, recognition may still
remain unresolved; no model is guessed or trusted from a persistent cache.

## Optional output-setting reads for a verified standalone HMS

- Explicit Live `con=0` defers optional output-setting refreshes.
- Missing Live alone still allows an independent settings read. Only an actual
  `cloud_rejected` read for the same verified target pauses subsequent optional
  reads while Live remains unavailable.
- When connected Live returns, reads resume on the existing schedule, preserving
  normal deadlines and account/server pauses.
- Diagnostics show `waiting_for_live` and `polling_paused`. A retained confirmed
  value keeps its original timestamp and is not presented as a fresh reading.
  The refresh button is unavailable while the read is paused.

This gate does not apply to storage/hybrid targets or unknown models. Explicit
writes still require fresh settings, bounds, permission/target checks and full
readback. There are no automatic write retries. The first real rejection, or an
already-running request, can still produce a warning; valid failures are not
silenced globally.

## Testing

Update to **v0.6.2b6** through HACS with beta versions enabled, then restart Home
Assistant Core. Keep the existing integration entry and configuration.

**For #61:** leave HA running from an inactive period through production resuming,
without another reload. Check model recognition, battery-read applicability,
inverter details and output settings separately. If recognition was unresolved,
allow approximately 20–25 minutes after fresh measurements begin progressing for
the additional recovery cycle to complete. Also check the following evening
whether repeated optional output-read failures stop under the conditions above.
Export diagnostics if the model remains unresolved or a warning persists.

**For #59:** check that startup still finishes while the inverter is inactive and
that daytime readings return automatically without another reload. This beta
does not change PV sensor availability rules or replace missing values with zero.
Historical zero-valued statistics and current entity availability are separate;
a fresh diagnostic export is useful if current zero/unavailable behavior remains
unexpected.

## Validation and limits

Local validation: **1,429 HA tests on HA 2026.11.0** and **56 unit tests**, syntax,
translation-key parity and whitespace checks. Forty new cases across the two
fixes cover recovery channels, duplicate/stale/future data, bounded retries,
context changes, unload, independent settings reads, retained timestamps and
fresh-write guards. Release CI additionally checks both HA 2026.10.4 and
2026.11.0, HACS and Hassfest before publication.

No real Hoymiles account/device commands or user database access were used.
Private diagnostics and identifiers are not included. Implementation/evidence:
[issue-61-output-polling.md](https://github.com/Phil-0805/hoymiles-home-assistant/blob/v0.6.2b6/docs/issue-61-output-polling.md).
