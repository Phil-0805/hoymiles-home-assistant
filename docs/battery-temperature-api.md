# Battery temperature source

Manufacturer web client inspected on 29 October 2026:

- [Main API/temperature formatting bundle](https://static.hoymiles.com/cdncache/website/js/index-CTUY73vV.js), SHA-256 `a2790e4875668e9de1f8a3aacb0164bffbfe8cfb6ca4180e042330aac3240c98`.
- [Plant topology bundle](https://static.hoymiles.com/cdncache/website/js/index-CZ5oZNvO.js), SHA-256 `f1e45abe8c7c3d36c3c1f5d2c09730bcde08610f92fcd3fe89a5b3448dd6d068`.

`getAuroraInfo(stationId)` reads `POST https://neapi.hoymiles.com/pvm/api/0/dev/au_inv/au_s_c` with `{id: stationId}`. The topology uses each returned battery's `sn` and `temp`; expansion records are in `pack_list` and also expose `sn`/`temp`. Temperature formatting treats the API value as Celsius and converts only for a Fahrenheit display preference. No factor of ten, inverter temperature or average across batteries is substituted.

The integration reads this dedicated device endpoint only when the per-entry Battery temperatures option is enabled (off by default). One background read per five-minute cycle shares the normal account request budget, HTTPS certificate verification, redirect restrictions and rate-limit pauses. No device commands or additional login loop are added. Unloading cancels the read.

Keep battery and expansion-pack identities separate, using returned hexadecimal serials of 12–24 characters. No model is inferred from a serial prefix. Ignore invalid identities, reject conflicting duplicates and bound device/pack counts. Each finite temperature, including zero and negative values, is accepted only within the conservative -80 to 120 Celsius guard; missing/invalid values do not create a zero or renew an older reading's age.

The endpoint does not establish a vendor measurement timestamp. `fetched_at` and the ten-minute freshness limit refer to receipt of a valid cloud response, not physical sample age. An old device measurement repeated by the cloud cannot be detected from these fields. Station disconnection makes the sensors unavailable. Diagnostics export only the option state, poll status and device count, without serials or raw payloads.

Evidence is inspection of the manufacturer's public JavaScript, not an authenticated capture or real battery test. Hardware/app comparison, device-specific endpoint access and expansion-pack support remain to be confirmed. A separate phase-topology endpoint exists in the web UI; this beta deliberately does not add fallback/probing requests for unsupported accounts.

Since b5, battery/pack temperature entities use the existing S-Miles Home station device. Each sensor keeps its b4 unique ID; the battery serial is exposed as a sensor attribute to distinguish measurements without creating extra devices. Setup migrates existing b4 registry entries before loading sensor platforms, preserving entity IDs, custom names and disabled state. Only empty, integration-owned legacy battery devices without dependent devices are removed.
