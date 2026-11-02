# v0.5.0b5

- Group battery temperature sensors under the existing S-Miles Home station device alongside the other battery readings. Do not create separate battery/pack devices solely for temperature.
- Migrate b4 temperature entities automatically before platform setup. Keep unique IDs, entity IDs, custom names and disabled state; no entity deletion or reinstallation is required. Remove only unused integration-owned b4 battery devices without dependent devices. Preserve shared/composite devices, other entities and dependencies.
- Keep separate per-battery/pack measurements, distinguishable by the battery_serial sensor attribute. Reading, HTTPS verification, freshness rules and polling intervals are unchanged.

Install this prerelease and restart Home Assistant. The existing temperature sensor should appear on S-Miles Home. Its entity ID stays the same, preserving the existing recorder history. If the old battery device is used by another entity/device it deliberately remains. Do not delete the integration or the temperature entity manually.

Maintainer feedback: b4 battery temperature display works, and b3 mode switching works on the maintainer's setup. This does not establish affected-user compatibility or complete the release-readiness evidence. Stable remains v0.4.2.
