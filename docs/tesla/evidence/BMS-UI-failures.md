# BMS UI regression cases recorded before production edits

Target: clean dev-sp-chipmunk at 5c4868e1eb5aaac06b086bfb96d680f2afa1f1cf. Parent requested no commit or device access.

- Tesla settings pushes BmsLayout on the navigation stack, but the BMS widget has no back control: user becomes trapped.
- Chinese strings and non-ASCII missing-value/unit glyphs depend on unavailable fallback glyphs: garbled display. All BMS user-facing text must remain English under English and Chinese application locales.
- Adding navigation without reserving height can hide tabs/cards/footer or overlap the header; English labels can overflow at the normal2160x1080 canvas or the legacy1560x1030 panel size.
- Back must pop exactly one widget, reveal the same Tesla settings parent, invoke hide_event, release the CAN subscription, and clear cached vehicle data. Reopening must establish a fresh subscription.
- Unsupported/unknown cars must remain unsubscribed. BMS remains receive-only; no publisher or UDS requests may be introduced.

E2E (written before production changes): tools/sp_tesla_e2e/bms_ui_e2e.py opens through the actual Tesla settings entry, renders every BMS tab with representative synthetic values, captures flushed logical-canvas PNGs, checks all captured labels for ASCII, verifies English across locales, validates text bounds at both panel dimensions, and invokes the normal Back callback to verify stack/lifecycle cleanup. Existing tesla_display_e2e remains the passive CAN/parser/staleness regression. These are local native UI checks, not device or road proof.

## Local result and reproduction

Before production edits, the native E2E failed with7 findings: non-English/glyph-dependent labels on each of three tabs under both application locales, plus the missing Back control. After the fix, the same entry opens BMS, all three tabs remain English in en-US and zh-CHS, and measured text stays within both2160x1080 and1560x1030 bounds. Native Back pops exactly one page, releases the subscription, and clears vehicle data. Reopening obtains a new subscription; unknown and Toyota CP remain unsubscribed. All three final tab screenshots were visually reviewed. Existing passive/display E2E:14 in-scope checks passed; its3 pre-existing out-of-scope home/localization exclusions remain unchanged.

Production scope: only `openpilot/selfdrive/ui/sunnypilot/layouts/settings/bms.py` (+37/-35). Reuses NavButton and pop_widget, reserves navigation height, converts BMS labels/units/placeholders to ASCII English, and uses the application's ordinary text drawing/measurement APIs consistently. No parser, battery calculation, CAN sender, parent settings entry, or shared renderer changes. `measure_text_cached` already applies FONT_SCALE; the removed mismatch was ASCII-only drawing bypassing the locale font selected during measurement.

From the repository root, with the existing project Python environment:

```bash
export PYTHONPATH=$PWD:$PWD/opendbc_repo:$PWD/msgq_repo:$PWD/rednose_repo:$PWD/tinygrad_repo
python tools/sp_tesla_e2e/bms_ui_e2e.py --output /Users/mile/work/tesla-port/phone-onroad-20261010-5min/bms-local/after.json
python tools/sp_tesla_e2e/tesla_display_e2e.py --output /Users/mile/work/tesla-port/phone-onroad-20261010-5min/bms-local/passive-display.json
```

All run logs/JSON/PNG artifacts are outside the source repository under `/Users/mile/work/tesla-port/phone-onroad-20261010-5min/bms-local/`. Source SHA256 for bms.py: `d474c89ef1c8480203c382c52d5f5f80e9cb3ac92ff183f010e3bbf0bbe57732`. Syntax and git diff whitespace checks pass. No local commit, push, or device access performed by the worker.

Device follow-up after the separately required phone baseline: open Tesla→BMS, inspect each English tab on the actual display, tap Back and reopen repeatedly, and confirm live CAN data becomes stale/clears normally when the vehicle stream stops. Local synthetic E2E does not establish physical touchscreen/display or vehicle data acceptance.
