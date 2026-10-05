# Tesla display fixes: failure cases and E2E acceptance

Before changing the UI, the repeatable `tools/sp_tesla_e2e/tesla_display_e2e.py` flow must reproduce these failures through the real renderer and BMS widget boundaries, with UI language and `CarParamsPersistent` supplied through the process's isolated `Params` store:

1. **Ordinary alert localization:** with `LanguageSetting=zh-CHS`, a `selfdriveState` alert whose text is `Camera Malfunction` must produce `相机故障` from both C3 and Mici `AlertRenderer.get_alert()`. `alertSize`, `alertStatus`, Mici `alertHudVisual`, and `alertType` must survive unchanged.
2. **Late vehicle parameters:** opening the BMS page with no `CarParamsPersistent` must not subscribe. Writing Tesla Model 3 parameters while the page stays open must make its next UI state update create one passive `can` subscription.
3. **Vehicle support changes:** changing the live parameters from Tesla Model 3 to another supported Tesla fingerprint keeps one subscription and clears readings from the previous car; changing to a non-Tesla car releases the subscription and clears readings.
4. **Visibility boundary:** with the page hidden, even a later supported Tesla `CarParamsPersistent` update must not create a subscription. Reopening may subscribe based on the latest parameters. Hiding releases the subscription.

The harness uses the actual `BmsLayout`, both renderers, actual `UIState.update_params()`, and an isolated Params prefix. It replaces only the CAN socket factory with a passive in-memory socket, so it exercises no vehicle hardware and cannot transmit CAN. Its JSON output is the repeatable acceptance artifact.
