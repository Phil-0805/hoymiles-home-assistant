# Consumer work modes (station action 83)

Source inspected on 29 October 2026: the publicly delivered Hoymiles [WorkModeDrawer bundle](https://static.hoymiles.com/cdncache/website/js/index-COaHho1l.js), referenced by [the plant detail bundle](https://static.hoymiles.com/cdncache/website/js/index-CZ5oZNvO.js). SHA-256 of the WorkModeDrawer bundle: `d932523a3183d7d24ad0ea26ae544eeaf63075b50189f3b5368974a9d0efd8f4`.

This is direct inspection of the manufacturer's web client, not an authenticated command capture or hardware test. No account credentials or battery writes were used during this investigation.

| App selection | Action-83 mode | Integration mode (existing IDs) |
| --- | --- | --- |
| Self-Consumption | 2 | 1 |
| TOU | 3 | 8 |

These IDs differ from the action-1013 BMS enum. Never substitute that enum for this protocol.

The web client reads action 83 using the station ID and polls the job result. It reads SOC limits from the response and TOU selection from `k_3`. The integration also retains the previously supported `k_2.soc_l/soc_h` layout and rejects conflicting SOC evidence.

Observed write forms (inside action 83's `data`, alongside `sid`):

- Self-consumption: `{mode: 2, soc_l, soc_h}`.
- Existing recommended TOU: `{mode: 3, data: {mode: 1}}`.
- Existing basic TOU: `{mode: 3, data: {mode: 2, data: {id, week}}}`; the saved plan is read from `k_3.k_2`.
- Existing advanced TOU: `{mode: 3, data: {mode: 3, id}}`; the saved plan ID is read from `k_3.k_3`.

Only a supported, complete TOU selection actually returned by the account is offered. Basic/advanced plan IDs must be positive; absent plans, defaults needing creation and newer TOU submodes 4/5 remain blocked. Switching does not call plan editing/deletion endpoints (such as configuration 502), invent schedules or expose a schedule editor.

Before a mode switch, read current settings once under the write lock and use the current saved target configuration, not the thirty-minute cache. After writing, require the original API method, readable settings, target mode and complete target configuration to match. No automatic repeat writes. All requests use the shared account budget and certificate-verified HTTPS with redirects disabled. Periodic polling remains unchanged.

The reserve-SOC control applies to the confirmed self-consumption settings only; TOU uses its own plan thresholds. A mode/schedule match confirms cloud readback, not that the battery physically charged/discharged. Real-device switching and comparison against the app remain required before stable publication.
