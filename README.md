# Hoymiles S-Miles Home for Home Assistant

[![HACS Default](https://img.shields.io/badge/Marketplace%20%7C%20HACS-Default-orange)](https://github.com/hacs/default/blob/master/integration)
[![Release](https://img.shields.io/github/v/release/Phil-0805/hoymiles-home-assistant)](https://github.com/Phil-0805/hoymiles-home-assistant/releases/latest)
[![Last commit](https://img.shields.io/github/last-commit/Phil-0805/hoymiles-home-assistant/main?label=last%20commit%20%28main%29)](https://github.com/Phil-0805/hoymiles-home-assistant/commits/main)
[![Tests](https://img.shields.io/github/actions/workflow/status/Phil-0805/hoymiles-home-assistant/tests.yml?branch=main&label=tests%20%28main%29)](https://github.com/Phil-0805/hoymiles-home-assistant/actions/workflows/tests.yml)
[![HA tested](https://img.shields.io/badge/HA%20tested-2026.10.4%20%7C%202026.11.0-blue)](https://github.com/Phil-0805/hoymiles-home-assistant/actions/workflows/tests.yml)
[![Release downloads](https://img.shields.io/github/downloads/Phil-0805/hoymiles-home-assistant/total?label=release%20downloads)](https://github.com/Phil-0805/hoymiles-home-assistant/releases)
[![License MIT](https://img.shields.io/github/license/Phil-0805/hoymiles-home-assistant)](LICENSE)

**English** | [Deutsch](README.de.md)

Connect your **S-Miles Home** account to Home Assistant to monitor your solar
installation and supported battery settings through the Hoymiles cloud.
No Node-RED or MQTT broker is required. This is a community integration,
unaffiliated with Hoymiles, and officially listed in the HACS default catalog.

**v0.6.0** brings account-aware login, separate battery cutoffs and light/display
controls to the stable channel. It includes the fixes tested throughout the
v0.5.2 betas and v0.6.0b1. Existing installations can update without starting over.

[What changed in v0.6.0](docs/release-0.6.0.md) · [Upgrade notes](#updating-to-060)

[Installation](#installation) · [Features](#features) · [Controls](#controls) ·
[Beta testing](#testing-beta-versions) · [Troubleshooting](#troubleshooting)

## Installation

1. Open HACS / Marketplace and search for **Hoymiles S-Miles Home**.
   It is in the default catalog; adding a custom repository is unnecessary.
2. Install the integration and restart Home Assistant.
3. Open **Settings → Devices & services → Add integration** and choose
   **Hoymiles S-Miles Home**.
4. Enter your S-Miles Home email and password, then select your plant.
   For another plant, add the integration again.

If plant discovery is unavailable, enter the numeric station ID manually.
See [Finding your station ID](#finding-your-station-id). Updates do not require
recreating an existing integration or its entities.

## Features

Availability depends on the device, firmware and cloud response.

| Area | Available features |
| --- | --- |
| Live data | PV, grid, home load and battery power; connectivity and battery SOC |
| Energy | Station energy totals where supplied; locally calculated daily battery charge/discharge and home-consumption energy |
| PV modules | Power, voltage and current from five-minute charts; selectable PV source |
| Battery | Mode, reserve SOC and read-only status diagnostics |
| Battery controls | Automatic temperature readings and separate charge/discharge cutoff settings |
| Device settings | Automatic-heating permission, LED colour/brightness, display brightness and separate off delays |
| Output power | Watt control when the cloud reports complete settings, limits and phase information; device validation remains open |
| Diagnostics | Login/connection error stages and reasons, plus attempted recovery when the mobile API supplies no live-server address |

Live polling follows Hoymiles' requested interval, normally around three seconds.
Module charts and battery temperatures refresh about every five minutes.
Settings normally refresh every 30 minutes and have manual refresh buttons.
Transient settings-read failures receive at most two additional attempts, after
one and then three minutes. Authentication errors, rate limits and invalid
settings keep their normal handling. Cloud availability can affect all readings.

## Controls

Under **Settings → Devices & services → Hoymiles S-Miles Home → Configure**:

| Option | Enables |
| --- | --- |
| **Allow battery controls** | Battery mode, reserve SOC, separate charge/discharge cutoffs and supported output-power settings |
| **Allow device controls** | Heating permission, LED and display settings |
| **Additional inverter telemetry (beta)** | Optional inverter temperature, frequency and AC voltage where available |

Write controls are disabled by default. Changes read current settings first,
preserve related values and verify the result by readback. Check the app after
a change and avoid simultaneous app/HA edits.

- **Reserve SOC and discharge cutoff are separate settings.** See
  [battery cutoff details](docs/battery-charge-limit.md).
- **Heating permission** allows automatic heating; it does not force heating or
  report heater activity. Named light effects are not exposed. See
  [device settings](docs/device-settings.md).
- **Output power** requires explicit cloud limits. An unavailable control does
  not establish a device fault. This control does not raise the separately
  permitted maximum or change the grid-export limit. See
  [output-power details](docs/output-power-settings.md).

## Device compatibility

| Setup | Evidence so far |
| --- | --- |
| HMS-2000-4WB with HiBattery | Maintainer setup; model/PV readings and selected battery/device controls tested |
| HMS-800-2WB | Model and PV readings confirmed; battery/device settings can differ between installations |
| HiBattery 4020-X with one expansion battery | User confirmed selected PV source, temperatures, relay direction and battery commands in v0.5.1; [issue #9](https://github.com/Phil-0805/hoymiles-home-assistant/issues/9) |

These observations do not establish support for every setting or firmware.
The tests badge tracks `main`; the HA badge names versions covered by the current
test matrix, not a minimum HA version. Models use explicit device metadata;
otherwise the name remains generic. Missing values remain unavailable. Battery
entities only provide useful data when the installation has supported storage.
Daily calculated energy can have gaps during outages and is not a billing meter.

## Updating to 0.6.0

Read the selected release's notes, install it and restart Home Assistant.
Keep existing config entries and entity identities.

- Battery mode sensor states use keys such as `self_consumption` and
  `time_of_use`, displayed in your language. Update templates that compare
  against the previous English sensor text. Command select values remain unchanged.
- The incorrectly mapped b2 charge-limit number and its sensor are removed.
  Automations using them need deliberate changes to use the separate app cutoffs.
- Battery temperatures no longer require their previous opt-in. Additional
  inverter telemetry remains optional.
- The obsolete **Maximum power setting (raw)** sensor is removed. Update any
  dashboards or automations referencing it; the output-power control remains.

## Testing beta versions

Stable is recommended for everyday use; betas remain available for volunteers.
Read the selected version's [release notes](https://github.com/Phil-0805/hoymiles-home-assistant/releases)
and create a backup before testing.

- **HA 2026.11+ / Marketplace:** Open **Settings → Devices & services → Marketplace**
  and the device page for this repository. Enable the disabled **Pre-release**
  switch entity, then turn it on. Install the offered beta, or use **Install
  another version** on the repository page to select a beta such as `0.6.0b1`.
- **HA 2026.10 or older / HACS:** Open this repository, enable prereleases and use
  **Redownload** to choose the beta. Labels vary with the HACS version.

Restart Home Assistant afterwards; keep the existing integration and entities.
Compare readings with the app using the [device test guide](docs/testing-0.5.0.de.md).
Report the beta/HA version, device model and observed problem in an issue,
without credentials, tokens, serial numbers or private screenshots. Battery
command tests are optional and require enabling battery controls.

To leave beta testing, disable prereleases. For an immediate rollback, restore
your pre-beta backup; see the [Marketplace version guidance](https://www.home-assistant.io/integrations/marketplace/#installing-another-version).
Automations are not automatically adapted when sensor states change.

## Troubleshooting

Check the installed integration version, HA version and device/firmware model.
For login or connection failures, open **Settings → System → Logs →
Home Assistant Core** and look for `hoymiles_home.cloud_logging`.
Warnings identify `stage`, `reason` and, where relevant, numeric status codes.
Debug logging is not required. See [connection test instructions](docs/release-0.6.0.md).
A missing live-server address and a failed login can have different causes.
If readings stop, compare with the official app. Stale values in both may indicate
a shared device/cloud issue; this alone does not establish its cause.
A settings refresh may take several minutes after a transient startup failure.

For login reports, name the exact app tested: **S-Miles Home** and **S-Miles
Installer** are different clients. A successful Installer/website login does
not establish access through the Home API. The v0.6.1b11 beta includes initial account routing, improved TOU mode readback,
activation of supported existing basic plans and restored bounded live-data recovery after the b5 regression, and station setup while a live server address is missing; see [its test instructions](docs/release-0.6.1b11.md)
and [the evidence and remaining limits](docs/login-routing-0.6.1.md).
B10 also corrects Home DTU nesting and chart-time acceptance, retains confirmed
output settings overnight, and removes the separate last-temperature entity.
B11 corrects chart availability between normal polls while preserving original
sample times and expiring non-advancing data.

Download diagnostics for the affected integration under **Devices & services**.
Report the version, affected setting and matching app observation in an
[issue](https://github.com/Phil-0805/hoymiles-home-assistant/issues).
Do not publish credentials, tokens, serial numbers or unredacted screenshots.

## Manual installation

If the release includes **hoymiles_home.zip**, extract its contents directly into
`<config>/custom_components/hoymiles_home/`; `manifest.json` must be directly in
that folder. For a GitHub **Source code (zip)** archive or older releases,
copy its `custom_components/hoymiles_home` folder into `<config>/custom_components/`.
Restart Home Assistant and add the integration under **Devices & services**.

## Finding your station ID

Setup requires the numeric **station ID** (`sid`) of your plant, not the
inverter serial number or an individual device's numeric `id`.

1. Sign in to [S-Miles Cloud](https://global.hoymiles.com) in a desktop browser.
2. Open **Plant** (**Anlage** in German) and select your installation.
3. On the plant detail page, check the address bar. The maintainer has confirmed
   that the station ID can be obtained from the selected plant's URL:
   `https://global.hoymiles.com/website/plant/detail/<station-id>`.
   Copy the numeric station ID into the Home Assistant setup form.
4. For orientation, the portal also displays an ID directly below the plant
   name in the top-left corner. The maintainer's German interface labels it
   **Mikro-Energiespeicher ID**. A user in [issue #2](https://github.com/Phil-0805/hoymiles-home-assistant/issues/2)
   reports **PV microinverter ID** instead. Do not assume that every field
   with either label is the API station ID; use the confirmed URL value.

If you already use the Node-RED `hoymiles-watch` node successfully for this
plant, its configured `sid` is the station ID. Node-RED is not required.

Setup checks that the signed-in account can retrieve a non-empty device tree
for the entered ID. After setup, check that the devices and measurements match
your plant. If the URL differs or you cannot identify a numeric station ID, ask
in issue #2 rather than entering a serial number. Never post passwords, login
tokens or unredacted diagnostics in a public issue.

## Privacy

Login data is sent to Hoymiles over HTTPS. The password is stored in Home
Assistant's local config entry for reconnects; protect the host and backups.
Account tokens are restricted to HTTPS Hoymiles hosts. Login permits one redirect
to the same auth path on explicitly allowed HTTPS API hosts, without forwarding
a previous token. Other API redirects remain blocked.
The integration sends no measurements or credentials to this project or an
additional analytics service. New cloud diagnostic logs use fixed labels and
structural information, without raw responses, identifiers or credentials.

The cloud API is undocumented and can change. This project is not independently
audited.

[MIT license](LICENSE) · [Release notes](https://github.com/Phil-0805/hoymiles-home-assistant/releases) ·
[Device test plan](docs/testing-0.5.0.de.md) · [MQTT investigation for v0.7.0](docs/roadmap-0.7.md)

### Installer account profile (experimental)

Beta **v0.6.1b3** adds an explicitly selected experimental **S-Miles Installer**
account type at setup and reauthentication. It covers live readings, energy
totals and basic device identity/model only. Home controls, temperatures, charts
and additional telemetry are not enabled for this profile. See
[the protocol findings and test scope](docs/installer-app-protocol.md).

### Enduser account profile (experimental)

Beta **v0.6.1b12** adds **S-Miles Enduser (experimental, read only)** as
a separate account type. It supports station monitoring for the verified PV
and storage/hybrid response formats, with generation totals where the cloud
supplies the standard fields. Home controls, module charts and inverter detail
telemetry are not enabled. Device testing is pending; this profile is experimental. See [protocol, scope and testing](docs/enduser-app-protocol.md).

B13 additionally accepts app-compatible Enduser setup response representations
and provides specific validation reasons; see [the b13 test instructions](docs/release-0.6.1b13.md).
