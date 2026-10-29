# Integration boundaries and release invariants

## Responsibilities

- `api.py`: endpoint requests, authentication exchange and scoped read/write commands. Shared error types live in `errors.py`. A write is sent once, followed by readback; never put control writes into a generic retry loop.
- `cloud_runtime.py`: shared in-memory token/login lock, account request pacing, concurrency and Retry-After pauses. `AccountPool` references sessions by credential fingerprint and releases them after the last entry unloads. Signed live URLs remain per station/client.
- `coordinator.py`: live polling, station-local daily energy, settings lifecycle and locked settings writes. It does not decode binary payloads or wait for slow module polling inside the live refresh.
- `module_polling.py`: independent cancellable chart/detail polling, five-minute schedule and response/sample freshness. Background updates notify entities without claiming a failed live connection is healthy.
- `protobuf.py` / `module_data.py`: bounded independent decoders. Match known station/day/device/port identity; missing values remain unknown. Optional detail samples align by their own inverter time array and expire by vendor sample time.
- `battery.py` / `telemetry.py`: capability and numeric interpretation. Keep unsupported mode IDs, unverified units and unknown status codes distinct from supported controls.
- Entity platforms: presentation and HA services only. Preserve existing unique IDs and device identifiers. New optional sensors do not rename or delete old entities.
- `diagnostics.py`: allowlisted values and capability states. Never export raw cloud payloads, account/device identifiers, credentials or tokens.

## Request budget

Live cadence follows `max(3 seconds, server dly)`. Slow module polling is no more frequent than five minutes; enabling details adds one station snapshot per cycle. Settings are read every thirty minutes; manual refreshes have a thirty-second cooldown and join a running read.

All HTTP requests for identical account credentials share one budget: minimum one second between starts, maximum two in flight. Authentication is coalesced under one lock. Retry-After pauses the account budget. Other applications/integrations do not share this state; the vendor's actual quota is undocumented. Do not claim these client bounds guarantee a particular daily quota.

## Validation layers

1. Dependency-free decoder, calculation and release-gate tests.
2. HA integration tests with mocked cloud boundaries: identity/history schema, options, lifecycle, pacing, unsupported capabilities, freshness and error paths.
3. Optional pinned Node-RED decoder comparison using a synthetic fixture, without Hoymiles account access.
4. Real-device/app comparisons recorded in issues. These remain essential; the first three layers cannot establish undocumented device semantics.

## Stable publication

`docs/release-readiness.json` tracks the candidate, target stable version, affected-user evidence and maintainer approval. `scripts/check_release_readiness.py` is executed before creating a new stable release. Prereleases still require tests/HACS/Hassfest but do not manufacture evidence. Invalidate affected confirmations after material code changes; the gate checks recorded evidence completeness and cannot authenticate the truth of a hardware test.

Current unverified areas are cloud EMS/charge enum meanings, model-specific maximum-power settings and extra control modes. Keep raw diagnostics and disable unsupported controls until repeatable evidence exists. Do not turn MQTT string enums or Node-RED README sign conventions into cloud numeric mappings.
