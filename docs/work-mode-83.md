# Consumer work modes (station action 83)

Source inspected on 29 October 2026: the publicly delivered Hoymiles [WorkModeDrawer bundle](https://static.hoymiles.com/cdncache/website/js/index-COaHho1l.js), referenced by [the plant detail bundle](https://static.hoymiles.com/cdncache/website/js/index-CZ5oZNvO.js). SHA-256 of the WorkModeDrawer bundle: `d932523a3183d7d24ad0ea26ae544eeaf63075b50189f3b5368974a9d0efd8f4`.

This is direct inspection of the manufacturer's web client, not an authenticated command capture or hardware test. No account credentials or battery writes were used during this investigation.

| App selection | Action-83 mode | Integration mode (existing IDs) |
| --- | --- | --- |
| Self-Consumption | 2 | 1 |
| TOU | 3 | 8 |

These IDs differ from the action-1013 BMS enum. Never substitute that enum for this protocol.

The web client reads action 83 using the station ID and polls the job result. It reads SOC limits from the response and TOU selection from `k_3`. The integration also retains the previously supported `k_2.soc_l/soc_h` layout and rejects conflicting SOC evidence.

Observed write forms (inside action 83's `data`, alongside `sid`):

- Self-consumption: `{mode: 2, soc_l, soc_h}`.
- Existing recommended TOU: `{mode: 3, data: {mode: 1}}`.
- Existing basic TOU: `{mode: 3, data: {mode: 2, data: {id, week}}}`; the saved plan is read from `k_3.k_2`.
- Existing advanced TOU: `{mode: 3, data: {mode: 3, id}}`; the saved plan ID is read from `k_3.k_3`.

Only a supported, complete TOU selection actually returned by the account is offered. Basic plans require a fully read schedule and a nonnegative ID (including the Android custom selector 0); advanced plan IDs must be positive. Absent plans, negative default selectors and newer TOU submodes 4/5 remain blocked for writing. Switching does not call plan editing/deletion endpoints (such as configuration 502), invent schedules or expose a schedule editor.

Before a mode switch, read current settings once under the write lock and use the current saved target configuration, not the thirty-minute cache. After writing, require the original API method, readable settings, target mode and complete target configuration to match. No automatic repeat writes. All requests use the shared account budget and certificate-verified HTTPS with redirects disabled. Periodic polling remains unchanged.

The reserve-SOC control applies to the confirmed self-consumption settings only; TOU uses its own plan thresholds. A mode/schedule match confirms cloud readback, not that the battery physically charged/discharged. Real-device switching and comparison against the app remain required before stable publication.

## Explicit upper SOC limit

**Correction after b2 device feedback:** this is an upper work-mode SOC value.
Matching cloud readback did not change the separate app charge/discharge
cutoffs. b3 removes the b2 upper-limit control; the historical
implementation rationale below does not establish app-cutoff support. See
[corrected mapping](battery-charge-limit.md).

The same manufacturer bundle was fetched again on 5 November 2026; its SHA-256
still matches the source above. The self-consumption write includes both
`soc_l` and `soc_h`. The new upper-limit control therefore reuses action 83 and
its existing readback verification. It is enabled only when `soc_h` is actually
present in the selected read layout; the historical parser default of 100 does
not establish upper-limit capability. The control preserves the freshly read
lower limit, rejects unsupported/TOU modes and never retries the write.

App screenshots identify the feature and its percentage unit; they do not prove
command availability on every device. The new control still needs device/app
validation before being described as verified on a particular model.

## Local follow-up to issue #34 — 2026-11-09

The b1 reporter's new warning establishes a completed action-83 result with an
object payload, app mode 3 and TOU submode 2 (basic plan). The parser rejected
it before the legacy fallback also failed. The log does not expose the actual
plan or establish which individual validation failed.

The known manufacturer's WorkModeDrawer bundle above was downloaded again on
2026-11-09; SHA-256 is still
`d932523a3183d7d24ad0ea26ae544eeaf63075b50189f3b5368974a9d0efd8f4`.
This rechecks the archived protocol source, not a claim that its historical
filename is the currently loaded settings module. Its read handler assigns
`mode` independently of whether `k_3.k_2` supplies a usable ID/week, whereas its
submit handler builds a complete selected configuration. It distinguishes
negative/default plan IDs, but that does not establish the reporter's ID or
justify automatically recreating a default plan.

The local fix separates the readable current mode from safe write targets.
A successful command result with explicit integer mode 2/3 remains readable
when SOC or TOU configuration is incomplete. Conflicting SOC disables the
self-consumption write target; invalid or unsupported plans disable the TOU
write target. The existing strict command builders are unchanged. No default
schedule is created, no negative/string plan ID is newly allowed for writing,
and no additional API request is introduced.

`available_modes` can include the reported current mode for display;
`writable_modes` contains only fully validated targets. The select displays
that current mode and remains usable when a safe target exists, including
switching from a read-only TOU configuration to validated self-consumption.
A current-mode selection is a no-op; direct requests to write a display-only
mode are rejected. With no safe target, the select remains unavailable and
the read-only mode sensor can still show the reported mode. Existing fresh
read, lock, permission checks and full write confirmation remain in force.
Reserve SOC is still writable only for verified active self-consumption.

A known readable action-83 mode no longer triggers action-1013 fallback merely
because its plan cannot be resent. This prevents that fallback from masking
the current app mode. Unknown modes, invalid payloads and unsuccessful command
results remain rejected. This fixes the demonstrated code coupling, but the
reporter's exact missing/conflicting fields and device confirmation are still
pending. Recurrent live-data gaps are outside this change.

Local validation: 896 HA tests and 134 subtests on each of HA 2026.10.4 and
2026.11.0, plus 56 unit tests. The new synthetic cases cover read-only TOU,
missing/default/malformed plans, conflicting SOC, no legacy fallback, select
availability, forbidden TOU writes and loss of capability during a fresh read.
No real account/device operations were performed. The initial local validation preceded the b2 version bump;
this follow-up is included in v0.6.1b2.

## Existing basic-plan activation: Android custom selector 0

A further static trace through the same archived Android V2.13.0 package
identifies a concrete compatibility defect in the earlier positive-only check:

- `StationSystemBmsBleSettingWorkModeV1Activity` reads the basic selection from
  `WorkModeBean.data.k_3.k_2.week`. Its submit path passes `EconomicModeType.BASE`,
  the selected week list and a default-plan comparison flag to
  `WorkModeRequestHelper.T()`.
- `WorkModeRequestHelper` sets action **83** in its constructor. In `T()`,
  `WorkModeType.ECONOMIC.getMode()` resolves to **3** and
  `EconomicModeType.BASE.getType()` to **2**. For a custom basic plan it explicitly
  sends `data.id=0`, alongside `data.week`; the default branch sends -1.
  Thus zero is an evidenced custom-plan selector, not an invented device ID.
- `p()` serializes each selected weekday group and its `dcs`; `r()` serializes
  known action types and `start_time`/`end_time`. The enum defines numeric actions
  1, 2, 3, 4 and 255. This is manufacturer-code evidence, not an inference of
  numeric command values from the user's screenshots.
- `CommandRequestHelper.d1()` uses `PVMC_STATION_CTL_WRITE_C`; `Y()` puts the
  selected station's `sid` in the command's data. `J0()` is the corresponding
  read; `U0()` polls status. The existing integration transport matches this
  call chain. No configuration-502 editing endpoint needs to be introduced for
  activation of a complete plan already returned by action 83.

The relevant helper/enum methods are readable; unrelated decompilation failures
are not used as evidence. Base APK hash was verified again:
`0b0e12fcc3bd14bbb10188a1055eed06bfac44e9e332f8d6b5597a5d69e9a633`.
Mirror/signature limitations remain as described in android-app-protocol.md.

The local implementation accepts an **explicitly returned** custom selector 0,
while retaining positive IDs supported by the existing web-based path. It does
not fill a missing ID with zero, infer a default/custom plan from screenshots,
activate negative default selectors or create a new schedule. Android's read
model does not require an ID member; if an installation returns only week data,
its safe reactivation semantics still require further evidence. The reporter's
log does not establish the actual ID or missing field, so ID zero is not yet
proven as his individual cause.

Before advertising a basic plan as writable, validate nonempty weekday groups,
unique integer weekdays 1–7 without duplication across groups, nonempty action
lists, known integer action types, HH:MM times, increasing/nonoverlapping periods,
and valid types/ranges for any supplied SOC/power fields. Partial-week and daily
coverage gaps are preserved rather than silently filled. Unrecognized/cross-
midnight interval forms remain read-only. Unknown returned fields within weekday groups and periods are retained,
with the existing finite-JSON/size bound. The signed-integer power-field bound
is a transport validation bound, **not** a device power capability or a new
power setting. No interval or threshold is clamped, reordered or synthesized.

Activation uses the fresh plan read under the existing lock, sends one action-83
write and requires full plan/mode confirmation. A disappeared or invalid fresh
plan blocks the write. No retry writes, new account requests, plan editor or
additional service inputs are introduced. Final device verification remains
pending; these changes are included in the authorized v0.6.1b2 beta.

Combined local validation after the basic-plan addition: **928 HA tests and
134 subtests on each of HA 2026.10.4 and 2026.11.0**, **56 unit tests**, Python
syntax, translation-key parity and whitespace checks passed. Device confirmation
remains pending. No issue comment was posted.
