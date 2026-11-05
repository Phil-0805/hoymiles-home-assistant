# v0.6 planning: optional MQTT support

Maintainer request, 2026-11-05: investigate an optional MQTT connection alongside
the existing cloud integration for v0.6. This is a planned investigation, not a
compatibility or release commitment. It is separate from the v0.5.2 connection
fixes. MQTT implementation is outside the v0.5.2 release scope.

References:
- Community report: https://github.com/Phil-0805/hoymiles-home-assistant/issues/9#issuecomment-6664727610
- Hoymiles Micro Energy Storage MQTT Protocol Development Guide V0.5:
  https://www.photovoltaikforum.com/core/file-download/621124/

## TODO

- [ ] Record actual supported models, firmware versions and anonymized discovery
  examples. The guide alone does not prove support on every installed firmware.
- [ ] Inspect device-published `supported_topics` and discovery messages to select
  capabilities explicitly; preserve valid zero values and unavailable states.
- [ ] Evaluate existing HA MQTT discovery support before adding duplicate entities.
  Define stable identities and explicit source selection for cloud/MQTT data.
- [ ] Investigate read-only temperature, per-pack heating activity and power data.
  Distinguish heater activity from permission to heat.
- [ ] Investigate output and phase power limits, EMS modes and TOU support only
  where the device advertises them. Keep MQTT enums separate from unverified
  numeric cloud status codes.
- [ ] Verify write ranges, acknowledgements, device roles, retain/QoS requirements,
  control timing and recovery behavior. Require explicit permission for controls;
  avoid competing cloud/MQTT writes and automatic changes to the operating mode.
- [ ] Add synthetic capability, reconnect, privacy and command tests, then obtain
  real-device confirmation before claiming compatibility.
