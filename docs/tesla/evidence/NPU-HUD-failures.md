# C3 large HUD NPU indicator: failure cases before production edits

Target dev-sp-chipmunk, clean HEAD6226b05e8cfeb66d5ee6e26f3c178c2cb2b82066. Scope: only the large-screen sunnypilot HUD production file. No device operations or commits by worker.

- Green based on connection, toggle alone, cached history or previous-trip model output would claim phone inference that is not used. Green requires enabled + onroad + live/valid/current-trip modelV2 + big=true.
- Missing, invalid, stale, local fallback or disabled model selection must be grey immediately; grey→green→grey must work on the same renderer instance.
- Offroad must not show the indicator. A previous-trip frame cannot become green when a new trip begins.
- Icon must respect rect origin and bottom developer overlay offset; existing alerts must still render over the HUD. The C4/mici renderer must remain unchanged.
- Asset must be reused with tint, and tests must verify actual output pixels, not only a helper returning a colour.

E2E written before production edits: tools/sp_tesla_e2e/npu_hud_e2e.py renders the complete native HudRendererSP with synthetic message state into a2160x1080 logical texture, measures green/grey pixels in the expected icon rectangle, and captures each state. It uses the same HUD instance throughout, includes developer modes/shifted rect/full critical alert, and verifies C4 source remains byte-identical. Artifacts go outside source to /Users/mile/work/tesla-port/npu-hud-20261010. Synthetic messaging is not live phone/device inference proof.

## Local validation result

Before production edits, full native HUD E2E completed13 cases:11 required-icon cases failed, while offroad-hidden and alert-covered states passed. After the8-line production addition, all13 cases pass. Every green/grey state has10,147 exact expected-colour pixels inside the144x106 icon bounds; the other colour count is0. Grey→green→grey uses one continuous HudRendererSP instance, so no history window can mask local fallback. Full critical alert produces0 original icon-colour pixels and15,264 red pixels in the same area. C4 source is byte-identical to HEAD.

Screenshots for phone/local fallback/developer-bottom/full alert were visually reviewed. Normal icon is at rect.x+30 and rect.bottom-106-60; bottom developer mode moves it upward another60px. The existing augmented-road render order is unchanged: full HUD first, then AlertRendererSP. Reuses the existing144x106 white NPU asset with COLORS.ENGAGED or COLORS.GREY tint; no generated assets or new dependencies.

Production file SHA256: `8752dcc79408cdf69e8d2ac2ce716d7a2b2ec5841a4538468fc0489f6acf92ad`.

Reproduction (existing Python environment; runtime checkout root on PYTHONPATH):

```bash
export PYTHONPATH=$PWD:$PWD/opendbc_repo:$PWD/msgq_repo:$PWD/rednose_repo:$PWD/tinygrad_repo
python tools/sp_tesla_e2e/npu_hud_e2e.py --output /Users/mile/work/tesla-port/npu-hud-20261010/after.json
```

The E2E resolves runtime source via openpilot.common.basedir.BASEDIR, so it may be copied outside the checkout for device-side execution. All local logs/JSON/PNGs are outside Git at `/Users/mile/work/tesla-port/npu-hud-20261010`. Syntax and diff whitespace checks pass. Worker performed no commit, push, or device access. Parent still needs actual device UI/phone-source verification; synthetic message/pixel checks do not prove live phone inference.
