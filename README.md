# Hoymiles S-Miles Home for Home Assistant

Unofficial Home Assistant integration for **S-Miles Home** accounts. It reads
Hoymiles cloud data directly; Node-RED, MQTT and local inverter access are not
required. Developed and tested on an HMS-2000-4WB with HiBattery. A user has
also reported success with an 800 W microinverter, but that model and its
available sensors have not yet been independently verified here.

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

## Installation with HACS

1. Install HACS if you have not already, then open **HACS → Integrations**.
2. Open the HACS menu and choose **Custom repositories**.
3. Add `https://github.com/Phil-0805/hoymiles-home-assistant` with category
   **Integration**.
4. Install **Hoymiles S-Miles Home**. You do **not** need to enable beta versions.
5. Restart Home Assistant.
6. Under **Settings → Devices & services → Add integration**, search for
   **Hoymiles S-Miles Home** and enter your S-Miles Home email, password and
   numeric station ID (not the inverter serial number).

HACS can then offer subsequent releases. The integration is not in HACS's
default catalog; adding the custom repository remains necessary.

## Manual installation

Extract the release ZIP and copy `custom_components/hoymiles_home` into the
Home Assistant configuration directory as `custom_components/hoymiles_home`.
Restart Home Assistant, then add **Hoymiles S-Miles Home** under
**Settings → Devices & services**.

If you previously used the Node-RED `hoymiles-watch` node, its `sid` is the
station ID. Otherwise look for the numeric station ID in your S-Miles Home
installation details. The integration reports an error if that ID has no
devices for the signed-in account. Never post your password, login token, or
unredacted diagnostics in a public issue.

## What to expect

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

This project uses an unofficial cloud API and is not affiliated with Hoymiles.
The fast live endpoint follows the server-provided delay. Module values update
every five minutes. Do not enable another fast cloud poller for the same station
unless needed for diagnostics.

The diagnostic `ems`, `brs`, `chs` and `bhs` values are exposed raw because
Hoymiles does not publish a reliable meaning for every numeric state. On the
tested HMS-2000-4WB, `brs` carries the battery direction (`1` charging, `2`
discharging, `0` idle), while `power.bat` is an unsigned magnitude.

Battery controls use Hoymiles' unofficial asynchronous cloud setting API.
Changing the reserve SOC or mode sends a real command to the HiBattery. The
integration preserves the complete settings block for the selected mode and
reads it back after every write. Undocumented backend-only modes are not
offered as writable choices.
