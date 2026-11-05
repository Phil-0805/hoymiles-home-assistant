# v0.5.2b6 — bounded login redirects and clearer live diagnostics

This beta follows the issue #16 report that b5 fails at
`stage=login_challenge reason=redirect_rejected`. The failure occurs before
password challenge calculation. The Android app handles certain redirects;
this candidate implements a narrower, explicitly checked version of that path.
Affected-user testing is still required. Other login/live failures may have
separate causes. Stable remains v0.5.1.

## Login recovery attempt

- Allow one manual HTTP **302 or 307** redirect during auth pre-inspection or
  login, preserving the original POST and JSON body as in the inspected app.
- Restrict the destination to the **same auth operation path** on explicitly
  allowed production HTTPS API hosts (`euapi`, `neapi`, `indapi` under
  `hoymiles.com`). Queries, fragments, URL credentials, alternate ports,
  test/CDN/external hosts, unexpected paths and further redirects are rejected.
- Public auth calls omit any previous Authorization token. Other API redirects
  remain blocked. Every request uses the existing shared account budget and
  rate-limit handling; TLS certificate validation stays enabled.
- Rejected redirects now identify the numeric HTTP status and a fixed policy
  reason such as `blocked_target` or `hop_limit`. The target URL is never logged.

Evidence: the archived Android V2.13.0 `RedirectInterceptor`, app HTTP setup and
DNS host list; see [protocol notes](android-app-protocol.md#login-redirects--b6-investigation).
The affected user's actual redirect destination has not been captured, so this
is not a claim that every account will now connect.

## Live logging

Malformed live samples now show only relevant structure: `data_type`,
`flow_type`, `con_type`, `con_state` and `power_type`. The misleading
`cloud_status=unavailable` / `uri=missing` fields are removed from this specific
warning; they did not establish a missing address or cloud outage there.

A subsequent accepted live sample logs one recovery message at warning level,
even if recovery occurs on a later poll. Repeated identical failures are
suppressed within an episode, then re-armed after recovery. Accepted offline
samples retain their existing meaning; recovery means valid communication,
not proof that the inverter is online. No live acceptance rules were loosened.

## Packaging and documentation

- Releases now attach **hoymiles_home.zip** for HACS installation and GitHub
  download counts. The ZIP contains tracked integration files directly at its
  root, together with the MIT LICENSE. The release is published only after
  upload succeeds.
- Counts represent asset requests, including updates/re-downloads; they do not
  recover earlier source downloads or count unique/active users.
- English/German READMEs are reorganized with accurate status badges,
  installation, controls, compatibility, upgrade and troubleshooting guidance.
- Optional MQTT support is recorded as an investigation for v0.6; this beta adds
  no MQTT runtime feature. The MIT license is unchanged.

## Test instructions / Testanleitung

1. Select **v0.5.2b6** in HACS/Marketplace, install it and restart Home Assistant.
2. Retry first-time setup or reload the existing failing entry once. Do not
   delete existing entries, and no battery-control permissions are needed.
3. Report whether the login and subsequent live readings now work, together with
   integration and HA versions. If setup fails, share the new warning lines from
   **Settings → System → Logs → Home Assistant Core**, logger
   `custom_components.hoymiles_home.cloud_logging`. Debug logging is unnecessary.

**Deutsch:** Nach Update und Neustart erneut einrichten beziehungsweise den
bestehenden Eintrag neu laden. Bitte Ergebnis und die neuen Warnungen mit
`stage`, `reason`, gegebenenfalls `http_status` und `redirect_policy` melden.
Kein Passwort, Token und keine vollständige Cloud-Antwort oder Weiterleitungs-URL
posten. Bei `live_data` zeigt eine spätere `Cloud request recovered`-Warnung an,
dass wieder ein gültiges Datenpaket akzeptiert wurde.

Examples with fixed labels only:

```text
Cloud request failed: stage=login_challenge reason=redirect_rejected redirect_policy=blocked_target http_status=302 cloud_status=unavailable data_type=null uri=missing
Cloud request failed: stage=live_data reason=invalid_live_data data_type=object flow_type=missing con_type=missing con_state=missing power_type=object
Cloud request recovered: stage=live_data previous_reason=invalid_live_data
```

Logs exclude email, passwords, challenges, tokens, identifiers, Location headers,
URLs, raw response data and exception tracebacks. No live accounts were used for
validation. Please share the relevant new lines instead of a full system log.

## Validation

Local: **527 HA tests and 35 unit tests passed**, including full redirected
login, blocked-target/status/hop cases, shared-budget usage, token omission,
rate limits, live recovery, privacy and ZIP contents. Python compilation,
translation-key parity, documentation file links, workflow structure and diff
checks passed. Release CI also checks both HA 2026.10.4 and 2026.11.0, HACS and
Hassfest. Real affected-account confirmation remains pending.
