# v0.4.2 — cloud inverter model discovery

## Fixed

- Load the real inverter model from `model_no`, using supplemental read-only device metadata when the S-Miles Home device tree omits it. This completes the model-discovery work following #6; v0.4.1 had only removed the incorrect hard-coded model label.
- Apply the identified model before creating PV sensors and querying module charts. Two-input models use PV1/PV2; four-input models use PV1–PV4.
- Optional metadata requests share a 12-second budget. If an account cannot access the metadata or no exact model is supplied, normal telemetry continues with the neutral model fallback and legacy four-input probing. No model is guessed from a serial prefix or power limit.

## Diagnostics

Download integration diagnostics from Settings > Devices & services if the model remains generic. The `inverters` section reports model-discovery results without account credentials, full serial numbers, station IDs or raw cloud responses.

## Validation

The maintainer tested v0.4.2b1 on 28 October 2026 and confirmed correct HMS-2000-4WB and HMS-800-2WB model labels with PV readings on both installations. This does not establish compatibility with every model, firmware or account, or verify every function.

74 automated tests pass (26 unittest tests and 48 Home Assistant pytest cases), including optional API access, model propagation into device entities, port selection, identity preservation, timeouts and diagnostic privacy. HACS and Hassfest are checked before publication.

## Upgrade

Update through HACS and restart Home Assistant. Keep the existing integration configured; no removal or reconfiguration is required. Existing device and per-port sensor identifiers are preserved. Previously registered surplus PV3/PV4 entities on a two-input inverter may remain in the registry; they are not deleted automatically. A four-input inverter retains PV4 even when only three panels are connected.
