# v0.5.0b3

- Add switching between Self-Consumption and an existing supported TOU configuration on the consumer action-83 path. Reuse the saved recommended/basic/advanced selection; do not generate, edit or delete schedules. Missing/incomplete plans and unsupported submodes remain blocked. Existing entity IDs stay unchanged.
- Refresh settings once before an explicit mode change so app schedule edits supersede the cache. Verify the target mode and full target configuration by reading back over certificate-verified HTTPS. Failed verification does not repeat the write automatically.
- Keep optional frequency, voltage and temperature samples independently. A missing field no longer deletes another still-fresh reading or borrows the timestamp of a newer metric. Each sample expires after ten minutes using its own vendor timestamp; polling stays at five minutes.

Install this beta and restart Home Assistant; do not delete the integration. Wait for the normal settings read, or use the existing refresh button (thirty-second cooldown). Check that Time of Use appears only when the app already has a supported TOU configuration. Compare a deliberate switch with the app and switch back; verify your plans and SOC limits are unchanged. The reserve-SOC slider is unavailable in TOU because that mode uses schedule-specific thresholds.

The manufacturer web client establishes the command mapping; automated tests do not replace real-device confirmation. The maintainer reports temperature, voltage and frequency readings working after a delay. App accuracy comparison and mode-switch tests remain pending. This is a prerelease; stable remains v0.4.2.

See [protocol evidence and limitations](work-mode-83.md).
