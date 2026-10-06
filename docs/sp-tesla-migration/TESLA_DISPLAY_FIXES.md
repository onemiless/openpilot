# Tesla display fixes: failure cases and E2E acceptance

Before changing the UI, the repeatable `tools/sp_tesla_e2e/tesla_display_e2e.py` flow must reproduce these failures through the real renderer and BMS widget boundaries, with UI language and `CarParamsPersistent` supplied through the process's isolated `Params` store:

1. **Ordinary alert localization:** with `LanguageSetting=zh-CHS`, a `selfdriveState` alert whose text is `Camera Malfunction` must produce `相机故障` from both C3 and Mici `AlertRenderer.get_alert()`. `alertSize`, `alertStatus`, Mici `alertHudVisual`, and `alertType` must survive unchanged.
2. **Late vehicle parameters:** opening the BMS page with no `CarParamsPersistent` must not subscribe. Writing Tesla Model 3 parameters while the page stays open must make its next UI state update create one passive `can` subscription.
3. **Vehicle support changes:** changing the live parameters from Tesla Model 3 to another supported Tesla fingerprint keeps one subscription and clears readings from the previous car; changing to a non-Tesla car releases the subscription and clears readings.
4. **Visibility boundary:** with the page hidden, even a later supported Tesla `CarParamsPersistent` update must not create a subscription. Reopening may subscribe based on the latest parameters. Hiding releases the subscription.
5. **BMS display jitter:** 100 Hz 0x132 voltage/current ripple (±5 V, ±20 A) must not reach the screen. Values are smoothed (1 s EMA) and the snapshot refreshes at 2 Hz; the last second may show at most 3 distinct 0.1 V voltages, and power is computed from the smoothed voltage and current.
6. **SOC matches the car screen:** 0x33A `UI_SOC` (48|7, Model3CAN.dbc) is shown as the primary SOC, with 0x292 `SOCUI292` as the note. A `UI_SOC` more than 10 % from the BMS value, or a missing BMS value, falls back to the BMS value.
7. **Consumption is shown:** average Wh/km over a 2 km distance-decayed window, using raw 0x132 power integrated at frame rate and `carState.vEgo`. It appears after 0.05 km and is not hidden at low speed. 20 kW at 72 km/h must read 250-305 Wh/km.
8. **Stale data:** 0x132 values older than 3 s clear.
9. **Home alerts:** offroad alerts no longer open the home ALERTS panel or show the alert count. `Offroad_ExcessiveActuation` stays, because `selfdrived` blocks engagement until its acknowledge button clears it.

The harness uses the actual `BmsLayout`, both renderers, actual `UIState.update_params()`, and an isolated Params prefix. It replaces only the CAN socket factory with a passive in-memory socket, so it exercises no vehicle hardware and cannot transmit CAN. Its JSON output is the repeatable acceptance artifact.
