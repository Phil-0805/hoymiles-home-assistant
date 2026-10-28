# v0.4.1 — inverter model display fix

- Fixes #6: microinverters are no longer unconditionally displayed as HMS-2000-4WB. An explicit HMS model number from device metadata is used when available; otherwise the device is labelled "Hoymiles microinverter".
- Sensor creation and module chart polling use the physical PV input count from the identified model. Unknown models retain the previous four-input chart probing for compatibility.
- Existing device identifiers and per-port sensor unique IDs are preserved. Existing surplus PV3/PV4 registry entries are not deleted automatically. This change does not rescale measurements or alter battery commands.
- Documents community-reported operation with a HiBattery 4020-X plus one additional storage unit (sensors, Self Consumption, SOC settings and diagnostics). This is not independent certification of all functions.

## Upgrade

Update through HACS and restart Home Assistant. Keep the existing integration configured; no removal or reconfiguration is required.

## Validation and limitations

62 automated tests pass (26 unittest tests and 36 Home Assistant pytest cases), including model display, input counts, stable identifiers and mixed-inverter polling. HACS and Hassfest validation are also run before publishing.

The hard-coded model-label bug is confirmed in the previous release. End-to-end HMS-1000-2WB model discovery is not yet confirmed with a user's real API metadata; model-field tests use synthetic fixtures. If no explicit model is returned, the neutral fallback is intentional.
