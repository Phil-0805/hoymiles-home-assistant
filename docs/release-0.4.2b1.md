# v0.4.2b1 — inverter model discovery beta

This is a pre-release for testing. v0.4.1 remains the stable release.

## Changes

- Read the explicit `model_no` field used by the S-Miles web device API.
- If the Home device tree lacks a model, try the read-only web device tree and microinverter detail endpoints during initialization. Match devices by ID and reject conflicting serial numbers; never replace existing identity fields.
- Apply any returned model before creating device entities and deciding which PV inputs to query.
- Optional metadata calls have a shared 12-second budget. Rejected requests or missing model data do not prevent normal telemetry. A neutral model remains if no exact model can be retrieved; no model is guessed from a serial prefix or a configured power limit.
- Add allowlisted model-discovery diagnostics. They contain model results and retrieval statuses, not credentials, full serial numbers, station IDs or raw cloud responses.

## Test in Home Assistant

1. Enable pre-release versions for this repository in HACS, then download v0.4.2b1.
2. Restart Home Assistant. Keep the existing integration configured.
3. Open the microinverter device and check the model line. The expected result is your actual model, e.g. HMS-2000-4WB or HMS-800-2WB, if the cloud detail endpoints expose it to your account.
4. Confirm that measurements and history remain present. Previously registered surplus PV entities are not deleted automatically.
5. If the model is still generic, download the integration diagnostics from Settings > Devices & services and share the `inverters` section. It shows whether metadata was unavailable, timed out, or lacked an explicit model.

To return to stable, redownload v0.4.1 in HACS and restart Home Assistant.

## Validation

26 unittest tests and 48 Home Assistant pytest cases pass locally (74 total). Network responses are mocked; this is not a live-account confirmation. The read-only metadata routes and `model_no` field are also used by other cloud clients. Some Home accounts may not have access to them. This beta must be tested with real devices before stable publication.
