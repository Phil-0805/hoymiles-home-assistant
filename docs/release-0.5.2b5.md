# v0.5.2b5 — cloud connection diagnostics and live-address recovery

This prerelease investigates the login/setup and missing live-server address
reports in issue #16. It includes the earlier v0.5.2 beta features. Stable stays
v0.5.1. The recovery path has synthetic coverage; affected-account confirmation
is still needed. A successful device test is not claimed.

## What changes

- Warning logs identify login challenge, login, station discovery/validation,
  mobile/web live-address lookup and requests to the selected live server.
- Fixed reasons distinguish rejected cloud responses, numeric HTTP errors,
  timeouts, transport errors, invalid JSON/response types, invalid login
  challenges, missing tokens, missing URIs and unsafe URIs. Cloud status codes
  are limited to bounded numeric values; response summaries contain only known
  structural labels. No raw server error text is logged.
- Setup now logs failures even when no config entry has been created yet.
  Repeated identical request failures are suppressed for each client instance.
- If the mobile live-address lookup succeeds but has no URI, try the
  manufacturer's web lookup with the same station ID. Both routes use the
  existing account request budget and HTTPS/host checks. Authentication,
  rate-limit, transport, malformed response and unsafe-address failures do not
  trigger the web fallback. Neither credentials nor device settings are changed.
- Both routes returning no URI still fails explicitly; no live values are
  invented and station totals are not substituted for live measurements.

## How to test / So testen

Select **v0.5.2b5** in HACS/Marketplace, install it and restart Home Assistant.
For an existing failing entry, reload it once; for a first installation, retry
setup once. There is no need to delete a working/existing entry or enable
battery/device controls for this test. A firmware update is not required by b5.

Open **Settings → System → Logs** and search for `hoymiles_home.cloud_logging`.
The new warnings work at the normal logging level; debug logging is unnecessary.
Please report integration version, HA version, whether setup now works, and the
new `Cloud request failed` / `Cloud setup failed` lines. Recovery through the web
route also produces an info message when info logging is enabled.

**Deutsch:** Bitte neue Warnungen mit `stage=`, `reason=`, gegebenenfalls
`http_status=` und `cloud_status=` sowie das Ergebnis des erneuten Versuchs melden.
Diese Felder grenzen die Fehlerstelle ein. Ein erfolgreicher Login-Test und ein
fehlgeschlagener Live-Abruf können unterschiedliche Ursachen haben.

Examples (fixed labels and synthetic status only):

```text
Cloud request failed: stage=live_uri_mobile reason=missing_uri cloud_status=0 data_type=object uri=missing
Cloud request failed: stage=login reason=http_error http_status=403 cloud_status=unavailable data_type=null uri=missing
Cloud setup failed: stage=login reason=cloud_rejected
```

The integration's new diagnostic lines contain no account names, email,
passwords, challenge values, tokens, station/device IDs, URLs, headers, raw
responses or exception tracebacks. This does not control unrelated HA or
third-party debug logs; share the requested lines rather than a full system log.

## Implementation evidence and validation

The manufacturer web bundle exposes `getSecDataUri(sid)` using
`/pvm/api/0/station/get_sd_uri` with `{sid}`. The integration's existing mobile
route is `/pvmc/api/0/station/get_sd_uri_c`. The web fallback uses the same
explicit `data.uri` contract and trust checks; other shapes are not guessed.
Source: https://static.hoymiles.com/cdncache/website/js/index-CTUY73vV.js,
archived 2026-11-05, SHA-256
`a2790e4875668e9de1f8a3aacb0164bffbfe8cfb6ca4180e042330aac3240c98`.
The public client is evidence of the route, not proof it is enabled for every account.

Tests cover fallback success and ordering, absent URI variants, rejection of
unsafe/malformed addresses, no fallback for authentication/rate/transport errors,
bounded retries, warning deduplication, real HTTP/JSON response handling, initial
setup logging and exclusion of sensitive synthetic values. No live account or
device commands were used to validate this change.

Local validation: **489 HA tests and 32 unit tests passed**, Python compilation,
translation-key parity and `git diff --check` passed. CI additionally validates
HA 2026.10.4 and 2026.11.0, HACS and Hassfest before release.
