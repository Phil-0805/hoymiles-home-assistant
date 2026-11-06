# v0.5.2b7 — observed login redirect and Never light/display timers

This beta fixes a concrete login redirect incompatibility found while
investigating issue #16, and supports the app's Never timeout for light/display
settings. Confirmation on the affected reporters' devices/accounts is still
needed. Stable remains v0.5.1.

## Login redirect with `times=1`

A successful login captured by the maintainer in Hoymiles' official web portal
shows HTTP 307 from the pre-inspection endpoint on `neapi` to the same endpoint
on `euapi`, with `?times=1` appended, followed by HTTP 200. B6 rejected that target
because it rejected every nonempty query string.

B7 accepts exactly the raw query `times=1`, in addition to an empty query, for
the existing bounded auth redirect handling. It does not add the parameter to
requests itself. The target still has to use the same auth operation path on
the explicitly allowed production HTTPS hosts, with no credentials, fragment
or alternate port. Extra parameters, duplicate or encoded parameters and other
values remain blocked. Only one redirect is followed; POST and its JSON body
are preserved, old Authorization tokens are omitted, and each request uses the
existing shared account budget and rate-limit handling. Other API redirects
remain blocked.

The observed routing may reflect a Hoymiles server-side change, but its
introduction date is unknown. The capture came from the maintainer's account;
it does not prove that every reporter receives the same redirect. This is a
targeted fix for an observed incompatibility, not a claim that all login errors
are resolved. The APK's redirect interceptor and call chain were checked again;
source details are in [the protocol notes](android-app-protocol.md).

## Light/display Never timeout

The Android app uses `65535` for Never in both strip (`slot`) and display (`sot`)
off timers. B6 rejected the entire settings record when that value was present,
which could make otherwise valid brightness/color settings unavailable.

B7 accepts this exact sentinel for both timer fields, including app-style integer
strings in cloud responses. Other ranges stay unchanged. New display and strip
off-delay selects offer 1 minute, 5 minutes, 15 minutes, 1 hour and Never. Existing
seconds-number entity IDs remain unchanged. At Never, those numbers become
unavailable rather than displaying 65535 seconds; they return when a regular
duration is selected. Existing custom seconds values remain visible as Custom
in the selects and are preserved.

Device-control permission is still required. Writes retain the existing lock,
fresh settings read, preservation of unrelated values, target/permission checks
and complete readback without automatic repeat writes. No faster polling or
additional control permission is introduced.

## Testing this beta

1. Install **v0.5.2b7** through HACS and restart Home Assistant.
2. Retry the failing setup or reload the existing entry once. Do not delete
   existing entries; the login fix needs no device/battery-control permission.
3. Report whether login and live readings work. If login still fails, share only
   the new warning lines from `hoymiles_home.cloud_logging`, including stage,
   reason, HTTP status and redirect policy. Debug logging is unnecessary.
4. For light/display, check brightness availability with either timer at Never
   and compare the timer presets with the official app if device controls are
   already enabled. Confirmation on the originally affected setup is pending.

Do not share passwords, tokens, full redirect URLs, raw cloud responses or
unredacted diagnostics. No screenshots, APKs, decompiled sources or private
account data are included in this release.

## Validation

Local: **578 Home Assistant tests and 35 unit tests passed**, including the
complete redirected login with the observed marker, rejection of unsafe targets
and query variants, one-hop enforcement, rate-limit handling, token omission,
log privacy, Never parsing and timer write/readback behavior. Python syntax,
translation key parity and whitespace checks passed. Release CI validates
Home Assistant 2026.10.4 and 2026.11.0, HACS and Hassfest before publication.
Real affected-account login and light/display device confirmation remain pending.
