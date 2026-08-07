# Hoymiles S-Miles Home for Home Assistant

Native Home Assistant custom integration for consumer S-Miles Home accounts,
tested against an HMS-2000-4WB installation.

## Features

- Three-second live PV, load, grid and battery power
- Persistent daily home-consumption energy calculated from the live load
- Correct WB battery charge/discharge direction using the live relay state
- Separate positive battery charge and discharge power sensors
- Persistent daily battery charge and discharge energy counters
- Writable reserve SOC and battery mode controls with read-back verification
- Read-only battery setting diagnostics
- Battery state of charge and raw operating flags
- PV1–PV4 power, voltage and current from five-minute module charts
- Station connectivity
- Daily, monthly, yearly and total energy when supplied by the station endpoint
- UI setup through Home Assistant

## Installation with HACS

1. Open **HACS → Integrations**.
2. Open the menu and choose **Custom repositories**.
3. Add `https://github.com/Phil-0805/hoymiles-home-assistant` with category
   **Integration**.
4. Install **Hoymiles S-Miles Home** and restart Home Assistant.
5. Add the integration under **Settings → Devices & services**.

Future versions can then be installed directly through HACS.

## Manual installation

Extract the release ZIP and copy `custom_components/hoymiles_home` into the
Home Assistant configuration directory as `custom_components/hoymiles_home`.
Restart Home Assistant, then add **Hoymiles S-Miles Home** under
**Settings → Devices & services**.

The setup form needs the S-Miles Home email, password and numeric station ID.
Credentials are stored only in the local Home Assistant config entry and are
never written to this repository.

## Notes

This project uses an unofficial cloud API and is not affiliated with Hoymiles.
The fast live endpoint follows the server-provided delay. Module values update
every five minutes. Do not enable another fast cloud poller for the same station
unless needed for diagnostics.

The diagnostic `ems`, `brs`, `chs` and `bhs` values are exposed raw because
Hoymiles does not publish a reliable meaning for every numeric state. On the
tested HMS-2000-4WB, `brs` carries the battery direction (`1` charging, `2`
discharging, `0` idle), while `power.bat` is an unsigned magnitude.

Battery controls use Hoymiles' unofficial asynchronous cloud setting API.
Changing the reserve SOC or mode sends a real command to the inverter. The
integration preserves the complete settings block for the selected mode and
reads it back after every write. Undocumented backend-only modes are not
offered as writable choices.
