# Shared Tesla settings / failure cases before implementation

- Mici choice values remain stale after an actual Params write; enum labels show raw numbers.
- Unknown/mixed tuning config throws during page entry or preset/adjust callback.
- C3 and mici use separate ranges/units and drift; legacy values must remain readable.
- Invalid config must not be overwritten by default display or a preset click.
- Planner selection during an active session must not change; live tuning behavior remains intentional.
- Retired Web validation controls remain exposed although no request writer exists.
- Official's brake/stop tuning approximations must be disclosed without silently deleting custom values.

E2E uses actual native UI constructors/callbacks and isolated Params, with real config parsing and saved values; no device or CAN output. C3/C4 layout render proofs remain separate from hardware qualification.


Implementation: `openpilot/selfdrive/ui/sunnypilot/tesla_settings.py` is the shared
UI-owned metadata and guarded tuning adapter. C3 and mici retain their native
widgets. Choices, range steps, units, enum display labels, setting titles and
11 tuning fields are shared. High threshold is 40..120/5; low threshold is
20..115/5 (the previous mici 115 option remains available); traffic range is
20..120/5; brightness is 0..100/1. Existing stored values remain readable.

Unknown or mixed tuning JSON is kept unchanged. Both pages show a recovery
message and disable preset/value writes; direct callbacks also reject saves.
They do not replace unreadable backend data with defaults for display. Valid
configurations still use the existing tuning module's independent profiles and
validation. Planner selection callbacks use the actual session gate; live tuning
is retained. Mici choice writes immediately refresh enum labels/units, and tuning
rows refresh after native preset or value callbacks.

The two ordinary Web validation controls were removed. The underlying controller,
Params and safety flags are owned by the separate control cleanup. Official's
registry tuning notice is shown in both layouts; a matching Chinese fallback
constant lives in UI source so the existing font glyph scan includes its text.
No backend parameter was removed or silently relabeled as an exact solver input.

Repeatable local E2E (from the repository root):

```sh
PYTHONPATH=. /Users/mile/Desktop/mo-op/.venv/bin/python tools/sp_tesla_e2e/tesla_settings_e2e.py
```

Evidence: `artifacts/tesla-implementation-20261005/settings-red-expanded.log`,
`settings-green.log`, and `settings.json`. The JSON hashes all changed UI code and
the harness. It records actual choice-page callbacks, C3 OptionControl writes,
C4 preset callbacks, unknown/mixed JSON recovery for all three backends, matching
ranges and active-session selection retention. The native Mac window is initialized;
rendered C3/C4 layout proof, physical hardware and road acceptance remain separate.

The obsolete isolated `test_tesla_settings_display_invalid_config_without_repairing_it`
was retired: it required a fabricated default display for unreadable config, which
conflicts with this explicit recovery policy. Its exact mixed-v1 JSON now runs through
both real UI constructors/callbacks for each backend in the native E2E, in addition to
unknown-version and invalid legacy-family cases. No replacement unit test was added.

C3's status is a native text row with an explicit invalid/approximate title and
expanded explanation, rather than an empty disabled button. Official comfort
brake and stop distance titles carry an approximation marker; valid non-Official
pages hide the status row. The real-control E2E checks titles, visibility,
expanded description and absence of an action capsule in invalid configuration.
