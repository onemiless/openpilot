# Tesla audit implementation: scope and release boundary

This implements the audit against parent91a9dacb0c and opendbc e15d18898f.
Failure modes and integration checks were defined before implementation; no new
post-implementation unit tests were added. Obsolete fixtures/contracts were
retired or maintained, and existing regression suites were run separately.

## Implemented

- Traffic green release respects forceDecel and unknown/unhealthy controlsState.
- Actual ACC FAULT remains an event and cancels ownership/output even with stale
  active commands. Standard carOutput fields no longer contain steering debug.
- Tesla yaw for ARS408 is explicitly VehicleModel-estimated from steering/speed,
  including reverse; it is not presented as a measured yaw sensor.
- Retired attachment TX permissions and Web validation consumers are removed;
  critical RX/AEB/normal control, automatic speed wheel and blindspot lamp paths
  remain. Old Params/schema slots remain tombstones for compatibility.
- Parent owns Params reads and delivers explicit startup config; opendbc no
  longer imports openpilot Params. Pure visualization parser/provider is retired.
- Backend selection is atomic, and manager joins old consumers before clearing
  the completed session. Other brands do not inherit Tesla custom backend state.
- Experimental/TN share a legacy planner; its solver ABI/constants no longer
  inherit silently from Official MPC. TN NoDEC/AccelController/stopping policy
  remain distinct. Official nondefault brake/stop approximations are disclosed,
  not silently removed or claimed numerically equivalent.
- C3/C4 share Tesla setting metadata and invalid-config guards. C4 labels refresh;
  invalid saved data remains untouched, numeric controls hidden/disabled as
  appropriate. Runtime alert localization is wired, BMS handles late CarParams.
- Tesla PCM speed-limit step policy moved out of generic constants; its mapping
  and other-brand behavior remain identical. It is distinct from DynamicAutoStock.

## Validation and limits

See TESLA_CONTROL_FIXES.md, TESLA_PLANNER_FIXES.md, TESLA_SETTINGS_FIXES.md,
TESLA_DISPLAY_FIXES.md, and TESLA_SPEED_LIMIT_POLICY.md for repeat commands.
Evidence receipts live under artifacts/sp-tesla-migration and
artifacts/tesla-implementation-20261005.

The primary and fallback legacy solver were generated/compiled/linked on Darwin
arm64 with SCons cache disabled. Matched replay covers18 configurations ×236
cycles (4248) and compares final outputs/trajectories exactly; DEC/Vision SCC/Map
SCC/SLA transition modes were disabled in that replay, so it is not exhaustive
feature-interaction proof. Existing tests and source-order review supplement it.
Actual planner-publication-LongControl, compiled host safety, real Params/UI
callbacks, multi-process startup and manager stop/clear boundaries are exercised.

No new upstream version was merged, no remote refs were published, and no device
was modified in this implementation. C3 target firmware/runtime build, stationary
installation checks, ARS408 physical mounting/sign validation, and onroad handoff
behavior remain release gates. Host safety is not flashed Panda firmware, and a
Darwin solver build is not a C3 binary.
