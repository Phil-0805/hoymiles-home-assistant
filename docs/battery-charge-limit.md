# Separate battery cutoffs (v0.5.2b3 beta)

## Correction of the b2 mapping

The b2 charge-limit control changed action-83 `soc_h`, an upper work-mode SOC.
The maintainer's device test found that HA and cloud readback changed while the
separate charge/discharge cutoffs in the app remained unchanged. The value was
restored. In b3 the incorrect number and its matching sensor are removed from
the platform and from this entry's entity registry, including disabled entries.
The old setter is removed. No aliases redirect old automation calls to a new
command. Reserve-SOC, temperature, new cutoff and other entries' identities are
preserved. The raw mode value remains only in diagnostics as
`work_mode_upper_soc`; it is not labelled as an app cutoff.

## Android action 1537

Static inspection of Android V2.13.0 located `DisChargeActivity`, which uses
**1537** with **sl/sh** and device addressing. See the exact provenance, method
chain, routes and limitations in [Android protocol evidence](android-app-protocol.md).
These are not mode-level `soc_l`/`soc_h`, reserve SOC, or an EV charger setting.

b3 adds two separate number entities:

- **Discharge cutoff SOC / Entladeschlussstufe**: 10–70%.
- **Charge cutoff SOC / Ladeschlussstufe**: 50–100%.

The upper cutoff must be at least 10 percentage points above the lower cutoff,
matching the app slider. UI bounds also reflect the other last-read cutoff.
Each service call reads both values freshly under a lock, validates the pair,
changes only the requested value, writes both once and checks both by readback.
The counterpart is never filled with a default. Missing or invalid data prevents
a write. A failed confirmation never repeats the write automatically.

Enable **Allow battery controls** under Configure. The new entities have their
own IDs, distinct from the removed b2 number and the reserve-SOC control. No
heating/display-control permission is required. Settings are refreshed every
30 minutes using the shared account budget, with a dedicated manual refresh
button (30-second cooldown). A command read includes its status-poll requests.
Unsupported stations and ambiguous multiple battery controllers stay unavailable.
Diagnostics report allowlisted cutoff numbers/status under `battery_cutoffs`,
without serial numbers, account data or full command responses.

## Validation still required

The implementation has synthetic regression coverage, not a hardware success
claim. In b3, change one cutoff at a time, check that exact field in
the app after refreshing it, then restore the original value. Avoid simultaneous
app edits. Matching cloud readback does not by itself prove a physical cutoff
was applied. Reserve SOC remains a separate existing setting.

The historical b2 release is unchanged. Replacement controls are included in b3.
The Node-RED reference at e48ac860e2d1d17fdad108be4dfe306e511608e2 was also checked;
it contains telemetry nodes, not these cutoff commands.
