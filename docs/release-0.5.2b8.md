# v0.5.2b8 — account-selected login protocols and output-power availability

This beta adds the legacy login protocols explicitly supported by Hoymiles'
Android app and web client, and fixes output-power settings that were rejected
when the saved value exceeded the current permitted maximum. Stable remains
v0.5.1. Confirmation on the affected login account and output-power device is
still needed.

## Follow the login version returned by Hoymiles

The issue #16 reporter now reaches the actual login request instead of failing
at the previous HTTP redirect. The cloud rejects authentication; this alone does
not prove incorrect credentials.

The official clients choose their password transformation from `v` in the
pre-inspection response. B7 always used the v3 Argon2id calculation, even if
Hoymiles selected v1 or v2. B8 supports the explicitly returned versions:

- **v1/v2:** the app/web client's MD5-hex and Base64 SHA-256 composite.
- **v3:** the existing Argon2id calculation, with unchanged parameters and UTF-8
  password bytes, outside the event loop.

This is protocol compatibility, not an algorithm fallback: after rejection the
integration does not retry another version. Missing, malformed or unsupported
versions stop before login. A missing legacy nonce is omitted as in the official
clients; v3 still requires a valid salt and nonce. The existing trusted HTTPS,
bounded redirect, token-omission and shared account-budget rules remain in place.

The error text now says that S-Miles Home rejected authentication rather than
asserting that the credentials are invalid. Failure logs add only a known
numeric `auth_version`; passwords, hashes, salt, nonce, tokens and raw responses
are excluded.

The maintainer's working account uses v3. The affected reporter's version is
unknown, so this fixes a verified compatibility gap without claiming that it
necessarily explains that account's rejection. Why Hoymiles assigns different
versions, and when that behavior changed, has not been established. See the
[APK and web source notes](android-app-protocol.md).

## Output-power settings outside their current write range

The maintainer's web read showed an empty phase list and `power=2000` alongside
`max_power=800`. B7 rejected the entire record because the saved value exceeded
the current write maximum, making the control unavailable.

B8 preserves the actual stored value and the explicit maximum separately. In
this example the control can show the saved 2000 W and permit a new setting of
100–800 W. It neither silently changes the reading to 800 W nor authorizes a
2000 W write. The saved value does not establish actual physical output.
Stored values below 100 W are also readable; new total settings still start at
100 W. Missing maxima never become an assumed device capability.

Known numeric response strings and station command status codes are normalized
as in the app. Invalid representations remain rejected. For phase-controlled
stations, the 1532 read now sends only `{sid}`, matching both official clients;
`type=0` remains exclusive to output writes. A phase value above its own limit
can be read but blocks a write that would resend that invalid counterpart.

Fresh reads under the existing lock, permission/controller checks, current-limit
validation, full readback and no automatic repeat writes remain mandatory.
Configuration 515, polling frequency and control permissions are unchanged.
Diagnostics add fixed output-error reasons and known field types only. Details:
[output-power protocol notes](output-power-settings.md).

## Testing this beta

1. Install **v0.5.2b8** through HACS and restart Home Assistant.
2. Retry the failed setup or reload the existing integration once; do not delete
   existing entries. No control permission is needed for the login fix.
3. Report whether login and live readings work. If authentication still fails,
   share only the new `hoymiles_home.cloud_logging` warning lines, including
   stage, reason, cloud status and `auth_version` when present. Debug logging
   is unnecessary; do not post passwords, hashes, challenges, tokens or URLs.
4. If battery controls are already enabled, refresh the battery settings and
   check the output-power number. Compare its stored value and maximum with the
   app before making an intended change within that maximum. A high stored value
   does not raise the permitted new value. Device confirmation is pending.

## Validation

Local: **673 Home Assistant tests, 17 subtests and 35 unit tests passed**.
Coverage includes independent Node-crypto legacy vectors, unchanged v3 worker
parameters, explicit version selection without fallback, full login through the
bounded redirect, log privacy, the observed 2000/800 output record, permitted
lowering and blocked over-limit writes, phase payloads, numeric-string polling,
fresh limits, permission/target changes and complete readback. Python syntax,
translation key parity and whitespace checks passed. CI validates both
HA 2026.10.4 and 2026.11.0, HACS and Hassfest before publication.

No real account or device was accessed by the agent. Private captures and vendor
sources are not included. Affected-account login and output-control device
confirmation remain outstanding.
