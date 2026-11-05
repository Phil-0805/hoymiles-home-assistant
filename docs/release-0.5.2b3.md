# v0.5.2b3 — separate battery cutoffs

This is a prerelease for testing. Stable remains v0.5.1. The new cutoff protocol
is traced to the Android app, with synthetic regression tests; actual device/app
confirmation is still pending.

## Before updating / Vor dem Update

**The incorrectly mapped b2 charge-limit number and its matching sensor are
removed.** Their action-83 value belongs to work-mode settings and did not change
the separate app cutoffs in the maintainer's test. Old automations must be
deliberately updated to the new entities; they are not automatically redirected.
Reserve SOC remains a separate existing setting.

**Deutsch:** Der falsch zugeordnete Ladegrenzen-Regler aus b2 und sein Sensor
werden beim Update entfernt, auch wenn sie deaktiviert oder umbenannt wurden.
Automationen auf diese Entitäten müssen bewusst auf die neuen Regler angepasst
werden. Reserve-SOC und bestehende Temperatur-Entitäten bleiben erhalten.

## New and changed

- Add **Charge cutoff SOC / Ladeschlussstufe** and **Discharge cutoff SOC /
  Entladeschlussstufe** using Android action **1537**, device addressing and the
  distinct `sl`/`sh` fields. This does not reuse work-mode `soc_l`/`soc_h`.
- Follow the inspected app ranges: discharge 10–70%, charge 50–100%, with at
  least 10 percentage points between them. Require both values explicitly;
  missing values are never replaced with defaults.
- Enable the new entities with **Allow battery controls** under Configure.
  Each change reads both thresholds freshly, preserves the counterpart, writes
  once and requires matching readback of both. Invalid or ambiguous controller
  data, permission revocation and unload prevent a write.
- Read cutoff settings every 30 minutes while battery controls are enabled,
  using the shared account request budget. Add a manual refresh button with a
  30-second cooldown. Failed confirmation never automatically repeats a write.
- Make **battery temperatures automatic**, including existing installations
  where the previous option was off. Remove the temperature toggle. Background
  reads remain at most every five minutes; missing values remain unavailable.
- Add allowlisted cutoff diagnostics without controller addresses or raw command
  responses. Retain the upper work-mode SOC only as a clearly named raw
  diagnostic value.
- Keep the b2 heating, light, colour, display brightness and off-delay controls.
  No new output-power entity or named light effect is introduced in b3.

## Install and test

Enable prereleases in HACS / Marketplace, select **v0.5.2b3**, update and restart
Home Assistant without deleting the integration. Under Configure, enable battery
controls if you want to test the separate cutoffs. Compare both initial values
with the app, change one at a time, refresh the app and restore the original
values. Avoid simultaneous app edits. Cloud readback is not proof of physical
charge/discharge behaviour.

**Deutsch:** b3 in HACS installieren und Home Assistant neu starten. Für die
Schlussstufen die Batteriesteuerung freigeben. Beide Ausgangswerte mit der App
vergleichen, jeweils nur einen Wert ändern und danach zurückstellen. Die
Batterietemperaturen benötigen keine Freigabe mehr. Die Gerätesteuerung für
Heizung/Licht/Display bleibt eine eigene Option.

## Evidence and limitations

The inspected Android package identifies itself as V2.13.0 (2026101400) and was
obtained from an APK mirror; publisher signature authenticity was not independently
established. The app was statically analyzed and never installed or run. No live
account requests or real device writes were used in development. See the exact
hashes, method chain, endpoints and addressing in
[Android protocol evidence](https://github.com/Phil-0805/hoymiles-home-assistant/blob/v0.5.2b3/docs/android-app-protocol.md).

The app's output-power commands were also identified, but phase capabilities,
permissions and device readback still need checking before a new control is
offered. Other firmware/models and multiple battery controllers remain unverified.

Local validation on Core 2026.11.0: **394 HA tests and 32 unit tests passed**,
including removal/migration, correct cutoff transport, fresh counterpart
preservation, permission guards, full readback, values and temperature activation.
Syntax, translation structure and diff checks passed. GitHub checks Core
2026.10.4 and 2026.11.0, HACS and Hassfest before publication.

Upgrading directly from stable also includes the b1 battery-mode sensor enum
change. Adjust templates comparing old English states to keys such as
`self_consumption` and `time_of_use`; see the b1 migration notes.
