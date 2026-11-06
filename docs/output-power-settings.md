# Output power commands: manufacturer evidence

The public manufacturer web client was inspected on 2026-11-05. It exposes two
different operations. The screenshot's output-power **upper limit** must not be
silently substituted with the running output-power setting or grid-export limit.

## Configured output upper limit: configuration 515

`OutPowerLimitConfigDrawer` reads and writes station configuration type **515**:

- Read: `POST /pvm/api/0/station/setting/cfg_g_m`, body `{sid, type: 515}`.
- The returned data contains a `515` block with `max_power` and, where supplied,
  `power_a`, `power_b`, `power_c`.
- Write: `POST /pvm/api/0/station/setting/config`, body
  `{sid, type: 515, data: {max_power, power_a, power_b, power_c}}`.
  JavaScript omits undefined phase values when serializing the request.
- Values are watts; the drawer validates whole values starting at 100 W.
- Phase information is read from `POST /pvm/api/0/station/phase/type_s_c` with
  `{sid}`. The drawer also reads the station's inverter list.

The UI derives an upper range of 2000 W per phase, or 2500 W for series 2805/2806,
then multiplies by its phase count. These UI bounds and defaults are not evidence
of the permissions or hardware limits of any particular account. Do not infer
an allowed increase from a displayed device series or a default value.

## Running output setting: action 84 / 1532

`OutPowerConfigDrawer` uses device-settings **action 84** with `data.sid` and
`data.power` for a single-phase station. Its readback contains the current
`power` and an upper `max_power`. It defaults a missing upper bound to 2000 W;
that default is not a verified capability and must not become a HA control range.

If the phase endpoint returns phase entries, the drawer switches to **1532**.
Writes use `{type: 0, power_total, power_a, power_b, power_c, sid}` in `data`;
readback uses `out_power_total`, `out_power_a`, `out_power_b`, `out_power_c`.
Do not mix these read and write field names or select action 84 without checking
the station layout.

## Implementation: v0.5.2b4 beta

b4 adds **Output power limit / Ausgangsleistungsgrenze** in watts,
behind **Allow battery controls**. It follows the app's effective output-power
setting (84/1532); it does not raise configuration 515, a device's allowed
maximum, or a grid-export limit.

The Android phase endpoint `/pvmc/api/0/station/phase/type_s_c` is checked for
every settings read. An explicit empty array selects action 84. An explicit
non-empty array of unique A/B/C phase names selects 1532, output `type: 0`.
A failed, absent or malformed phase response is never replaced with an action-84
fallback. JSON-text phase arrays are bounded to 128 characters and validated.

Only returned integer settings and limits enable the number: `power` and
`max_power` for 84, or all active output-phase values and maxima for 1532.
Missing limits do not become a 2000 W default. Unsupported or incomplete settings
remain unavailable. The control starts at 100 W and cannot exceed the freshly
reported `max_power`. A unique AC battery controller is required; ambiguous
multiple-device trees are not selected arbitrarily.

Every write takes a fresh snapshot under a lock, checks permission and controller
identity again, rejects a changed phase layout and preserves active phase values.
The total output setting is written once. Readback must confirm the total, phase
values, limits, action and layout; failed confirmation never resends the write.
Simultaneous app edits cannot be made atomic by this unofficial API.

Settings refresh every 30 minutes while battery controls are enabled, with a
separate manual refresh button (30-second cooldown). Each read involves a phase
request, a command-read request and command-status polling, all through the
existing shared account budget. Diagnostics contain only fixed statuses,
phase names, action, total watts and maximum watts. No controller addresses or
raw responses are exported.

This new control has synthetic test coverage but still needs an actual device/app
comparison before hardware success is claimed. The historical b3 release is unchanged. The new control is included in b4.

## Sources

- [Manufacturer settings drawers](https://static.hoymiles.com/cdncache/website/js/index-COaHho1l.js),
  SHA-256 `d932523a3183d7d24ad0ea26ae544eeaf63075b50189f3b5368974a9d0efd8f4`.
- [Manufacturer station transport](https://static.hoymiles.com/cdncache/website/js/index-CTUY73vV.js),
  fetched on 2026-11-05, SHA-256
  `a2790e4875668e9de1f8a3aacb0164bffbfe8cfb6ca4180e042330aac3240c98`.

These are public client implementation details, not a published API guarantee
or an authenticated device command capture.

## B8: stored value outside the current write range

The maintainer's web read returns an explicit empty phase list and a settings
record with `power=2000`, `max_power=800`, and phase limit fields of 800. Only
these allowlisted numeric values were retained, without account/device data.
An empty phase list selects action 84, not 1532. The stored power setting is
not evidence of actual physical output or permission to write 2000 W.

The previous parser rejected that entire record because it required the stored
value to fit the current write range. B8 preserves the actual
stored integer even outside that range while still requiring explicit valid
limits. It does not clamp the reading to a fictional 800 W. The number remains
readable at 2000 W with a maximum allowed new setting of 800 W, and can be lowered
after the existing fresh-read preflight. A write above the freshly reported
maximum remains blocked, including a no-op request for the old 2000 W value.
Values below 100 W are likewise readable, while new total settings remain
restricted to at least 100 W. No maximum is invented when it is absent.

The app's `getInteger` / `Integer.parseInt(String.valueOf(...))` parsing also
supports short decimal integer strings. Known output values/limits and station
job status codes are now canonicalized at the response boundary. Floats, booleans,
oversized/invalid strings and missing values stay rejected; service inputs stay
strict. For phases, a stored counterpart above its own fresh limit is readable
but blocks a write that would resend that invalid counterpart.

A separate source cross-check found that the 1532 read incorrectly included
`type=0`. Both the archived web `OutPowerConfigDrawer` and Android
`PhaseConstraintLayout.w` → `CommandRequestHelper.J0/Y` read with `{sid}` only.
B8 removes the read-side type. Writes still use `type=0`:
`OutPutPowerActivity` calls `PhaseConstraintLayout.B(..., 1, ...)`, which writes
`type = argument - 1`. This does not explain the maintainer's phase-empty case;
the captured out-of-range stored value does.

Fixed output phase/settings/command error reasons now include only known field
type labels. No raw settings snapshots or identifiers are added to diagnostics.
Synthetic tests reproduce the 2000/800 record, a permitted lowering to 800 W,
blocked writes above 800 W, numeric-string roundtrips, complete readback and the
exact phase read/write payloads. Device-level confirmation of the updated control
is still pending. Polling frequency, configuration 515 and permissions are unchanged.

## Android cross-check

Android V2.13.0 independently uses action 84 for the legacy output-power page
and 1532 for phase controls, through station_ctl routes. This confirms the
commands in that app implementation, not the settings of a live device. See
[APK provenance and method chain](android-app-protocol.md).
