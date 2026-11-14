# Issue #54: authentication routing and client profile

Investigation only, 2026-11-14; no authentication/runtime behavior changed.
[Issue](https://github.com/Phil-0805/hoymiles-home-assistant/issues/54).
Baseline: v0.6.1.

## What the report establishes

The reporter says the integration worked the previous day, then failed with
`stage=login_region reason=invalid_auth_routing cloud_status=0 data_type=object`.
They confirm the official S-Miles Enduser app and the global website still work.
This does not establish a password error, rate limit, changed server routing or
the exact contents of the rejected response.

## Important distinction in the current code

`HoymilesHomeClient._async_login_unlocked` invokes Home's `region_c` only when
`supports_home_features` is true, which is set from `profile == "home"`.
The reported validation reason occurs exclusively in that branch, before the
password challenge or hash calculation. A successful response wrapper alone
does not satisfy the trusted-host/DC routing checks.

Enduser and Installer do not invoke `region_c`; they start at their documented
pre-inspection endpoint. In particular, Enduser uses its own `smo` identity,
session and app-type-3 route evidence. Existing regression tests verify its
actual mocked transport has pre-inspection/login only, no Home region request.
Missing `client_profile` in an old config entry intentionally defaults to Home.

Therefore, if the log belongs to the stated v0.6.1 code and the affected entry,
that request ran through the Home profile. The reporter's working app being
Enduser makes an account-profile mismatch the first thing to check. It does
not prove which profile they selected, whether they have another entry, or why
the previous day worked. The actual rejected routing fields remain unknown.

## Next useful reporter check

Confirm the account type selected for the affected integration entry. If unsure,
a fresh setup flow explicitly selecting **S-Miles Enduser (experimental, read
only)** can test authentication/discovery; it can be cancelled before creating
an entry, so no existing configuration needs to be deleted. Do not suggest
trying each profile or repeatedly submitting credentials. If their existing
entry already says Enduser, identify which entry produced the log and compare
the new fixed stage/reason line before making a routing change.

Do not request a password, token, raw region response, account address, full
station URL or unredacted config entry. A new diagnostic after successful setup
already includes only the allowlisted `client_profile` label for this question.

## Implementation boundary

No justification currently exists to relax trusted authentication hosts, guess
another DC, skip Home validation, auto-switch profiles or retry password/hash
algorithms. Enduser is already supported in v0.6.1; no beta is required merely
to select it. Any remaining failure needs to be classified from that explicit
profile's result. No fix success is claimed for the reporter.

Protocol references and source provenance are in
[enduser-app-protocol.md](enduser-app-protocol.md) and
[android-app-protocol.md](android-app-protocol.md). This investigation uses the
existing source-backed login paths and synthetic tests, not real account calls.
