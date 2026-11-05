# Battery heating, light and display (v0.5.2b2 beta)

These controls are included in v0.5.2b2. Tests use synthetic responses; actual device confirmation
is still needed before claiming support for a particular firmware/model.

Enable **Allow device controls (heating, light and display; beta)** in the
integration options. This permission is separate from battery mode/SOC controls,
defaults to off and adds no requests while off. Enabling it creates:

| Entity | Meaning / range |
| --- | --- |
| Allow battery heating | Permission for automatic battery heating, not forced heating or activity |
| Battery indicator strip | On/off, RGB colour and brightness (0–255) |
| Display brightness | Whole percent, converted to the cloud's 0–255 scale |
| Indicator strip off delay | 0–3600 seconds |
| Display off delay | 0–3600 seconds |
| Refresh device settings | Read settings; at least 30 seconds between manual refreshes |

Settings are read every 30 minutes using the existing shared account request
budget. Failed or unsupported settings do not prevent ordinary telemetry from
working. Settings older than 60 minutes become unavailable. Light/display
controls require exactly one explicitly identified AC battery controller in
the station's device tree. Multiple controllers are not selected arbitrarily.
The manufacturer web UI suppresses strip settings for serial prefixes 2805 and
2806; this integration follows that restriction while retaining display support.
Missing strip fields also disable strip controls.

Each change takes a fresh snapshot under a lock, preserves other returned
light/display fields, sends one write and verifies the entire result by readback.
No optimistic state or automatic repeat write is used. Readback can be attempted
up to three times, three seconds apart. Avoid simultaneous app changes. A failed
confirmation can mean that the cloud did not confirm a write that already
reached the device; inspect the app before trying again. RGB changes without an
explicit brightness preserve the fresh brightness; turning on from zero uses
full brightness. Raw snapshots and controller addresses are not entity attributes.

The mobile app's named effects (Hoymiles, Rainbow, Aurora, etc.) and battery-level
lighting modes have no verified mapping in the inspected web client. They are
not exposed or assigned guessed command values. Zero-second delay is sent as
zero; no undocumented meaning such as “always on” is assumed.

## Manufacturer evidence

The public manufacturer web client was inspected on 2026-11-05:

- [Settings drawers](https://static.hoymiles.com/cdncache/website/js/index-COaHho1l.js):
  action 1518 for heating permission; action 1529 for RGB (`r/g/b`), strip
  brightness (`slb`), strip delay (`slot`), display brightness (`ldb`) and display
  delay (`sot`). SHA-256: `d932523a3183d7d24ad0ea26ae544eeaf63075b50189f3b5368974a9d0efd8f4`.
- [Command polling](https://static.hoymiles.com/cdncache/website/js/CommandState-BoPSD_r0.js):
  asynchronous read/write jobs and completion status.
  SHA-256: `5f65f776f7b0c49e92e60c0eb893e4992019cae0cef1ae7ea003265b354e0a57`.
- [Device transport](https://static.hoymiles.com/cdncache/website/js/device-AUWAMR52.js):
  `/pvm-ctl/api/0/dev/setting/read`, `/write` and `/status`.
  SHA-256: `57f331c97040a6976c0934c81652d4907e5cd5de9fe384207e3951fac3ed9596`.

Heating uses the manufacturer's `data.sid` station envelope. Light/display reads
use top-level `sid`, `dev_sn` and `dtu_sn`; writes put `sid` inside the complete
settings data. Existing station action-83 battery mode/SOC transport is unchanged.

## Beta device check

After installing v0.5.2b2 and restarting Home Assistant, enable the new
option and compare the controls with the app. Change one setting at a time,
confirm it in the app, refresh HA, and restore the previous value. Check both
light and display delays in seconds. Heating may stay physically inactive after
permission is enabled because the device decides when warming is needed.
Record beta/HA version, model, firmware and observed behaviour when reporting
results; omit credentials, controller addresses and unredacted screenshots.

## Development for b4: unavailable settings

Heating/display and cutoff reads now report separate fixed failure categories
in diagnostics, with only known response field types. Raw cloud responses,
arbitrary error messages, tokens and device addresses are not included.
The existing mode/reserve "Battery settings access" status does not describe
these separate reads. A failed read does not stop ordinary telemetry.

Short decimal integer strings returned by the cloud are accepted consistently
with the Android app. Booleans, fractions and arbitrary strings remain invalid.
Lighting data encoded as JSON text is decoded within the existing size/depth
limits. Known numeric lighting fields are normalized for full readback;
unknown settings retain their original values and types.

These changes improve protocol compatibility and diagnosis. The b3 export from
a second station showed only "unavailable", so it did not establish a specific
cause. If settings remain unavailable, use the relevant refresh button after
the 30-second cooldown and provide a new diagnostic export rather than deleting
and recreating the integration. No device write is needed to test the read.
