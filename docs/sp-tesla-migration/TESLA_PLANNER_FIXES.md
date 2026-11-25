# Tesla planner fixes: failure modes and acceptance

Source before implementation: `dev-sp@91a9dacb0cdd29372d0742f79d1ec3a95bbc6332`.
This work is offline. Device and road acceptance remain pending.

The following failure modes and E2E checks are defined before product edits:

1. F01: same-event green can replace a forced braking/stop plan with positive
   acceleration. Run all three actual planners/solvers, publish through the
   traffic sink, and consume the published fields in actual LongControl.
   `forceDecel` (driver no-response or soft disabling), missing controlsState,
   invalid/unseen/dead controlsState must veto GO. A healthy normal green must
   still clear model-only stop residue. Driver gas/brake and physical lead
   blocking must remain effective. Record base/final target, shouldStop, GO
   reason, and actual LongControl output in JSON.
2. F06: two processes can select different session backends during startup.
   Use actual typed Params in one temporary directory and two spawned OS
   processes. Pause A after it reads desired=Official, change desired=TN, start
   B, then release A. Both must return Official, with Active=Official. Restart
   a consumer and change Desired again: Active remains session-latched.
3. F07: Official obstacle translation cannot reproduce an eight-parameter OCP
   exactly when comfort_brake changes. Keep all three tuning profiles and
   values. Expose metadata for UI that marks Official comfort_brake and
   stop_distance as obstacle translations; default values remain unchanged.
   Record the seed20/predicted10/lead10/B3 mathematical 10 m residual.
4. Structural changes: the retained legacy MPC must not silently inherit new
   upstream N/time-grid/cost/lead propagation. Freeze its numerical contract;
   merge Experimental/TN common planner flow without changing ACC/E2E,
   NoDEC, AccelController, stop policy, tuning or recovery behavior. Before
   editing, capture actual process-replay outputs for all three backends,
   default/CrazyMAX/custom profiles and ACC/E2E. Repeat with identical inputs
   afterward and compare all published control/trajectory/discrete fields.
   Preserve input SHA and baseline/result artifact SHA. The minimized route
   includes inactive and active input frames; its limited replay slice is
   evidence of numerical preservation, not road validation.
5. Construction: Experimental may crash if its first frame is already
   engaged because a_desired is only initialized by an inactive reset. Run a
   first-frame-engaged actual solver/publish/control cycle before the shared
   constructor extraction; initialize a_desired from init_a in the new owner.
6. Scope: persisted Tesla custom-backend/tuning Params must not select legacy
   planners, custom tuning, or TN stopping policy after switching to another
   brand. Before adding the brand gate, exercise actual factories with a
   non-Tesla CP and desired Experimental/TN plus saved CrazyMAX profiles.
   Other brands must construct Official/ordinary LongControl and never latch
   the Tesla session Param.
7. Independent review found the consumer lock alone does not complete F06:
   manager clears OFFROAD Params before ensure_running requests nonblocking
   stop. A startup consumer can write its old Active afterward. Before repair,
   run actual manager_thread with synthetic deviceState ONROAD/OFFROAD transport,
   real spawned plannerd/controlsd latch workers and typed Params. Pause after
   desired0, change desired2, request offroad, then allow a delayed old write.
   Also exercise a worker ignoring graceful stop. Require old process joined or
   killed before session clear; Active absent offroad; next session selects2.

No implementation-following unit tests are added. Existing tests may be run;
new evidence uses `tools/sp_tesla_e2e/tesla_planner_chain_e2e.py`.

## Implemented boundaries

- The shared GO admission rejects `forceDecel` and missing, invalid, unseen or
  dead controlsState using the existing unsafeBasePlan reason 3. Normal healthy
  OEM green still overrides a model-only stop residue. STOP observation and
  final arbitration remain separate, and all three Tesla providers use the
  same final publisher sink.
- Session selection uses an OS file lock around both reads and the durable
  typed ActiveLongitudinalBackend write. Desired changes cannot split planner
  and LongControl selection while they initialize concurrently. The original
  OFFROAD clear-before-stop ordering was not sufficient: a delayed old consumer
  could rebuild Active after it was cleared. Manager now calls
  end_longitudinal_session before its OFFROAD clear: request both consumers to
  stop, wait for both through actual ManagerProcess.stop(block=True), then
  remove Active under the same file lock. It never holds the lock while joining
  a writer. A refused graceful stop uses the existing five-second SIGKILL path.
  No ONROAD flag was added: old writers are gone before the session is cleared,
  so they cannot repopulate it during a rapid next-session transition.
- Official keeps every tuning value. Registry metadata
  `approximate_tuning_fields` and `tuning_notice` expose its translation limits
  to settings. With seed20/predicted10/lead10 and brake3 instead of2.5,
  translated cost gap differs by 10 m. A stop_distance translation matches the
  distance cost but does not simultaneously preserve a scaled danger-zone
  constraint; it is also labelled approximate. Default values still match the
  current Official constants exactly.
- Non-Tesla factories return Official and ordinary LongControl without reading
  or latching Tesla backend selection and without custom runtime tuning.
- One legacy planner owns coast/turn/reset/throttle/SLA/MPC/output/publish.
  TN retains NoDEC, radar freshness, AccelController/Pace, accel seed, shouldStop
  policy and TN stopping policy; Experimental retains current upstream DEC.
  The shared constructor initializes a_desired even if the first input is
  already engaged.
