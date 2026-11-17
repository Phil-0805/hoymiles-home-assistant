# v0.6.2b4 — bounded inverter model recovery and clearer diagnostics

This beta investigates [issue #61](https://github.com/Phil-0805/hoymiles-home-assistant/issues/61),
where a previously recognized standalone HMS-2000-4WB now has unresolved model
metadata. Stable remains **v0.6.1**. The actual cause of the reporter's missing
metadata and successful recovery on that account are not yet confirmed.

## Changes from b3

- Retry missing startup model metadata at most twice: five and fifteen minutes
  after the preceding attempt finishes, on existing update ticks. Attempts run
  as one coalesced background task, using the existing endpoints, twelve-second
  attempt budget, request pacing, concurrency limits and server pauses.
- Keep successful model provenance and requery only devices with recoverable
  missing-data/connection outcomes. Identity, model-format, HTTP and redirect
  errors do not schedule recovery. Authentication/rate errors also stop the
  remaining optional metadata requests. No additional login or write retries.
- Cancel recovery on unload and discard results after station, device-tree or
  inverter changes. Original IDs, serials and topology remain unchanged.
- Add fixed `web_tree_reason` and `detail_reason` diagnostics to distinguish
  empty/missing metadata, unsupported representation/model, identity/serial
  mismatch, ambiguous candidates and known request errors. Export only a capped
  recovery count and pending flag in addition to those fixed reasons.
- After verified standalone recognition, use the existing guards to skip battery
  readers and select the existing output target. All control permissions, fresh
  reads, reported limits and complete readback confirmation remain mandatory.

The metadata acceptance rules are preserved. JSON-text metadata, numeric-string
identities and alternate model spellings are diagnosed rather than guessed.
Recovery does not recreate entities or rewrite registry labels; a newly discovered
different physical input count may require reloading the entry. The reported
four-input HMS retains its existing four-input entities.

The Live/URI path is independent of model discovery and is unchanged. This beta
therefore does not claim to fix missing station Live/PV values. Optional metadata
recovery does not wait in the fast update path, but shares the account HTTP budget
with other reads. Detail telemetry resumes on its normal chart schedule after
recognition. B3's optional history copies and their Recorder exclusions, b1's HMT
monitoring and b2's confirmed Home login correction remain included.

## Test on the affected Home installation

1. Install **v0.6.2b4** through HACS with beta versions enabled and restart
   Home Assistant Core. Keep the existing Home entry and account profile.
2. During production, export diagnostics after startup. If model discovery is
   still unresolved but recovery is pending, allow both recovery windows to
   complete (about twenty minutes plus request durations and update scheduling).
3. Compare `discovery.web_tree_reason`, `discovery.detail_reason`,
   `polling.model_discovery_recovery_attempts`, the pending flag and
   `standalone_hms_recognized`. Successful early discovery stops further attempts.
4. If the HMS is recognized, check battery-reader applicability, whether output
   settings become readable, and temperature/frequency/AC voltage after the next
   regular chart cycle. Report Live/PV behaviour separately.
5. If unresolved, share privacy-checked diagnostics and fixed stage/reason lines.
   Do not share credentials, serials, IDs, raw replies or unredacted captures.
   Identity/format failures need investigation; no alternative command is tried.

## Validation

Local verification: **1,393 HA tests plus 134 subtests on HA 2026.10.4** and
**56 unit tests**, Python syntax, translation-key parity, whitespace and release
packaging. Forty new tests exercise precise/private diagnostics, original-data
and provenance preservation, bounded recovery, completion-based delays, continued
Live updates, coalescing, unload cancellation, target changes and error handling.
Required PR/release CI tests HA **2026.10.4 and 2026.11.0**, HACS and Hassfest.
No real account, device or user Recorder database was accessed by the agent.

Thanks to @flo1990m for the detailed standalone report and comparison with b11.
[Investigation and limits](https://github.com/Phil-0805/hoymiles-home-assistant/blob/v0.6.2b4/docs/standalone-hms-issue-38.md#issue-61-bounded-model-recovery-in-v062b4-2026-11-17).
