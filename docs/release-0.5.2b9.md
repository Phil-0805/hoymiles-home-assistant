# v0.5.2b9 — account-selected authentication server

This beta follows the issue #16 report that b8 reaches login but is rejected
with `auth_version=3`. The reporter supplied a redacted successful web
pre-inspection showing `v=3, dc=0, f=0, t=159`. The previously added v1/v2
compatibility does not explain that account's failure. Stable remains v0.5.1.

## Follow the account's DC when sending the login

B8 starts both pre-inspection and login on `euapi`. The official web client
selects the subsequent authentication server from `dc`; the Android app uses
that value to update its route configuration between the two operations.
The public Android route configuration independently confirms `dc=0` maps auth
operations to `neapi`, while `dc=1` maps them to `euapi`.

B9 keeps the existing initial pre-inspection request and selects the subsequent
login destination from the freshly returned, validated code:

- `dc=0`: `https://neapi.hoymiles.com`
- `dc=1`: `https://euapi.hoymiles.com`
- `dc=4`: `https://indapi.hoymiles.com`, as explicitly selected by the web client.

Missing, malformed or unknown codes stop before login. No alternate server is
tried after rejection. The integration adds no dynamic-configuration request
or additional login retry. The v3 hash, password bytes, nonce, telemetry routing
and polling frequency are unchanged.

All three exact auth hosts/paths are classified as public authentication calls,
so previous Authorization tokens remain omitted. The existing trusted HTTPS,
same-operation redirect restriction, one-hop limit, exact `times=1` query rule,
account budget and rate-limit handling remain in place. Authentication failure
logs may include only a known numeric `auth_dc`, alongside `auth_version`;
credentials, hashes, nonce, salt, tokens and raw responses remain excluded.

This fixes a source-proven mismatch matching the reporter's account metadata.
A successful login on that account is not yet confirmed. The DC value describes
account routing, not the user's country of residence. Source details and hashes
are in [the protocol notes](android-app-protocol.md).

## Testing this beta

1. Install **v0.5.2b9** through HACS and restart Home Assistant.
2. Retry the failed setup or reload the existing entry once. Do not delete
   existing entries or change the account password for this check.
3. Report whether login and live readings work. If it still fails, share only
   the new `hoymiles_home.cloud_logging` warning lines with stage, reason, cloud
   status, `auth_version` and `auth_dc` where present. Debug logging is unnecessary.

Do not share credentials, login hashes, challenge values, tokens, complete URLs
or raw responses. No device-control permissions are needed for this login fix.

## Validation

Local: **708 Home Assistant tests, 17 subtests and 35 unit tests passed**.
Tests cover exact account-selected destinations across v1/v2/v3, the reported
v3/DC0 combination, unchanged DC1 behavior, fresh account-region changes,
invalid/missing codes, old-token omission, bounded redirects, account-budget
usage, private logging and no retries to another host or algorithm. Python
syntax, translation key parity and whitespace checks passed. CI validates
HA 2026.10.4 and 2026.11.0, HACS and Hassfest before publication.

No real account or device was accessed by the agent. Private captures and vendor
sources are not included. Affected-account confirmation remains outstanding.
