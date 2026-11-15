# v0.6.2b2 — restore the normal Home login entry

This beta addresses the new Home login prerequisite implicated by issue #54.
Stable remains **v0.6.1**. The six-input HMT monitoring change from b1 is retained.

## Changes from b1

- Start normal Home authentication directly at the established pre-inspection
  endpoint, removing the mandatory `region_c` request introduced in v0.6.1.
- Continue selecting the login server from the fresh, validated challenge DC.
  Keep explicit server-selected hash versions, challenge/nonce checks, token
  omission, strict authentication redirects, TLS and account pacing/pauses.
- Preserve v0.6.1 session-expiry handling and bounded Live-read reauthentication.
  No automatic alternate-profile/host/hash attempts or write retries are added.

Installer and Enduser authentication, Live/data routing, polling intervals,
entity identities and control permissions are unchanged. History sampling and
automatic history deletion remain unimplemented.

## Why this change

The reporter confirms v0.6.0 works again while v0.6.1 fails at
`login_region/invalid_auth_routing`. The normal Home Android login starts with
pre-inspection; the additional region operation is evidenced in a distinct OEM
login path. Making it compulsory for every Home login added an unnecessary
dependency. The current public web entry also has no `region_c` call.

This identifies a source-backed regression candidate, not the exact rejected
fields from the reporter's region response. Their earlier `missing_uri` log
under v0.6.0 concerns a separate, later data-access stage whose cause is unknown.
The actual outcome of b2 still needs confirmation on their account.

## Test for issue #54

1. Update to **v0.6.2b2** through HACS with beta versions enabled, then restart
   Home Assistant Core.
2. Keep the original **Home-profile entry** that worked under v0.6.0. Do not
   delete/recreate it or change its profile for this comparison.
3. Check whether setup completes and the original inverter/module entities
   resume updating. Module chart values follow their existing five-minute cycle.
4. If it still fails, share the new fixed `stage`/`reason` warning lines. A
   `missing_uri` result means a different stage from the removed region step.
   Do not share credentials, tokens, identifiers or raw API responses.

If only the separately created Enduser entry remains, report that first: Enduser
is still experimental station-only monitoring and does not provide individual
module-chart entities. This beta does not change that scope.

## Validation

Local validation: **1,267 HA tests on HA 2026.11.0** and **56 unit tests** passed,
plus Python syntax, translation-key parity, documentation links, whitespace and
deterministic 39-file HACS ZIP checks. Existing pytest anyio assertion-rewrite
warning only. Required CI covers HA 2026.10.4/2026.11.0, HACS and Hassfest.

Tests cover direct Home entry, DC0/1/4 login selection, stale-token/DC clearing,
explicit hash versions and malformed challenges, trusted one-hop redirects,
rejection/rate/transport handling, shared sessions and expiry without write
replay. Installer/Enduser regressions and HMT monitoring remain in the suite.
No real accounts or devices were accessed by the agent.

[Investigation and source provenance](https://github.com/Phil-0805/hoymiles-home-assistant/blob/v0.6.2b2/docs/issue-54-auth-profile-investigation.md).
