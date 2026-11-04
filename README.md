# Hoymiles S-Miles Home for Home Assistant

**English** | [Deutsch](README.de.md)

Unofficial Home Assistant integration for **S-Miles Home** accounts. It reads
Hoymiles cloud data directly; Node-RED, MQTT and local inverter access are not
required. Developed and tested on an HMS-2000-4WB with HiBattery. During the
0.4.2 beta test on 28 October 2026, the maintainer verified the correct model
labels and PV readings on HMS-2000-4WB and HMS-800-2WB installations. This does
not confirm every function or every firmware/account combination.

For a **HiBattery 4020-X with one expansion battery**, a user confirms PV
readings after choosing the matching PV source, battery temperatures, relay
direction and battery commands in v0.5.1. These observations apply to that
setup. Maximum-power settings remain unavailable on its current settings path;
some raw status codes are undocumented. See
[issue #9](https://github.com/Phil-0805/hoymiles-home-assistant/issues/9).

## Select your plant during setup

From version 0.4.0, sign in with your S-Miles Home account, then select a plant
by name and numeric station ID. To add another plant, add the integration again.
Existing configured stations and their identifiers are preserved.

You can also type a numeric station ID into the dropdown. If discovery is
unavailable or returns no plants, setup offers manual ID entry. Before saving,
the ID is checked against the account's device tree.

The maintainer verified plant selection and duplicate detection with his account
on 26 October 2026; existing history and measurements were preserved. Other
accounts and device models may behave differently with this unofficial API.
For manual setup, see [Finding your station ID](#finding-your-station-id).

## Features

- Live PV, load, grid and battery power when the station supplies these values
- Persistent daily home-consumption energy calculated from the live load
- Correct WB battery charge/discharge direction using the live relay state
- Separate positive battery charge and discharge power sensors
- Persistent daily battery charge and discharge energy counters
- Writable reserve SOC and battery mode controls with read-back verification
- Read-only battery setting diagnostics
- Battery state of charge and raw operating flags
- Per-module power, voltage and current from five-minute charts, where available
- Station connectivity
- Daily, monthly, yearly and total energy when supplied by the station endpoint
- UI setup through Home Assistant

## Battery controls

Battery commands are disabled by default, including when upgrading an existing installation. Under **Settings → Devices & services → Hoymiles S-Miles Home → Configure**, enable **Allow battery controls** to use the mode and reserve-SOC entities. Turn it off again for read-only operation. Existing entity identities and history are preserved; telemetry and settings refreshes continue while controls are disabled. Avoid simultaneous changes in the S-Miles Home app.

Use v0.5.1 or newer for the current security fixes. Earlier versions are superseded. After updating, restart Home Assistant and explicitly enable battery controls if needed. This also applies to existing automations that change the battery mode or reserve SOC.

## Battery mode display (v0.5.2 beta)

The battery mode sensor uses translated states with stable keys such as
`self_consumption` and `time_of_use`. Its entity ID is preserved. When installing this beta, adjust
automations/templates that compare this sensor to the old English text (for example `Self-Consumption`). Battery
command select options keep their existing English values.

## Installation with HACS / Marketplace

**Hoymiles S-Miles Home is officially listed in the [HACS default catalog](https://github.com/hacs/default/blob/master/integration).** You can install it directly from HACS without adding a custom repository. This remains an unofficial Hoymiles integration.

1. On HA 2026.11+, open **Settings → Marketplace**. On HA 2026.10 or older,
   install HACS if needed and open HACS.
2. Search for **Hoymiles S-Miles Home** and install it. Beta versions are not required.
3. Restart Home Assistant.
4. Under **Settings → Devices & services → Add integration**, search for
   **Hoymiles S-Miles Home**, enter your S-Miles Home email and password, then
   select your plant. For manual setup, see
   [Finding your station ID](#finding-your-station-id).

Subsequent releases are available through HACS. Existing installations added as
a custom repository can continue using the integration without recreating their
Home Assistant config entries.

## Testing beta versions

Stable is recommended for everyday use; betas remain available for volunteers.
Read the selected version's [release notes](https://github.com/Phil-0805/hoymiles-home-assistant/releases)
and create a backup before testing.

- **HA 2026.11+ / Marketplace:** Open **Settings → Devices & services → Marketplace**
  and the device page for this repository. Enable the disabled **Pre-release**
  switch entity, then turn it on. Install the offered beta, or use **Install
  another version** on the repository page to select a beta such as `0.5.2b1`.
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

## Manual installation

Extract the release ZIP and copy `custom_components/hoymiles_home` into the
Home Assistant configuration directory as `custom_components/hoymiles_home`.
Restart Home Assistant, then add **Hoymiles S-Miles Home** under
**Settings → Devices & services**.

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

## What to expect

- From version 0.4.2, model discovery reads `model_no` and tries optional
  read-only web device metadata when the Home tree lacks a model. Some accounts
  may not have access. Download integration diagnostics under **Settings →
  Devices & services** if the model remains generic; the `inverters` section
  reports the result without raw account/device data.
- Inverter model names are taken from explicit HMS model numbers in device
  metadata; otherwise the device is labelled "Hoymiles microinverter". Known
  models use their physical PV input count. Without a model, the integration
  retains its four-input chart probing; this does not mean four inputs or a
  2000 W rating were detected. Existing sensor and device identifiers are retained.
- Live data follows the interval supplied by Hoymiles, normally about three
  seconds. Module chart values typically refresh every five minutes. This is
  cloud polling, not a guarantee of true inverter-side real time.
- Battery entities and controls are useful only with a supported battery.
  A microinverter without storage will not gain battery measurements.
- Battery charge/discharge and home-consumption daily energy are calculated
  locally from power readings. Short outages can leave gaps; these are not
  revenue-grade meters.
- Reserve SOC is the configured minimum charge, not the current state of
  charge. Changes are sent to the device through Hoymiles and can take several
  seconds to appear. Check the S-Miles Home app after changing a control.

## Privacy and security

The integration sends account login data to Hoymiles over HTTPS, then uses an
account token to request data from Hoymiles endpoints. It does not send your
measurements or credentials to this GitHub project or to an additional analytics
service. The password is retained in Home Assistant's local config entry so it
can reconnect; protect your Home Assistant host and backups. This is **not**
end-to-end private or independently audited: Hoymiles already handles your
plant data, and its undocumented API can change. The token is only sent to
HTTPS Hoymiles hosts; redirects and unexpected live-data hosts are rejected.
Do not expose Home Assistant publicly without its normal access controls.

## Notes

- This integration uses an unofficial cloud API and is not affiliated with Hoymiles.
- Additional inverter readings and battery temperatures can be enabled under
  **Configure**. They are off by default and may initially be unavailable.
- Changing battery mode or reserve SOC sends a real control command. Avoid
  simultaneous changes in the app and check the result there.

See the [release notes and known limitations](docs/release-0.5.1.md) and
[device test plan](docs/testing-0.5.0.de.md) for details.
