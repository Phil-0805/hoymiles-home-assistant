# v0.6.1b1 — regional login investigation

**Experimental prerelease. Latest stable: v0.6.0.**

This beta investigates remaining login reports in issues #16/#27. The affected
reporter confirmed the **S-Miles Installer app**, not S-Miles Home. His specific
failure remains unconfirmed; a successful Installer login does not demonstrate
Home API access. Another reporter's station-validation failure is separate.

Changes:

- Query account routing once before pre-inspection. Accept only explicit known
  HTTPS authentication bases with a matching DC0/1/4; stop on rejected, missing,
  unsafe or inconsistent results. No alternate-server/password retry chain.
- Use the validated region for pre-inspection and the fresh challenge DC for
  login. Keep v1/v2/v3 algorithm selection explicit. Share the known DC for the
  existing Home User-Agent across clients using the same session.
- Treat response-envelope status 100 as session expiry, invalidate the shared
  token and stop. Never replay a settings write after this result.
- Recognize evidenced client-version/Home-app-only errors using fixed diagnostic
  categories. Daily login-limit responses pause the account. No server text or
  credential material enters logs.

There is one extra budgeted request per login; live polling is unchanged.
Home data routing remains separate from authentication routing. This beta does
not add a complete Installer/web data profile. A rejected plant request does
not automatically select another API. Existing config entries, entities and
control permissions are retained.

## Install and report

In HACS, open the integration's download/version selection, enable prerelease
versions and choose **v0.6.1b1**, then restart Home Assistant. Keep the existing
integration and dashboards; do not delete and recreate the entry.

For a manual installation, download `hoymiles_home.zip` from
[this release](https://github.com/Phil-0805/hoymiles-home-assistant/releases/tag/v0.6.1b1).
For a local build, use:

```sh
python scripts/build_release_zip.py --output /tmp/hoymiles_home-0.6.1b1.zip
```

Back up the installed `custom_components/hoymiles_home` directory, extract this
ZIP **inside that directory** and restart Home Assistant. Keep the existing
integration and dashboards. The generated ZIP has `manifest.json` at its root.

Test once and report login, plant discovery/validation and current readings
separately. Also test an existing working Home/DC0 installation. Region response
compatibility is experimental and must be checked before a stable release.
If it fails, share only fresh `hoymiles_home.cloud_logging` warning lines with
stage/reason and numeric/type labels; `login_region` is the new first step.
Do not share credentials, tokens, device identifiers or raw responses/HARs.
No password change, entry deletion or device command is required for this test.
To return to stable, restore the backup or reinstall v0.6.0 and restart HA.

See [the investigation and evidence limits](https://github.com/Phil-0805/hoymiles-home-assistant/blob/v0.6.1b1/docs/login-routing-0.6.1.md) for the
remaining hypotheses and minimal safe feedback. No real account login or device
operation was performed by the agent. Issue replies are supplied separately
to the maintainer and are not posted automatically.

Local validation: **874 HA tests plus 134 subtests on each of HA 2026.10.4 and
2026.11.0**, **56 unit tests**, syntax, translation-key parity, documentation
links, workflow YAML/beta trigger, whitespace and the 37-file package passed.
Publication is gated on CI tests, HACS and Hassfest checks.

## Additional investigation: issue #34

This beta also adds privacy-preserving structural diagnostics for rejected action-83
work-mode results (`work_mode_read/invalid_work_mode_settings`). It helps separate
TOU parser rejection from subsequent legacy battery-settings failures. TOU
acceptance and all control behavior are unchanged; this is **not a confirmed
fix** for unavailable mode/reserve entities. Reserve control in TOU is deliberately
restricted. Reporter feedback on the exact entities, TOU submode and app state
is pending. See [the separate investigation](https://github.com/Phil-0805/hoymiles-home-assistant/blob/v0.6.1b1/docs/issue-34-investigation.md).
