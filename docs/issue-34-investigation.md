# Issue #34 — mode and reserve unavailable after TOU change

Read on 2026-11-09: [report and maintainer follow-up](https://github.com/Phil-0805/hoymiles-home-assistant/issues/34).
Reporter: integration 0.6.0, HA 2026.10.4, HiBattery 4020 X/S. Reports unavailable
battery-mode/reserve entities and a self-consumption display after switching
to TOU. Exact entities and selected TOU submode are not yet supplied. No new
comment or request was posted by the agent.

## What the supplied logs establish

- `battery_settings_read/cloud_rejected`, envelope status 1 and null data:
  a battery-settings request was rejected. This stage describes the older
  action-1013 read, not the initial action-83 work-mode read.
- `other_api/http_error`, HTTP 404: an operation was not found; this generic
  label does not identify its endpoint. Do not attribute it to a specific probe.
- `other_api/cloud_rejected`, envelope status 2 and object data: an envelope
  rejection, not proof of a command's `code=2` execution status.
- `live_data/invalid_live_data` and later recovery: the returned sample lacks
  accepted fields and a subsequent valid sample was accepted. This does not
  establish a rate limit, login failure or a causal connection with TOU.

The login candidate's region change is not an established fix for this report.

## Code findings

The action-83 parser maps app mode 2 to self-consumption and mode 3 to TOU.
It already supports returned recommended/basic/advanced TOU selections (submodes
1/2/3), subject to complete existing plan data. Submodes 4/5, malformed data,
missing basic/advanced plans and conflicting SOC evidence are rejected. These
write restrictions prevent creating or guessing a plan; they must not be relaxed
based only on this issue.

A rejected active TOU configuration currently discards the entire action-83
read and enters the older battery-settings fallback. The fallback or subsequent
verification can then fail separately. This is a plausible path to investigate,
not proof of what the reporter received. A stale action-1013 mode after an
app-mode change is also possible; the supplied report does not establish that
it occurred. Do not treat the old fallback as proof of the active app mode.

The reserve control is deliberately restricted to verified self-consumption
settings. TOU uses plan-specific thresholds. Thus unavailable **reserve control**
in TOU can be expected, while a stale mode or failure to read all settings needs
separate investigation. The sensor and select are separate entities; their exact
IDs matter. A persisted old displayed state does not by itself prove that a new
cloud read returned self-consumption.

## Local diagnostic improvement

The prepared v0.6.1b1 candidate now emits the fixed warning
`stage=work_mode_read reason=invalid_work_mode_settings` if the action-83 result
reaches the parser but is rejected. The summary includes only bounded command
code, known app mode (2/3), known TOU submode (1–5) and fixed types of selected
known fields. It contains no plan IDs, schedules, arbitrary keys/text, SOC values,
account/device identifiers, job IDs or credential material. Because this is an
unwrapped command result, it does not invent envelope-status or URI labels.
Repeated identical failure shapes use the existing warning deduplication.

Parser acceptance, fallback behavior, controls, polling and retry timing are
unchanged. This is diagnostic preparation, **not a confirmed fix**. Synthetic
tests cover invalid/missing/unsupported TOU data, valid TOU, privacy, preserved
input and deduplicated warnings.

## Remaining evidence

The maintainer already asked in the issue for TOU submode, exact affected
entities, current app behavior/settings and a privacy-checked diagnostic export.
Those replies are still pending. No duplicate request is needed now.

For a later candidate test, use the existing read-only battery-settings refresh
once and inspect its new warning if present. A working action-83 parser will not
emit this warning, so absence alone does not prove success. Compare app mode and
HA mode, and distinguish reserve sensor from reserve control. No mode switch,
plan modification, integration deletion or password change is needed solely to
collect this evidence. Keep the live-sample problem separate until observations
establish a relationship.

Validation after this addition: 874 HA tests and 134 subtests passed on each
of HA 2026.10.4 and 2026.11.0; 56 unit tests passed. Syntax, local links,
updated release ZIP and whitespace checks passed. No real account or device
was accessed; the candidate remains local and unpublished.

## New reporter evidence and local fix after b1

The reporter confirmed basic TOU and identified the affected entities as the
mode select and reserve number. His new warning contains `command_code=0`,
`app_mode=3`, `tou_submode=2`, object settings and integer top-level SOC fields.
This establishes rejection of a completed work-mode response by our parser,
but not whether plan completeness or conflicting SOC triggered it. He also
explained that the different GitHub accounts are his own; do not count this as
an independent second installation.

The local follow-up keeps a known current mode readable without requiring its
configuration to be safely writable. It avoids legacy fallback for such results
and separates validated write targets from display. The select can switch to
self-consumption only if its SOC settings are valid; an incomplete TOU plan
cannot be written or recreated. Reserve control remains unavailable in TOU.
See [the implementation and source notes](work-mode-83.md#local-follow-up-to-issue-34--2026-11-09).
This code fix is included in v0.6.1b2; device confirmation is still pending.

### Further basic-plan finding

The Android activation helper explicitly sends **ID 0 for a custom basic plan**;
the previous parser's positive-only check rejected it. The local fix now accepts
an explicitly returned zero together with validated complete week/period data,
uses only the fresh plan during activation and verifies full readback. Missing
IDs or default selectors are not guessed. It is still unknown which field was
rejected in the reporter's actual response. See the Android trace and limitations
in [work-mode-83.md](work-mode-83.md#existing-basic-plan-activation-android-custom-selector-0).
The fix enables reuse of an existing supported plan, not creation/editing of
new time windows in HA. Reporter testing is required before claiming resolution.
