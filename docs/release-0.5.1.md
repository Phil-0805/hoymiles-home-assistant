# v0.5.1 — security hardening

## Before updating / Vor dem Update

**Battery commands are now disabled by default, including on existing installations.** After updating and restarting Home Assistant, open **Settings → Devices & services → Hoymiles S-Miles Home → Configure** and enable **Allow battery controls** if you want to change the battery mode or reserve SOC. Existing automations using these controls require this opt-in. Telemetry and read-only settings refreshes continue without it. Existing entity identities and history are preserved.

**Batteriebefehle sind jetzt standardmäßig gesperrt, auch bei bestehenden Installationen.** Nach dem Update Home Assistant neu starten und unter **Einstellungen → Geräte & Dienste → Hoymiles S-Miles Home → Konfigurieren** die **Batteriesteuerung freigeben**, falls Modus oder Reserve-SOC aus Home Assistant geändert werden sollen. Auch bestehende Automationen mit diesen Steuerungen benötigen diese Freigabe. Messwerte und lesende Einstellungsabfragen funktionieren weiterhin. Kennungen und Verlauf bleiben erhalten.

## Fixed

- Apply JSON size, depth and object-shape limits to JSON embedded in command-status text fields as well as to outer HTTP responses. Malformed or deeply nested responses become controlled connection errors.
- Limit battery sensor attributes to allowlisted finite numeric settings, generated mode names and fixed status flags. Arbitrary cloud fields, raw errors and complete TOU plans are no longer exposed as sensor attributes. Internal write/readback snapshots remain complete.
- Require explicit battery-control permission before preflight and immediately before sending a command. Direct calls and unloading during preflight cannot bypass the restriction.
- Pin GitHub Actions to full commit SHAs, avoid persisted checkout credentials and track action updates with Dependabot. Protect release branches and published version tags.

## Validation and limitations

269 Home Assistant tests and 41 unit tests pass locally. GitHub also runs Tests, HACS and Hassfest before publication. All regression data is synthetic; no real account or device commands were used for this patch.

The maintainer explicitly approved v0.5.1 as a security patch. Existing unconfirmed hardware checks remain unconfirmed; the release decision does not claim additional device validation. The HiBattery 4020-X readings reported in [issue #9](https://github.com/Phil-0805/hoymiles-home-assistant/issues/9), cloud measurement-age limits and other model/firmware differences remain unresolved. Avoid simultaneous app changes during battery commands; readback cannot make app and HA writes atomic.

Update to v0.5.1 through HACS and restart Home Assistant. Earlier releases are superseded. Historical releases and Git commits are retained; no real credentials were found in the publication review.
