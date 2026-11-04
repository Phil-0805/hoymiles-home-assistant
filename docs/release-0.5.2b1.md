# v0.5.2b1 — Home Assistant 2026.11 beta

This is a prerelease for testing. Stable remains v0.5.1. No new battery commands,
cloud endpoints or faster polling are introduced.

## Before updating / Vor dem Update

**The battery mode sensor now uses translated enum states.** Its entity ID is
preserved, but automations/templates comparing its old English state must be
updated. For example, replace `Self-Consumption` with `self_consumption`, and
`Time of Use` with `time_of_use`. Command-select options retain their existing
English values. The UI displays the sensor state in your selected language.

**Der Batteriemodus-Sensor verwendet jetzt übersetzte Zustände.** Seine
Entitäts-ID bleibt erhalten. Automationen/Templates, die den bisherigen
englischen Sensorzustand vergleichen, müssen angepasst werden: zum Beispiel
`Self-Consumption` → `self_consumption` und `Time of Use` → `time_of_use`.
Die Auswahlwerte für Batteriebefehle bleiben unverändert auf Englisch.

| Previous sensor state | New sensor state |
| --- | --- |
| Self-Consumption | `self_consumption` |
| Economy | `economy` |
| Backup | `backup` |
| Off-Grid | `off_grid` |
| Self-Consumption + Max Power | `self_consumption_max_power` |
| Backup + Max Power | `backup_max_power` |
| Peak Shaving | `peak_shaving` |
| Time of Use | `time_of_use` |

Unknown/unsupported numeric modes remain unknown; these labels do not enable
additional controls. Existing entity IDs and stored energy data are preserved.

## Changes

- Test the integration against Home Assistant Core 2026.10.4 and 2026.11.0.
- Translate battery mode sensor states into German and English.
- Add the Energy / Solar & batteries integration category for Core 2026.11.
- Document direct installation from the official HACS default catalog, beta
  selection and the newer 4020-X user feedback in issue #9.
- Align sensor and diagnostic descriptions of the reported 4020-X relay mapping.
- Keep release approval records outside tracked files. Preserve the required
  `setup-tests` check while testing both HA versions.

## Install and test

Select v0.5.2b1 with beta/prerelease versions enabled in HACS or Marketplace, then restart Home
Assistant without deleting the integration. Check the translated battery mode
sensor, affected automations, PV readings and existing temperatures against the
app. Battery controls remain disabled by default unless already enabled in the
integration options. No real-device command is required to test the display.

## Known limitations

Maximum-power availability and some raw EMS/charging/health meanings remain
unresolved in [issue #9](https://github.com/Phil-0805/hoymiles-home-assistant/issues/9).
The 4020-X user's PV source, temperature, relay and command reports apply to that
setup, not every firmware/account combination. Cloud response age does not
always establish physical measurement age. Avoid simultaneous app/HA changes
while sending battery commands.

Automated tests use synthetic data and do not establish new hardware support.
Published Git history and existing releases remain unchanged.
