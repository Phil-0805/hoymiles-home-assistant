# Login routing investigation — 2026-11-09

## Reports and established facts

Read the current [issue #16](https://github.com/Phil-0805/hoymiles-home-assistant/issues/16)
and [issue #27](https://github.com/Phil-0805/hoymiles-home-assistant/issues/27).
They contain different failures:

- **rupacheco:** v0.6.0, HA 2026.11.0; request-level `login_challenge`,
  `cloud_status=1`, `data_type=string`. The server rejected pre-inspection before
  any password-derived challenge was submitted. He explicitly confirmed a fresh
  **S-Miles Installer** login, not a Home-app login. Website and Installer access
  do not establish Home endpoint permissions. The actual cause remains unknown.
- **jacksontploong:** `station_validation/cloud_rejected`; this is after a token
  was obtained and concerns the selected station's Home device-tree operation.
  No request-level status has established the reason. Do not infer the first
  reporter's account profile or routing from this separate report.
- **gillesBdl:** DC0 login and matching readings were confirmed after b9. Preserve
  challenge-selected DC0 login and the explicit server-selected hash version.

The local untracked `issue-27-investigation.md` predates these changes and is
preserved. Its current-code observations describe the earlier implementation.

## Sources checked

The live manufacturer's entry was downloaded on 2026-11-09 and its **actually
linked** script inspected. Files remain outside the repository.

| Source | SHA-256 |
| --- | --- |
| `https://global.hoymiles.com/website` | `dc0ec5022780bd53c8a4cd819d41bcfef62be58e6c9b3c2d26cce4d4cef88b1d` |
| `https://static.hoymiles.com/cdncache/website/js/index-BTRAEMTt.js` | `093c693196cf7966d1565ee7cca170d65f7de28ba5d9078f911ec9e164b64164` |

The script still uses v1/v2 MD5+SHA256 and v3 Argon2id, chooses subsequent login
routing from DC, and treats envelope status `100` as expired authentication.
Its entry does **not** establish a `region_c` call: that string is absent from
this bundle. It uses web plant endpoints rather than the Home device tree.

The archived Android V2.13.0 package was inspected statically again. Provenance,
mirror/signature limitations and archive hashes remain as recorded in
[android-app-protocol.md](android-app-protocol.md). `OemLoginActivity.s0()` sends
`{email: account}` through `IAM_C_REGION_C`; `online_domain.json` maps this to
`/iam/pub/0/c/region_c`, domain id 1 (euapi). Its callback stores returned user
center data, updates configuration and proceeds with the OEM login. This is
**not** evidence that every regular Home login calls region discovery or that
OEM subsequently uses the same v3 sequence. `HttpUtils.AnonymousClass3.e()`
intercepts envelope `100` and enters the app's auto-login path.

Comparison sources read directly on 2026-11-09:

- [Eistee82/ioBroker.hoymiles](https://github.com/Eistee82/ioBroker.hoymiles/tree/2d7b60e6898eb9aa3f1175e4f4dac2cedf338d8c),
  `cloudConnection.ts`, `constants.ts`, `test/cloudConnection.test.js`.
  Git blob IDs respectively `bf2029d6233848cd117459b907eab8b7dfc302ff`,
  `a3712ebf612a28807af4557254f65e8e165bf4c4`,
  `7a0484e8da4e482946d38a1325bf275dc66756b2`.
  Its `{login_url, dc}` region response and region-before-v3 sequence are
  **implementation evidence from another project**, not our affected account's
  capture. Its fallback on arbitrary region errors, salt-presence algorithm
  inference and classification of every web rejection/403 as Home were not
  adopted. Those shortcuts could conceal authentication or permission failures.
- [Philra94/homeassistant-hoymiles-cloud](https://github.com/Philra94/homeassistant-hoymiles-cloud/tree/ff91ca7c36ef7b4cbabca18cb37a7ed123387eaf),
  `auth.py`, `hoymiles_api.py`, `const.py`, plus issues
  [27](https://github.com/Philra94/homeassistant-hoymiles-cloud/issues/27) and
  [30](https://github.com/Philra94/homeassistant-hoymiles-cloud/issues/30).
  Blob IDs `ddb10229d512d929dfdac89595d72ed470b2e465`,
  `e66818b217965d6d631d2119343068906ba64d0a`,
  `7396fb45788c26fbef8ee4b9041bc1b4935954a4`.
  Reports evidence known client-version and Home-app-only error messages. The
  Home UA format already existed in this integration; introducing it again is
  not a fix. Reports about one region do not justify hardcoding all accounts
  to that region or trying multiple password protocols.

Both comparison projects' LICENSE files were checked: MIT. The implementation
here is independently written against this client's existing boundaries; no
third-party source files were incorporated.

## Candidate behavior and boundaries

The local **v0.6.1b1** candidate makes a single account-region query before
pre-inspection. It accepts only DC0/1/4 and an exact HTTPS production base
(neapi/euapi/indapi, optional root slash) matching that DC. Credentials in URLs,
ports, paths, query/fragment, whitespace, unknown hosts, missing fields and
inconsistent pairs stop before pre-inspection. The returned URL is never used
as an arbitrary request target; the next URL is constructed from local constants.
No fallback follows a rejected/invalid/failed region query. This intentionally
conservative policy can expose an unsupported account at the new `login_region`
stage; real Home and Installer account testing is required before stable use.

Pre-inspection goes to that validated region; fresh challenge DC still selects
login, preserving b9 behavior even if the challenge changes the DC. The UA uses
only a known DC, shared with the token between station clients. The existing
version/tenant are retained: no evidence establishes that changing the version
fixes this report. Every region/auth request omits any previous token. Region
redirects remain blocked; pre-inspection/login retain the existing one-hop,
same-operation HTTPS redirect protection and exact optional `times=1` marker.
Each login clears the previous token before proceeding. All requests retain
account pacing, TLS checking, JSON limits and server pauses. Region adds **one
request per login**, not per live poll.

Known server messages map to fixed `client_update_required`, `home_app_required`
and `rate_limited` categories without logging the text. Unknown rejections stay
`cloud_rejected`. The daily-login-limit response pauses the entire account.
Envelope `100` invalidates the shared token and raises an authentication error;
it never returns data as success and never automatically resends a write or
its interrupted command. The existing live-read path can reauthenticate once
and repeat its read; that bounded recovery is retained. Command result codes
remain separate from this envelope rule.

Authentication region, station region and data API/profile remain distinct.
The public mobile route configurations previously inspected map Home station
operations to neapi for DC0/1/4; moving all data operations to the auth host would
contradict that evidence. No arbitrary profile probe is added. A complete web
profile needs verified discovery, tree/identity mapping, station DC, totals and
live telemetry, plus explicit boundaries for controls. A successful web tree
alone cannot establish this. The existing missing-URI-only web fallback stays
bounded and is not extended to rejected calls or invalid addresses.

This candidate therefore **does not claim automatic Installer compatibility**
and **does not claim rupacheco's issue is fixed**. It addresses the hardcoded
initial-region limitation experimentally, fixes proven expiry handling, and
provides narrower diagnostics. Entity IDs, config-entry format and device
associations are unchanged.

## Minimum safe feedback

After one test with the candidate, report separately whether login, plant
selection and live readings succeed. If it fails, share only the fresh fixed
`Cloud request failed` and `Cloud setup failed` lines: stage, reason, numeric
HTTP/cloud status, type labels, known `auth_dc`/`auth_version` where present.
No passwords, account emails, identifiers, tokens, hashes, nonces, salts, raw
responses, HARs or complete URLs are needed.

If routing succeeds but pre-inspection is still rejected, the narrow remaining
hypothesis is client-profile/account permission mismatch (or another server
rejection), rather than the old fixed EU entry. To distinguish further without
sharing a raw capture, report locally observed facts only: whether the **same
account** signs in to Home as well as Installer, whether the same station and
current readings appear there, and which of the three known auth hosts the
successful official client's pre-inspection uses. Do not infer account region
from country/language. jacksontploong additionally needs his own request-level
station-validation warning and whether station selection was discovered/manual.

## Local validation

Final candidate: **874 HA tests and 134 subtests passed on each of HA 2026.10.4
and 2026.11.0**, using Python 3.14.8, the repository runner and the pinned
pytest-homeassistant-custom-component 0.13.375. HA 2026.11 has the existing
pytest import-rewrite warning; no test failed. **56 unittest tests passed**.
Python syntax, translation-key parity, local documentation links, release YAML,
the beta branch trigger and `git diff --check` passed. The 37-file ZIP was
checked against the working integration files, its b1 manifest and LICENSE.
No CI/HACS/Hassfest publication run or real-account test was performed.

Tests cover region0/1/4 and exact transport/headers, unsafe/missing/inconsistent
routing, fresh challenge DC overriding discovery DC, existing hash protocols,
bounded redirects, a rejected pre-inspection without a password login, rejected
station access after login, account pauses, shared session identity, envelope
expiry without operation replay and private diagnostic categories. Existing
tests retain the missing-URI-only fallback and setup/reauthentication behavior.

## Additional report

[Issue #34](issue-34-investigation.md) concerns work-mode/reserve settings and
recurring live-sample failures after a TOU change, rather than a demonstrated
login failure. It is tracked separately. The local beta adds a structural
parser-failure warning without changing accepted TOU data, fallback or writes.

## Installer follow-up — 2026-11-10

The reporter's new warning includes `auth_dc=0` and still rejects pre-inspection.
Thus Home-style region discovery completed, but changing its initial route did
not resolve this report. There is still no successful challenge or auth-version
evidence for this account. Static analysis of the actual Installer V3.14.0 APK
establishes a different `smc/ad/...` identity, a direct pre-inspection start,
app_type 2 routing and a different v1 calculation. This does not prove which
server condition caused the rejection. See
[the Installer protocol and local monitoring implementation](installer-app-protocol.md).
A separately selected experimental Installer profile is included in v0.6.1b3;
there is no automatic alternate-profile retry after rejection and no confirmed
fix at the reporter's account. Existing Home behavior remains the default.