- `legacy_mpc/contract.py` freezes the generated solver's N=12, 10 s grid,
  dimensions, cost constants, internal accel bounds and lead math/tau. Legacy
  no longer inherits Official MPC. Its SConscript depends on the pinned local
  contract rather than Official solver.so/model grid. Publication still uses
  the current CONTROL_N/model time interface; an upstream publication-grid
  change requires a new matched replay.
- Removed unused Official max_accel_override, mpc_factory, _update_mpc and MPC
  no-op hooks. Removed the uncalled experimental cruise_obstacle helper and
  retired only its isolated test. Existing test fixtures were synchronized to
  healthy controlsState/shared source ownership; no new unit test was written.

## Verified offline results

`artifacts/sp-tesla-migration/planner-validation-summary.json` records receipts
and SHA-256 for the inputs, outputs, source and the two cached solver modules.

| Check | Before | After |
|---|---|---|
| Actual planner/solver -> Capnp publisher -> selected LongControl | 15 force/health GO failures in 27 cases | 27/27 pass |
| Two spawned processes with real typed Params | 5/5 split selections (A=0, B=2) | 5/5 agree (A=B=Active=0), restart preserved |
| Actual manager ONROAD/OFFROAD boundary with delayed process writer | 3/3 clear-before-stop failures, next session stale0 | 3/3 clear only after exit/join or SIGKILL; next session selects desired2 |
| First input already engaged | Experimental AttributeError | 3/3 providers pass |
| Other brand with persisted Tesla selection/tuning | Experimental/TN selected | 2/2 Official/no custom policy/tuning |
| Actual plannerd process replay: 3 providers x 3 tuning profiles x ACC/E2E | 18 combinations, 236 cycles each | Frozen, merged and final each exactly match all 4248 cycles |
| Existing regression suite | Existing checks reused | 452 pass, 0 fail |
| Focused Ruff | — | Pass |
| Official real MPC constants and T_FOLLOW vs tuning defaults | — | Ten values match; receipt records drift differences |
| Darwin primary/fallback solver generation and native build | Existing cache used for the initial before/after comparison | SCons --cache-disable generated/compiled/linked both; rebuilt outputs exactly match baseline |

Replay comparisons cover aTarget, shouldStop, allowThrottle, source, speeds,
accels and jerks. Wall-clock solver/processing timings are deliberately not
compared. This matrix explicitly disables DEC, Vision/Map SCC and SpeedLimitMode;
their state transitions are not covered by this numerical replay evidence.
Source comparison preserved their shared update ordering; separate enabled
feature replay remains a future acceptance requirement. The route SHA is
`36e4a6e774d33839b2b9f78d9f90d14b132020fb1cb88511d1096c737b0747f4`.
It contains 174 longActive carControl input frames and speeds from -1.27 to
11.85 m/s; it does not cover an unrestricted onroad operating envelope.

The initial comparison used the existing generated solver cache. Root then
ran SCons with --cache-disable for both primary/fallback native solver targets
on this Darwin/arm64 host. The build log records actual generation, compilation
and linking, followed by `scons: done building targets.` The final 4248-cycle
matched replay, 27-case control chain, five concurrent-consumer checks, three
cold starts and two other-brand checks were rerun with these rebuilt modules.
The three manager session-transition checks were also rerun. Output equality
remains exact; no tolerances were weakened.
The affected existing MPC convergence/recovery checks were rerun after rebuild:
119 passed, 0 failed. The broader 452-case existing gate passed before this
native rebuild; the rebuilt E2E chain and exact replay independently passed afterward.

The executable primary/fallback modules and
`artifacts/tesla-implementation-20261005/solver-build.log` are recorded by hash.
N=12, eight parameters, final node10 also match the regenerated OCP metadata.
This is a real Darwin host build, not a C3 target build. Full target build,
stationary device checks and road acceptance remain pending.

Run from the repository root with the existing local environment:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/mile/Desktop/mo-op/.venv/bin/python \
  tools/sp_tesla_e2e/tesla_planner_chain_e2e.py --mode p1 \
  --output artifacts/sp-tesla-migration/planner-final-chain.json
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/mile/Desktop/mo-op/.venv/bin/python \
  tools/sp_tesla_e2e/tesla_planner_chain_e2e.py --mode session-transition \
  --output artifacts/sp-tesla-migration/planner-session-transition-after.json
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/mile/Desktop/mo-op/.venv/bin/python \
  tools/sp_tesla_e2e/tesla_planner_chain_e2e.py --mode cold-start \
  --output artifacts/sp-tesla-migration/planner-cold-start-after.json
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/mile/Desktop/mo-op/.venv/bin/python \
  tools/sp_tesla_e2e/tesla_planner_chain_e2e.py --mode non-tesla \
  --output artifacts/sp-tesla-migration/planner-scope-after.json
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/mile/Desktop/mo-op/.venv/bin/python \
  tools/sp_tesla_e2e/tesla_planner_chain_e2e.py --mode replay \
  --baseline artifacts/sp-tesla-migration/planner-replay-before.json \
  --output artifacts/sp-tesla-migration/planner-replay-final.json
```

SCC's all-brand desiredCurvature and five-sample confirmation patch is retained
as an existing independent behavior change; it was not modified here. Tesla SLA
discrete policy extraction is handed to the root agent separately.
