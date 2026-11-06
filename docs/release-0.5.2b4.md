# v0.5.2b4 — output power limit beta

This prerelease adds the app's effective output-power setting. Stable remains
v0.5.1. Device/app confirmation of this new control is still pending.

## New control / Neuer Regler

Under **Configure**, enable **Allow battery controls (mode, SOC and output
power)**. The **Output power limit / Ausgangsleistungsgrenze** number sets watts
from 100 W up to the maximum explicitly returned by the cloud. A separate button
refreshes output-power settings.

**Deutsch:** In HACS / Marketplace **v0.5.2b4** auswählen, installieren und Home
Assistant neu starten. Unter **Konfigurieren** die **Batteriesteuerung** freigeben.
Der neue Regler **Ausgangsleistungsgrenze** verwendet den aktuell gemeldeten
Höchstwert. Ohne gültige Einstellungen bleibt er unverfügbar.

- Determine the phase layout explicitly before selecting action **84** or
  **1532**. Missing or failed phase discovery never falls back to a guessed
  single-phase command. Require a unique AC battery controller.
- Require explicit integer settings and limits; do not substitute a missing
  maximum with 2000 W or infer capability from a device model.
- Before each change, read fresh settings under a lock, check permission,
  controller identity and phase layout, and preserve active phase settings.
- Write once, then require matching total, phase values, bounds and layout by
  readback. Failed confirmation never repeats the write automatically.
- Read settings every 30 minutes while battery controls are enabled, with a
  manual refresh button and 30-second cooldown. Phase discovery, command reads
  and status polls use the existing shared account budget.
- Include only allowlisted output-power status, phase names, action, watts and
  maximum watts in diagnostics; no raw responses or controller addresses.

## Response compatibility and HA warning

- Accept short decimal integer strings in returned cutoff, heater and lighting
  fields, as the Android app does. Booleans, fractional values and arbitrary text
  remain invalid; HA service inputs are still validated independently.
- Decode JSON-text lighting data as well as object data. Canonicalize known
  numeric fields for readback while retaining unknown fields unchanged.
- Add separate heating/display and cutoff error reasons, target-selection flags
  and allowlisted response field types. Never export backend text, unknown keys,
  credentials or raw command responses. A successful later read clears the error.
- Register the station before child platforms and use its actual `via_device_id`
  for inverter sensors, removing the deprecated `via_device` argument reported
  by HA. This path is supported by both tested Core versions.

A second b3 station reported unreadable cutoff/display settings while live
telemetry worked. Its old diagnostics did not include the failure reason.
These format fixes are not confirmation of that station's root cause. If it
still fails after updating, refresh its settings and download new diagnostics;
the separate per-feature status now distinguishes parsing failures, command
failures, authentication, rate limits and connection errors. The existing
"Battery settings access" status describes mode/reserve settings only.

This control follows the app's output-power setting. It does **not** increase the
separately configured permitted maximum (configuration 515) or change the
grid-export limit. See [protocol and supported settings](https://github.com/Phil-0805/hoymiles-home-assistant/blob/v0.5.2b4/docs/output-power-settings.md).

## Test with the app

Compare the initial value and maximum with the app. Change one value, refresh the
app to check that exact setting, then restore the original value. Avoid
simultaneous app edits. Cloud readback alone is not proof of physical output
behaviour. Unsupported, incomplete or ambiguous settings remain unavailable.

**Deutsch:** Ausgangswert und Höchstwert mit der App vergleichen. Einen Wert
ändern, die App aktualisieren und danach den ursprünglichen Wert wiederherstellen.
Bei fehlender Bestätigung zuerst die App prüfen, bevor erneut geschrieben wird.

## Previous beta feedback and validation

The maintainer reports that both b3 charge/discharge cutoff controls work
correctly on their setup. This does not confirm other firmware/models. Those
controls and automatic five-minute battery temperatures remain included.
The incorrectly mapped b2 charge-limit entities remain removed; no old
automation is redirected automatically.

Local Core 2026.11.0 validation: **456 HA tests and 32 unit tests passed**,
including new cases for response formats, safe failure diagnostics, station
parent registration, phase/limit validation, exact transports, fresh
counterpart preservation, permission/unload/controller guards, full readback,
failed phase discovery and no repeat writes. Syntax, translation-structure and
diff checks passed. CI checks Core 2026.10.4 and 2026.11.0, HACS and Hassfest
before publication. No live account reads or real device writes were used to
develop the new output-power control.

Direct upgrades from stable also include the b1 translated battery-mode sensor
states. Update templates comparing old English text to keys such as
`self_consumption` and `time_of_use`; existing command-select values are unchanged.
