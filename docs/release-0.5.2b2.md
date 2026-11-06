# v0.5.2b2 — battery controls beta

This prerelease adds upper charge SOC, battery heating permission and
light/display controls. Stable remains v0.5.1. The new controls have automated
coverage with synthetic responses; actual app/device confirmation is still
pending. They are not a claim of support for every battery or firmware.

## Installation / Einrichtung

Enable prereleases in HACS / Marketplace, select **v0.5.2b2**, update the existing
integration and restart Home Assistant. Do not delete and recreate the station.

Under **Settings → Devices & services → Hoymiles S-Miles Home → Configure**:

- Enable **Allow battery controls** to change a supported upper charge SOC limit.
- Enable the separate **Allow device controls (heating, light and display; beta)**
  option for the new heater, light and display entities. This option is off by
  default, including after upgrading from b1.

**Deutsch:** In HACS / Marketplace Vorabversionen aktivieren, **v0.5.2b2**
installieren und Home Assistant neu starten. Unter **Konfigurieren** die
**Batteriesteuerung** für die obere SOC-Ladegrenze und die separate
**Gerätesteuerung** für Heizung, Licht und Display freigeben. Die neue
Gerätesteuerung ist standardmäßig aus. Anlage und Integration nicht löschen.

## New controls

- Upper charge SOC sensor and number in the supported Self-Consumption settings
  path. Only an explicitly returned upper threshold enables the control. It
  preserves the freshly read lower threshold; TOU plan thresholds are unchanged.
- **Allow battery heating** switch. This permits automatic warming by the device;
  it neither forces heating nor reports whether the heater is physically active.
- RGB colour, brightness and on/off for a supported battery indicator strip.
- Display brightness in percent and separate strip/display off delays in seconds.
- A dedicated button to refresh heating and light/display settings.
- German and English labels and updated user documentation.

When device controls are enabled, their settings are read every 30 minutes.
Manual refreshes have a 30-second cooldown. All requests share the existing
account budget. Light/display controls require a unique supported controller;
missing or unsupported capabilities remain unavailable.

Each change reads fresh settings, preserves other settings, sends a single write
and checks the complete result by readback. Failed confirmation does not cause
an automatic repeat write. Avoid simultaneous changes in the app. If readback
fails, inspect the app before retrying: the device may have received the write.

## Validation and limitations

Local validation on Home Assistant Core 2026.11.0: **369 HA tests and 32 unit
tests passed**, plus syntax, translation-structure and whitespace checks. CI also
tests Core 2026.10.4, HACS and Hassfest before publication. No real-device command
was sent during development.

Named app lighting effects (such as Rainbow and Aurora), battery-level lighting
modes, EPS/backup, touch lock, new output/export limits and firmware updates are
not added in this beta. Heating permission may remain on without physical warming
because the device decides when heating is needed. Hardware and firmware
differences remain unverified. See [device settings](https://github.com/Phil-0805/hoymiles-home-assistant/blob/v0.5.2b2/docs/device-settings.md)
and [charge-limit testing](https://github.com/Phil-0805/hoymiles-home-assistant/blob/v0.5.2b2/docs/battery-charge-limit.md).

When upgrading directly from stable, the b1 battery-mode sensor change also
applies: automations comparing old English state text must use stable keys such
as `self_consumption` and `time_of_use`. Existing entity IDs and stored history
are preserved; command-select values remain unchanged. See the
[b1 migration notes](https://github.com/Phil-0805/hoymiles-home-assistant/releases/tag/v0.5.2b1).
