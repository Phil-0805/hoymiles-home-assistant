# Issue #55: six-input HMT monitoring

Prepared for v0.6.2b1. Investigation: 2026-11-14; device validation pending.
[Report](https://github.com/Phil-0805/hoymiles-home-assistant/issues/55).

## Reproduced code gap

The reporter uses an HMT-2250-6T with a DTU-Pro-S and sees only four individual
PV inputs, while total generation matches the official app. The existing model
parser recognizes selected HMS models only. Unknown models fall back to four
ports. Both entity creation and module chart polling use that same helper, so
the fallback omits entities and chart reads for inputs 5 and 6. Station total
generation is obtained separately; its agreement does not prove individual
module data for the omitted inputs was previously fetched.

## Evidence and implementation

The manufacturer-authored *Three-phase Microinverter HMT-1800/2250 User Manual*,
section 8.1, lists HMT-1800-6T and HMT-2250-6T with three MPPTs and two inputs
per MPPT: six physical PV inputs, not six MPPTs.

- Public PDF, hosted by a third party:
  <https://panele-sloneczne.com/wp-content/uploads/USER-MANUAL_HMT-18002250-6T_GLOBAL_EN_V202207.pdf>
- Retrieved 2026-11-14; SHA-256:
  `88ee4d2992751f597390cacd6838cf55a7a6d2653291ffff7b7a4ed3a1c46207`.
- Original manufacturer download-list lookup timed out. Hosting on this mirror
  is disclosed; it is not an independent verification of this installation.

The local parser accepts these two explicit model designations in the existing
model metadata fields. It does not infer a model from serial numbers, numeric
model IDs, installed-panel counts or arbitrary HMT power/suffix combinations.
Existing HMS matching and the unknown-model fallback remain intact.

The common `inverter_ports` helper now returns 1 through 6 for these models.
Existing discovery can retain such model metadata from the device tree or its
already implemented, identity-checked enrichment path. This adds no discovery
endpoint or fallback. Entities keep their existing entry/inverter/port IDs for
ports 1–4; ports 5 and 6 each add power, voltage and current sensors.

Module polling uses the existing read-only chart transport and cadence. An HMT
now needs six per-port chart reads per cycle instead of four; shared request
pacing, concurrency, server pauses, deadlines and field freshness stay intact.
This does not enable Enduser module monitoring, which remains unimplemented.

HMT recognition is deliberately separate from `standalone_hms_assessment`.
Neither a raw HMT node nor enriched HMT metadata grants the HMS-only standalone
output-control capability. No write maximum is inferred from the model name.

## Verification and remaining device test

Synthetic tests cover direct/enriched metadata, unknown/malformed models,
serial-only rejection, 18 module entities with stable existing IDs, port 5/6
values, mixed two/four/six-input polling and continued denial of HMS standalone
control targeting for HMT.

Full local validation on HA 2026.11.0: 1,278 HA tests and 56 unit tests passed.
The pytest run emits its existing anyio assertion-rewrite warning. Actual
availability and same-time app comparison of inputs 5/6 on the reporter's setup
remain unconfirmed. No real accounts or devices were accessed.
