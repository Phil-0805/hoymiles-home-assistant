# Issue 38 follow-up after b8 — local review, 2026-11-11

**Local follow-up, 2026-11-12:** see the [b9 daylight investigation](b9-daylight-investigation.md)
for corrected Home DTU/type nesting, chart handling, retained output display and
removal of the separate last-temperature entity. The historical findings below
refer to the published versions examined at the time.

Prepared for **v0.6.1b9**. See the [release notes](release-0.6.1b9.md).
This review does not claim that the reporter's hardware has tested the changes.
The original report and latest comments are in
[issue #38](https://github.com/Phil-0805/hoymiles-home-assistant/issues/38).

## Findings and changes

| Topic | Evidence / outcome |
| --- | --- |
| Cold startup without live URI | Reporter confirms b8 now starts with an inactive inverter. Preserve b8's independent station validation and partial startup. |
| Output control `no_unique_target` | Export identifies the HMS through `web_tree`; the selector used only the original tree. The mismatch is reproduced with synthetic data. Matching supplemental model information is now considered without replacing original device IDs, serials or topology. |
| Battery requests without storage | Reuse the same corrected standalone check for mode/SOC reads, battery-temperature polling and battery write guards. `enabled` remains the configuration flag; a new fixed `applicable` diagnostic flag distinguishes whether the reader applies. |
| Output setting at night | No production or live-URI condition is added to output settings. A real-coordinator test verifies successful output reading while URI discovery is unavailable and battery readers are skipped. Real API access/readback on the inactive device still needs testing. |
| Temperature displayed as 0 | Later reporter feedback says unavailable, with no paired app measurement. No evidence establishes zero as a universal missing-value sentinel. Genuine 0 °C remains valid; no shared or temperature-specific zero filter is introduced. |
| Last-known temperature | Maintainer chose current sensor unavailable when stale, plus a separate diagnostic entity showing the last sample and timestamp. HA deliberately omits ordinary extra attributes on unavailable entities; adding attributes to the unavailable sensor alone cannot satisfy that choice. |
| PV-input zero values stay available | Confirmed code defect: successful chart requests renewed sample age using request time. Runtime module parsing now retains each metric's aligned chart time, and each field expires independently. Re-reading the same old zero does not refresh its age. |
| Daily chart future tails | Both Home module and micro-chart decoders can select the latest finite sample at or before the requested local cutoff, rather than discarding the entire useful series because its last point is in the future. Sparse series keep their own label; unknown/misaligned axes are rejected. |
| Live-address warnings during partial startup | A successful response without a live address is now a deduplicated INFO event, not a failed-request warning. The typed missing-URI error still reaches the coordinator; b8 handles partial setup. Auth, HTTP, redirect, rate, invalid-data and genuine transport errors retain their warning/failure paths. |

The diagnostic export is used only as evidence for the allowlisted fields
summarized above. No attachment, real device identity, account information or raw
cloud settings are copied into this repository.

## Identity and write safety

Supplemental models must come from a verified `web_tree` or `micro_detail`
discovery result for exactly one matching positive-integer device ID, original
type 3 and unchanged original serial field. Conflicting duplicate web models or
serials are not arbitrarily selected. Boolean identities cannot verify device 1.
Unknown/mixed trees, multiple inverters, invalid identities and storage nodes
retain their previous rejection. No fallback to a different device or station
is added. The raw tree is not mutated to manufacture a topology.

Output continues to require explicit control permission, fresh phase evidence,
actual reported maxima, preflight under a lock and target rechecks immediately
before a single write. Complete relevant readback remains mandatory; a missing
confirmation never resends the command. Cached output values do not prove that
the API remains writable all night. The existing settings age/error policy is
not loosened to make a failed read look successful.

No new endpoint, command, account access, login retry or write retry is added.
Existing metadata requests are reused. Account-wide HTTP pacing, server pauses,
TLS/redirect rules, five-minute charts, thirty-minute settings, manual cooldowns
and bounded read recovery remain unchanged. Installer profile restrictions remain.

## Sample time and display

Home charts use the already inspected float32 ChartPB format. Installer float64
is not enabled through these readers. Request payloads and identity checks remain
scoped to the requested station/device/port. Only the three known module metrics
are accepted for input sensors; micro detail fields keep their existing meanings.

An HH:MM label is interpreted on the requested station-local date and converted
to UTC. A repeated or nonexistent DST wall-clock hour cannot be disambiguated by
this protocol and is not asserted to be a fresh sample. Nonascending/duplicate
axes, oversized axes, duplicate metric series and values beyond the axis are
rejected. Future samples and older replacements cannot refresh a newer reading.
No missing/nonfinite sample becomes zero. Missing fields retain earlier samples
only with their original timestamps and existing ten-minute expiry.

The normal temperature sensor remains a current measurement and expires. The
new **Last inverter temperature / Letzte Wechselrichtertemperatur** is an
explicit diagnostic value, with `sample_time` and fixed `sample_status=last_known`.
It has **no state class**, so an old repeated value is not presented as a new
measurement for long-term statistics. Its unique ID differs from the unchanged
current sensor. It is created only when extra inverter telemetry is enabled,
adds no cloud requests and has no effect on battery-temperature entities.

The diagnostic value uses this coordinator's in-memory chart cache. After a
restart, it remains unavailable until a valid chart sample is read; no restore
of an unverified former state or additional persistent snapshot is introduced.
Cloud PV day/month/year/lifetime totals and local energy integration are unchanged.

## Additional whole-integration review

The review also followed configuration/reauth/options, account/session isolation,
HTTP size/redirect/TLS limits, settings read/write flows, energy accumulation,
entity/registry ownership, migrations, unload, diagnostics and packaging/workflows.
During code review, the release/notification workflows were inspected without
being changed. Publication uses the existing release workflow.
No automatic notification or issue comment was sent.

Further confirmed defects corrected locally:

- Reserve-SOC service inputs are now validated as whole percentages in the
  existing 10–100 range before forwarding, rather than silently rounded. NaN,
  infinity, booleans and other invalid types produce a handled service error.
- Mode/SOC confirmation rechecks control permission and unload state before
  every follow-up read and again before publishing it. The original write is
  never resent; unloading after a write cannot undo a command already submitted.
- The older device-addressed battery fallback rejects multiple compatible
  controllers rather than returning settings from the first successful one.
  Noninteger device types, boolean command IDs and boolean/float success codes
  no longer masquerade as integer protocol fields. Existing missing-code legacy
  parsing remains supported; no new protocol coercion is inferred.
- Authentication and rate-limit errors in legacy verification/fallback reads
  propagate immediately. In particular, the rate-error subclass must not be
  handled by a generic connection-error fallback. Shared server pauses remain
  authoritative, and no additional login/write attempts are added.
- Exhausted legacy-device errors no longer incorporate even a serial-number
  suffix into error text. Known structural stage/reason diagnostics remain.

`tests/ha/test_general_code_review.py` covers these additional input, identity,
permission, unload and fallback cases. Current mode/SOC/light/display/cutoff
semantics, action IDs, registry migrations, URLs, auth algorithms, supported
profiles, cloud PV totals and energy integration formulas are not redesigned.

## Verification and open device tests

Synthetic tests cover the reporter pattern through real enrichment/coordinator
code; mismatched IDs/types/serials/provenance; ambiguous metadata; fresh limits
and complete readback; unchanged permission/target guards; exact per-input sample
age; sparse/foreign/future/invalid chart data; DST ambiguity; legitimate zeros;
real HA unavailable/current versus available/last-known states and omitted
statistics class; INFO deduplication, recovery rearming and log privacy.

Before considering Stable, obtain the reporter's daylight comparison for live
recovery, temperature versus the app and a deliberate output setting change
with readback/app confirmation. If nighttime output reads still fail after a
target is selected, inspect their fixed error reason rather than assuming they
must succeed. If a fresh temperature zero remains suspicious, obtain its sample
time and a contemporaneous app/device status; do not infer a sentinel from zero
alone. Actual raw-tree shape is not included in the original export, so the
model gap need not be the only reason an unknown topology remains rejected.

## Final local checks

1097 HA tests passed on each supported HA version (2026.10.4 and 2026.11.0),
plus 56 unit tests. Python syntax across integration/tests/scripts, translation
key parity, review links, whitespace and a 38-file local packaging smoke check
passed. Tests include real HA state publication for the last-temperature entity.
These are local results before the required release CI. The only HA 2026.11.0 warning is the known
pytest assertion-rewrite warning for an already imported anyio module.

PV input responses without a valid supported time axis now remain unavailable
rather than receiving an invented fresh timestamp. Different firmware chart
formats need verification before being interpreted. This review does not certify
all hardware, firmware, HA versions or every possible cloud response.
