# Developer overview

## Responsibilities

- `api.py`: authentication and scoped requests. Writes are sent once; confirmation uses subsequent reads.
- `cloud_runtime.py`: shared in-memory token, login lock, request pacing and Retry-After pauses for configured stations using identical credentials.
- `coordinator.py`: live data, local daily energy, settings lifecycle and serialized control operations.
- `module_polling.py` / `battery_telemetry.py`: independent cancellable background telemetry with freshness checks.
- `protobuf.py` / `module_data.py`: bounded binary decoders. Keep identity checks and missing-value handling separate from presentation.
- `battery.py` / `telemetry.py`: capability and numeric interpretation without inventing undocumented status meanings.
- Entity platforms and `device_migration.py`: presentation and registry changes preserving existing identities, customization and history.
- `diagnostics.py`: allowlisted values without raw cloud payloads or account/device identifiers.

## Requests and freshness

Live cadence follows the longer of three seconds or server `dly`. Module telemetry runs every five minutes; each enabled optional telemetry path adds one station read per cycle. Settings are read every thirty minutes, with a thirty-second manual refresh cooldown.

Configured stations using identical credentials share at least one second between HTTP starts and at most two in-flight HTTP requests. Retry-After pauses the account; these client bounds are not a documented manufacturer quota. Setup flows and other applications use separate clients.

Battery writes require the explicit `battery_controls` option (default off, including upgrades). The coordinator checks this permission before cloud preflight and immediately before the write, so direct service calls and an unload during preflight cannot bypass it. Entity identities remain unchanged.

Every control operation reads current settings before writing and verifies the target mode/configuration afterwards. The unofficial API cannot make concurrent app/HA edits atomic. Failed live refreshes break local energy integration anchors. Station totals expire by response age and station-local period boundaries.

Ordinary PV-input charts and battery temperatures use cloud response age. Additional inverter metrics retain individual vendor sample times. Do not claim physical measurement freshness without a reliable source timestamp.

## Checks

Run unit tests with `python -m unittest discover -s tests -v` and HA tests with `python scripts/run_ha_tests.py` after installing `requirements-test.txt`. CI also validates HACS and Hassfest before publishing. Stable publication requires a private `RELEASE_READINESS_JSON` repository secret matching the version and exact commit. The gate rejects missing or stale approval; automated tests do not establish hardware compatibility. See [release maintenance](release-maintenance.md).

The optional `scripts/compare_nodered_reference.py` compares a synthetic fixture against a checksum-pinned public decoder. Use `--reference-file` for a fully offline check. No Hoymiles account access is needed.

Protocol sources: [work modes](work-mode-83.md) and [battery temperatures](battery-temperature-api.md).

HTTP JSON bodies and JSON embedded in command-status strings share the same size, depth and object-shape validation. Sensor attributes expose only known finite numeric settings, generated mode names and fixed status flags. Raw settings and TOU plans remain internal to the write/readback path.

GitHub Actions are pinned to commit SHAs and updated through Dependabot. Checkout does not persist credentials; only the release job receives repository write permission. Historical tags remain unchanged.

Resolve station timezone names in `async_setup_entry` with HA's async timezone helper and pass the resulting `tzinfo` to the coordinator. Its default uses HA's cached timezone object. The options flow enumerates the timezone database in the executor and caches the sorted selector list.

CI tests Core 2026.10.4 and 2026.11.0. The current fixture package 0.13.375
pins 2026.10.4; CI installs the target Core afterwards. The test runner imports
Core before pytest to establish the 2026.11 HTTP aliases and supplies an import
adapter for an unused, removed logger fixture function. That fixture raises if
called. No integration or Core behavior is replaced. Remove this narrowly scoped
adapter when the fixture package supports 2026.11.
