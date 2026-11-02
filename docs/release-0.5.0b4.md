# v0.5.0b4

- Add optional read-only battery temperature sensors, separate from inverter temperature. Keep each battery and returned expansion pack distinct; do not average their temperatures or infer models.
- Use the manufacturer's dedicated battery-device endpoint over certificate-verified HTTPS. Off by default; enabling it adds one background read per station every five minutes under the existing shared account budget. Rate-limit pauses, cancellation on unload and ten-minute response-age expiry apply.
- Preserve valid zero/negative temperatures. Missing or invalid values never become zero or renew old samples. Diagnostics omit device identities and raw responses.

After installing, restart Home Assistant. Open the integration's options and enable **Battery temperatures (beta)** / **Batterietemperaturen (Beta)** for the relevant station. Wait for the next read; new battery/pack devices and temperature sensors are added automatically when returned. Existing devices, entity IDs and history remain intact. Compare values and pack association with the Hoymiles app.

`fetched_at` means the cloud read time, not the battery measurement time. The cloud may itself return stale device data. Endpoint access and actual device values still require user confirmation; no fallback probes or guessed temperature scaling are used. See [source evidence and limits](battery-temperature-api.md).

Maintainer feedback: the b3 mode selector now works on the maintainer's setup. This does not complete the affected-user validation for other devices. This remains a beta; stable stays v0.4.2.
