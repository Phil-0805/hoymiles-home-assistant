# v0.6.0 — better login compatibility and more control

**v0.6.0 brings the improvements tested throughout the v0.5.2 beta series and
v0.6.0b1 to the stable channel.** The larger scope is why this release is named
0.6.0 rather than 0.5.2. MQTT research moves to v0.7.0.

## Login fixes, now on stable

The integration follows Hoymiles' account-selected authentication server and
login protocol. It supports the tightly restricted authentication redirects
used by the official clients, including the observed `times=1` parameter.
No alternative server or weaker protocol is tried after a rejected login.

Issue #16 testers confirmed successful login and readings matching the official
app/cloud on their setups. This resolves the account-routing incompatibility
found during troubleshooting; it does not guarantee against future cloud changes.

If the mobile API supplies no live-server address, the integration can use the
manufacturer's documented-in-client web route. Missing addresses, authentication
failures and stale live data remain distinct diagnostic conditions.

## Battery, light and display controls

- **Separate charge and discharge cutoffs**, distinct from reserve SOC and
  work-mode SOC settings. Discharge: 10–70%; charge: 50–100%; at least ten
  percentage points between them. Both values are read before a change, the
  counterpart is preserved, and both are checked afterwards.
- **Automatic battery temperature readings**, including existing entries that
  had the former temperature option disabled. The five-minute interval remains.
- **Automatic-heating permission**, LED on/off, colour and brightness, display
  brightness, and separate strip/display off delays.
- **Off-delay presets**, including **Never**. Existing seconds entities retain
  their IDs and become unavailable while Never is selected, rather than showing
  the protocol sentinel as seconds. Custom numeric delays remain supported.
- **Output-power control in watts** when the cloud supplies supported settings
  and explicit limits. Existing stored values above a reported write limit can
  be displayed, but new writes must obey freshly read limits. This does not
  change the separately permitted maximum or the grid-export limit.

Controls require the corresponding battery/device permission in the integration
options. Changes use fresh reads, preserve related settings, write once and
verify by readback. Missing confirmation does not trigger an automatic resend.
Avoid simultaneous changes through the app and Home Assistant.

## Recovery, diagnostics and maintenance

- Transient settings-read failures receive at most two additional attempts,
  after one minute and then three minutes from the preceding failure. Successful
  features remain available and are not reread just because another failed.
  The normal 30-minute settings schedule applies after the retry limit.
- Authentication errors, rate limits, rejected redirects, HTTP 4xx and invalid
  settings do not receive accelerated retries. Existing account pacing,
  server pauses and command-status polling are preserved.
- Fixed diagnostic labels identify the failing stage and reason without logging
  passwords, tokens, identifiers, request URLs or raw cloud responses. Recovery
  of live data is reported once per failure episode.
- Improved response parsing for the integer strings and JSON-text settings used
  by the official clients; tighter device-parent registration and targeted
  entity cleanup; consolidated settings, permission and logging helpers.
- HACS release ZIP includes LICENSE. Its download count measures release-asset
  downloads, not active users.

## Upgrade notes — please read

Install **v0.6.0** and restart Home Assistant. Keep your existing integration;
you do not need to delete it or change your Hoymiles password. Beta testers can
move directly to this stable version and disable prereleases if desired.

1. **Battery-mode sensor states are translated enum keys.** Templates comparing
   `Self-Consumption` or `Time of Use` must use `self_consumption` or
   `time_of_use`. Entity IDs are retained; command-select values are unchanged.
   The complete mapping is in [the migration notes](https://github.com/Phil-0805/hoymiles-home-assistant/blob/v0.6.0/docs/release-0.5.2b1.md).
2. **The incorrect b2 charge-limit number and its sensor are removed.** Update
   references deliberately to the separate cutoff controls; reserve SOC remains
   a different setting.
3. **Maximum power setting (raw) is removed.** Only the obsolete diagnostic
   sensor owned by the configuration entry is removed, including renamed or
   disabled instances. Update dashboards/automations referencing it. The
   output-power control remains; no automatic alias is created.
4. Battery temperatures are now automatic. Additional inverter telemetry stays
   optional. Battery/device control permissions remain separate.

**Deutsch:** v0.6.0 installieren und HA neu starten; die vorhandene Integration
behalten. Templates für den Batteriemodus auf Kennungen wie `self_consumption`
umstellen. Der falsch zugeordnete b2-Ladegrenzen-Regler samt Sensor sowie
**Maximale Leistungseinstellung (Rohwert)** entfallen. Verweise in Automationen
und Dashboards bei Bedarf manuell anpassen. Die getrennten Schlussstufen,
Reserve-SOC und der Ausgangsleistungs-Regler bleiben eigenständige Einstellungen.
Für bisherige Betatester ist kein Neueinrichten erforderlich.

## Tested scope and remaining limitations

The maintainer reports v0.6.0b1 has run successfully and approves this stable
release. Testers confirmed login/readings; selected cutoff and light/display
controls, including Never timers, were confirmed on the reported installations.
These observations do not certify every device, firmware or control.

Output-power display/readback is not proof of physical output behavior across
hardware. Heating permission does not force heating or report actual heater
activity. Named light effects are not exposed. Missing settings stay unavailable;
limits and ambiguous device targets are not guessed.

One issue #16 reporter separately observed stale readings in both the official
app and Home Assistant. Its cause is unresolved. The message “Live URI expired”
can also indicate unusable live data after the address is refreshed; it does not
necessarily mean expired credentials. Cloud response age does not always prove
physical measurement age. Locally calculated daily energy can have gaps during
outages and is not a billing meter.

Local validation: **740 HA tests and 35 unit tests**, syntax, translation-key
parity, documentation links and whitespace checks. CI tests HA **2026.10.4 and
2026.11.0**, HACS and Hassfest before publication. Automated tests use synthetic
data; they do not establish hardware compatibility. No real account or device
was accessed by the agent for release preparation.

## Thank you

Special thanks to **@gillesBdl** for his patience, repeated beta testing and
detailed troubleshooting feedback during the login investigation. Thanks also
to **@ElchCarlo**, the other issue reporters and everyone who compared readings
and tested controls throughout the betas.

[English README](https://github.com/Phil-0805/hoymiles-home-assistant/blob/v0.6.0/README.md) · [Deutsche README](https://github.com/Phil-0805/hoymiles-home-assistant/blob/v0.6.0/README.de.md) ·
[Device settings](https://github.com/Phil-0805/hoymiles-home-assistant/blob/v0.6.0/docs/device-settings.md) · [API timing](https://github.com/Phil-0805/hoymiles-home-assistant/blob/v0.6.0/docs/api-request-timing.md) ·
[MQTT roadmap for v0.7.0](https://github.com/Phil-0805/hoymiles-home-assistant/blob/v0.6.0/docs/roadmap-0.7.md)
