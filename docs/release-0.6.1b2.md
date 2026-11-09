# v0.6.1b2 — TOU mode readback and existing basic plans

**Experimental prerelease. Latest stable remains v0.6.0.**

This beta follows the new evidence in [issue #34](https://github.com/Phil-0805/hoymiles-home-assistant/issues/34):
the cloud completes the action-83 read and reports TOU/basic mode, but b1 rejects
the configuration and falls back to the older battery API. The precise missing
or conflicting field in the reporter's response has not been established.

## Changes since b1

- Keep an explicitly reported self-consumption/TOU mode readable even if its
  SOC or plan configuration is incomplete. Do not fall back to the older
  battery API solely because that known mode cannot safely be written.
- Separate the displayed current mode from validated write targets. The mode
  select can display TOU and switch to self-consumption when valid SOC settings
  are available. Without a safe target, the select remains unavailable while
  the read-only mode sensor can still show the reported mode.
- Recognize **explicit basic-plan ID 0**, which the inspected Android app sends
  for custom plans. Previously, only positive IDs were accepted. This is an
  evidenced compatibility correction, not proof of the reporter's actual ID.
- Validate the existing plan's weekday groups, actions and time windows before
  allowing activation. Missing IDs, negative default selectors, invalid or
  overlapping intervals, unsupported actions and incomplete plans remain
  blocked for writing. No default schedule or identifier is invented.

Writes still require battery-control permission, a fresh read under the existing
lock, one write and full mode/plan confirmation. Fresh plan changes are preserved;
a plan that becomes incomplete blocks the write. No new endpoints, faster
polling or automatic repeat writes are added. Existing entries, entity IDs and
dashboards are retained. The regional-login changes from b1 are included.

**This is not a TOU schedule editor.** Configure time windows in the official app.
HA can activate an existing plan only when its complete supported configuration
is returned. **Reserve-SOC control remains unavailable in TOU**, whose thresholds
belong to its plan. Recurring live-sample gaps are a separate unresolved issue;
b2 does not claim to fix them or the remaining login reports.

## Test this beta

1. In HACS, enable prerelease versions and install **v0.6.1b2**, then restart
   Home Assistant. Keep the existing integration; do not delete and recreate it.
2. Refresh battery settings once and compare the displayed mode with the app.
   In TOU, distinguish the mode sensor/select from the intentionally unavailable
   reserve-SOC control. Report which exact entity still fails, if any.
3. If you choose to test switching, use a plan already configured in the app,
   enable battery controls and compare the result in both HA and the app. The
   cloud confirmation alone does not establish physical charging behavior.
4. Share only fresh `hoymiles_home.cloud_logging` warning lines and privacy-checked
   diagnostics. Do not share credentials, tokens, plan contents, device
   identifiers, raw responses or HARs.

A successful read may restore the mode display while some write options remain
unavailable; this is intentional when configuration is incomplete. Testing on
the affected installation is still required before claiming issue #34 resolved.

For manual installation, download `hoymiles_home.zip` from
[this release](https://github.com/Phil-0805/hoymiles-home-assistant/releases/tag/v0.6.1b2),
back up the installed integration and extract inside
`custom_components/hoymiles_home`, then restart HA. The ZIP contains
`manifest.json` at its root. To roll back, restore the backup or reinstall the
previous version and restart HA.

Local validation: **928 Home Assistant tests and 134 subtests on each of HA
2026.10.4 and 2026.11.0**, **56 unit tests**, syntax, translation-key parity and
whitespace checks passed. Publication is gated on required CI, HACS and Hassfest
checks. No real account or device operation was performed by the agent.

[Protocol evidence and limitations](https://github.com/Phil-0805/hoymiles-home-assistant/blob/v0.6.1b2/docs/work-mode-83.md)
· [Issue investigation](https://github.com/Phil-0805/hoymiles-home-assistant/blob/v0.6.1b2/docs/issue-34-investigation.md)
