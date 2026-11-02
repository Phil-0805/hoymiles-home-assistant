# v0.5.0

## Changes

- Reauthenticate with a new password without recreating the integration.
- Fix battery-settings fallback errors. Switch between Self-Consumption and a supported, already configured TOU plan, preserving settings and checking the result by readback.
- Choose the station PV source (`auto`, `pv` or `pv2`) when troubleshooting a mismatch with the app.
- Add optional inverter temperature/frequency/voltage and battery/pack temperatures. Enable them under **Configure**; they are off by default.
- Improve cloud recovery, shared account request pacing, response handling and calculated energy counters.
- Preserve existing entity identities and group battery temperatures under the station device.

## Known limitations

- A HiBattery 4020-X user reports missing consumption readings and mostly zero PV power in Home Assistant. The cause remains unresolved in [issue #9](https://github.com/Phil-0805/hoymiles-home-assistant/issues/9).
- Compatibility with other models, firmware and account combinations is not fully verified. Some status codes and maximum-power settings remain undocumented.
- Cloud data can be delayed. Ordinary PV-input charts and battery temperatures do not always expose the physical measurement time.
- Avoid simultaneous app changes while sending a battery command from Home Assistant. Writes are not automatically repeated.

Update the existing integration and restart Home Assistant; do not delete and recreate it. See the [device troubleshooting guide](testing-0.5.0.de.md) for checks and reporting a problem.
