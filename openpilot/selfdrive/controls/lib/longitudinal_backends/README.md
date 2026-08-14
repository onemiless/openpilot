# Longitudinal backends

The registry is the single source of truth for stable backend IDs, capability
declarations, parameter layers, apply lifecycle, and isolated solver contracts.

- `0`: SP Upstream Tunable. Its planner is kept in
  `longitudinal_planner_official.py`; runtime solver extensions live in
  `long_mpc_official.py` and do not modify the generic Local solver.
- `1`: Local. Existing lead-focused behavior and solver remain isolated.
- `2`: TN-NoDEC. TN planner/acceleration-controller code and the `long_tn`
solver are vendored under this package. DEC is deliberately unsupported.
The exact source provenance is recorded in `UPSTREAM_LOCK.json`.

`LongitudinalPlannerMode` is only the desired selection. At the start of an
onroad session it is copied to `ActiveLongitudinalBackend`; both `plannerd` and
`controlsd` use the latched value after process restarts. The planner publishes
its actual backend ID and controlsd refuses longitudinal actuation on mismatch.

Runtime tuning is stored in one versioned `LongitudinalTuningConfig` JSON
snapshot. Legacy Params remain writable for rollback/migration, but the final
JSON write is the authoritative atomic revision. Invalid revisions retain the
last known good values. HOT_RAMPED parameters move at the rates declared by the
registry; backend-native HOT values apply directly.

## Updating SP upstream

Fetch the desired SP ref, then run:

```sh
python3 tools/longitudinal_backend_sync.py --ref sunnypilot/dev-c3
python3 tools/longitudinal_backend_sync.py --ref sunnypilot/dev-c3 --diff
```

Review the upstream planner changes first, then reapply only the adapter-owned
imports, tuning reader, session telemetry, and eight-parameter solver contract.
Regenerate `long_official`, verify JSON `np == 8`, build its shared library, and
run the longitudinal backend tests. The tool is intentionally read-only; it
does not merge, overwrite, or silently accept upstream changes.
