# Battery charge limit (development)

The next development version adds a read-only charge-limit sensor and a
**Charge limit SOC** number entity. This is the upper charge threshold shown
alongside the lower discharge threshold in the S-Miles Home app.

The current release v0.5.2b1 does not include these entities yet.

The control is available only in Self-Consumption mode when the cloud explicitly
returns the upper threshold through the supported settings path. A missing field
stays unknown; the integration does not assume a 100% limit. TOU plan thresholds
and legacy fallback settings are not changed through this control.

Enable battery controls in the integration options to change the limit. Values
are whole percentages from 10 to 100, and cannot be below the freshly read lower
threshold. Each change reads current settings, preserves the other threshold,
sends one write and checks both thresholds by readback. A failed confirmation
does not repeat the write. Avoid changing the same settings in the app during
the operation.

No additional periodic polling or new cloud endpoints are required. Existing
entity identities are retained. The implementation is tested with synthetic
responses; device/app comparison of the new upper-limit control is still needed.
