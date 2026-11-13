# Station validation failure investigation — 2026-11-08

Research only: no runtime changes, account logins, device commands, issue
comments, commits or publication were performed.

Historical investigation snapshot from 2026-11-08. Statements about the current
implementation below refer to that date; the subsequent expiry/routing changes
are described in [the v0.6.1 investigation](login-routing-0.6.1.md).

## Report and scope

- [Issue #27](https://github.com/Phil-0805/hoymiles-home-assistant/issues/27)
  was opened by rupacheco. The detailed v0.6.0 / HA Core 2026.11.0 report is
  **jacksontploong's comment**, not the original author's diagnostic evidence:
  [reported warning](https://github.com/Phil-0805/hoymiles-home-assistant/issues/27#issuecomment-6718568302).
- The supplied warning is `Cloud setup failed: stage=station_validation
  reason=cloud_rejected`. The corresponding request-level warning, numeric
  cloud status and response shape were not supplied.
- [Issue #16](https://github.com/Phil-0805/hoymiles-home-assistant/issues/16)
  contains several different failures. gillesBdl confirmed the DC0 login fix
  and matching, stable readings. ElchCarlo confirmed login and matching readings,
  then reported one installation stale in both HA and the official app. Those
  observations do not identify the cause of the newer #27 validation failure.
- Latest release checked through GitHub: v0.6.0, stable, target
  `fdb120f34fc9f5ef8ba1e25321a02ba756d738b7`; local main matches that commit.

## What the warning establishes

`config_flow._async_finish()` has reached `async_device_tree(station_id)`.
An initial login has already returned a usable token. The selected or manually
entered station is then checked with:

```text
POST https://neapi.hoymiles.com/pvmc/api/0/station/select_device_c
body: {sid: station_id}
```

`_unwrap()` rejected the response envelope with the fixed reason
`cloud_rejected`. This is not the code path for a bare timeout, HTTP 403/429,
blocked redirect, empty successful device list, or malformed JSON. It can also
result from an absent/unrecognised envelope status; the quoted line alone does
not even establish a specific numeric cloud status.

It does **not** establish that station discovery succeeded. Discovery can fail
or return no stations and the flow still permits manual station-ID entry.
Nor does the earlier token establish that it remains valid or authorizes this
particular station/API operation.

## Rechecked manufacturer sources

The currently linked web entry and core JavaScript were downloaded again on
2026-11-08, following the entry's actual script link. They are byte-identical
to the 2026-11-06 archives:

| Source | SHA-256 |
| --- | --- |
| `https://global.hoymiles.com/website` | `76328c3b1e03e0a86e30d08fc91b5691262ac17812f275d9a1184ce50a9786eb` |
| `https://static.hoymiles.com/cdncache/website/js/index-BTRAEMTt.js` | `093c693196cf7966d1565ee7cca170d65f7de28ba5d9078f911ec9e164b64164` |

The APK-proven public configuration operation was read without credentials or
token: POST `https://euapi.hoymiles.com/dict/pub/0/dyn/uri_s`, with
`{app_type:1,h:"-1",dc:1}`. Its response is also unchanged:
SHA-256 `dd8c03a30936c3a4890c1e2faa1d1d1cd6d6a5082c6870c0a4f7ddd4014ece32`.
It maps `PVMC_STATION_SELECT_DEVICE_C`, `PVMC_STATION_SELECT_BY_PAGE_C` and
`PVMC_STATION_GET_SD_URI_C` to domain id 0, `neapi.hoymiles.com`.
Archived DC0 and DC4 configurations have the same station-route mapping.
There is no basis here to move all data requests to the authentication host.

The existing V2.13.0 Android archive was rechecked statically; both archive
hashes still match [the provenance record](android-app-protocol.md).
This is the previously downloaded third-party-mirror APK, not a newly obtained
or independently signature-verified current APK.

- `MainHomeSystemFragment.j0()` lists stations using
  `PVMC_STATION_SELECT_BY_PAGE_C` and `{page:1,page_size:50}`.
- `JgSystemListPageBean` uses a top-level `sid`; device `id` is nested under
  `devices`. The integration prefers `sid` and does not substitute nested IDs.
- `JgMicroinverterNetStatusActivity.f0()` calls
  `PVMC_STATION_SELECT_DEVICE_C` with precisely `{sid}`. `ScanDeviceActivity`
  independently uses the same operation.
- `EasyRequest` → `HttpUtils.h` → `HttpUrlManager.a` resolves the operation
  through `DomainManager`. Station-AK/DC special handling is restricted to
  `PVM_EXT_STATION_AK_FIND` and `PVM_EXT_STATION_AK_UPDATE`; it is not used for
  this device-tree call. No evidence supports adding an AK or guessed body field.
- The Home app explicitly has DTU-owner views as well as Wi-Fi-microinverter
  and battery views. A DTU or non-WB inverter model alone does not prove that
  Home API access is unsupported.

The web client uses a different family: `plant.getList()` calls
`/pvm/api/0/station/select_by_page`; `plant.getDeviceTree(id)` calls
`/pvm/api/0/station/select_device_of_tree` with `{id}`; the full tree operation
is `/pvm/api/0/station_v3/tree_g_a` with `{sid}`. The wrapper sends the token
as `authorization`. Successful portal login therefore does not demonstrate
permission for the mobile Home device-tree operation. This is a concrete
compatibility distinction, not proof of the reporter's account type or cause.

## Additional confirmed protocol defect: envelope status 100

The integration currently accepts envelope statuses `0` **and `100`** in
`_json()` / `_unwrap()`. Both inspected official clients disagree:

- Web `request()` accepts string status `0`; its error branch explicitly
  handles `data.status === "100"` by aborting outstanding requests and
  returning to login.
- Android `HttpUtils.AnonymousClass3.e()` intercepts status `100` and calls
  `AutoLoginUtil.n()`. That method obtains a fresh challenge/login and token;
  its success callback reissues the original request.
- Android `BaseDataResponse.isSuccess()` compares against the inlined
  `TlbConst.TYPELIB_MINOR_VERSION_SHELL`, whose actual value is `"0"`.

Synthetic calls against the current `_unwrap()` confirm that status `100`
with null data is accepted and returns `None`. Statuses `1` and `3` with a
neutral synthetic message instead raise `cloud_rejected`.

Consequences depend on the caller: station validation can misreport an expired
session as an empty/invalid station; discovery can report an unexpected list
shape. This is a real compatibility defect, but it does **not directly explain
the supplied #27 warning**, because status 100 bypasses that rejection path.
No response from the reporter establishes that status 100 occurred.

A subsequent fix should classify envelope 100 as authentication expiry,
invalidate the shared token, and test setup/reauthentication and runtime reads.
Do not copy the Android replay behavior indiscriminately: writes and settings
commands must not be automatically resent after an uncertain outcome.
This finding concerns the response **envelope**, not a command-poll result code.

## Remaining hypotheses and discriminating evidence

| Hypothesis | Evidence / next distinction |
| --- | --- |
| Wrong numeric ID entered manually | Possible because manual fallback is allowed. Ask whether the plant was selected from the discovered list or entered manually; compare locally with the plant-detail URL, without posting the ID. |
| Account/station permission or Home-versus-web API difference | Plausible because the reported successful portal uses different station endpoints. Ask whether the same account shows the same plant and live values in the actual S-Miles Home app, and whether access is owned, shared or installer-managed. |
| Expired/revoked session or concurrent-login policy | Not excluded, but neither the warning nor static source establishes it. Need the request-level fixed status/type labels; do not advise repeated logins or password changes without evidence. |
| Server-side request rejection or unexpected envelope | Not excluded. Need the missing `Cloud request failed` line for this operation. |
| Stale client User-Agent | APK constructs version/tenant/stored-user DC dynamically; integration fixes `sma/ad/2.12.1/159/0`. This is a known difference, but no evidence links it to this rejection. Do not claim a version bump or changed DC suffix fixes it. |
| Universal data-region routing error | Not supported by the rechecked public configuration: the mobile station operation remains on neapi. |
| Rate limit, HA 2026.11 regression, or old Argon2/DC-login mismatch | Not established by this warning. Its failure stage is after initial authentication; no rate-limit status is supplied. |

No fallback calls to alternative station endpoints were made on a real account.
Changing validation alone would also require checking discovery, target identity,
tree parsing and subsequent telemetry; accepting a web tree is not by itself a
complete compatibility fix.

## Minimal reporter follow-up (draft, not posted)

> Thanks for the log. This failure occurs while checking access to the selected
> plant after the initial login. Could you please share:
>
> 1. Was your plant offered in the integration's dropdown, or did you enter its
>    numeric station ID manually? If entered manually, please verify it against
>    the selected plant's detail-page URL; you do not need to post the ID.
> 2. Does this exact account show that same plant and current readings in the
>    **S-Miles Home mobile app**, as well as the website? Is it your own plant,
>    shared access, or an installer-managed account? Which inverter/DTU model?
> 3. Please check the same logger for the accompanying **Cloud request failed**
>    warning with `stage=station_validation`. It should include `cloud_status`
>    and `data_type`. The quoted **Cloud setup failed** line omits those details.
>
> Please share only those diagnostic warning lines. No passwords, tokens,
> serial numbers, complete API responses or HAR exports are needed.

## Cross-checks and validation

- The Node-RED reference still has head
  `e48ac860e2d1d17fdad108be4dfe306e511608e2`; no newer implementation was found.
- Supplemental reference: Philra94/homeassistant-hoymiles-cloud at
  `ff91ca7c36ef7b4cbabca18cb37a7ed123387eaf` also uses the web station/list and
  per-device API family. Its implementation does not prove the affected Home
  account can use those operations.
- Existing targeted tests: **123 passed** using `scripts/run_ha_tests.py` with
  HA 2026.11.0 / pytest-homeassistant-custom-component 0.13.375:
  `test_config_flow.py`, `test_stations.py`, `test_cloud_logging.py`,
  `test_auth_protocols.py`. One existing pytest import-rewrite warning.
- Synthetic `_unwrap()` probes used only invented statuses and neutral text.
  They demonstrate current code behavior, not the reporter's server response.

Only this protocol summary belongs in the repository. Manufacturer bundles,
APK/decompilation and raw public configuration archives remain outside it.
