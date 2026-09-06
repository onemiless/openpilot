# Tesla Traffic correctness and cleanup — 2026-09-05

Source baseline: `dev-sp-egpu@1ccc470870`; Nav baseline: `navassist-track-p0@7b68c3587e`.
Scope: implement the approved read-only audit findings without changing Stop/Go
thresholds, the three Planner Backends, or the common post-plan constraint Seam.

## Correctness fix

`TeslaTrafficControlObserver.update()` previously selected timestamp/DLC from
the latest qualifying frame, but read values left by a parser fed the entire
batch. A trailing short frame or older frame could therefore publish its green
light/distance with the newer red frame's timestamp/DLC. The original failing
case produced GREEN/20m/8 bytes at 2.0s instead of RED/80m from the valid frame.

The observer now validates and decodes each candidate as one tuple, keeps only
monotonically newest successful observations, and preserves last-successful
input ordering for tied timestamps. Decode rejection never refreshes metadata
and never hides a successful frame in the same batch. Six-byte observations
remain supported. No generic CAN parser or DBC was modified.

Persistent tests cover mixed short tails, all 120 orderings of a five-packet
batch, same-time valid/invalid frames, older frames, decode rejection, and
expiry. The initial short-tail regression failed before implementation; the
rejected-latest regression exposed and corrected a first-pass selection gap.
This proves the code defect, not its occurrence rate in actual vehicle logs.

## Behavior-preserving cleanup

- Remove unused onroad notice/latch/text computation and its exclusive tests.
  The 64×128 signal, current-applied blue outline, flashing and invalid-message
  behavior remain. Remove 31 obsolete entries from each of the English catalog
  template and Simplified Chinese catalog; keep diagnostic schema fields.
- Remove the always-true web visualization gate and unreachable disabled-tab
  handling. Keep web endpoints, CAN curves, diagnostics and existing permissions.
- Keep `TeslaWebDrivingVisualization` registered only as a retired compatibility
  tombstone. It has no runtime/UI readers. Removing its native registry copies
  would require relinking prebuilt native consumers; do not broaden this patch
  into an unrelated model/firmware rebuild just to erase the unused name.
- Centralize four flash-candidate resets and seven lead-gate resets. Do not
  merge confirmed flash latches with candidate evidence, or session-long GO
  delegation with current lead confirmation. Remove the unreachable
  `same_release_start` expression without changing branch order.
- Correct CONTEXT/ADR descriptions to the current post-plan Seam and small-icon
  contract. Existing Off semantics and legacy mode/diagnostic numeric values stay.

## Verification

- Focused combined suites: base 333 passed; Nav 342 passed.
- State refactor equivalence against fixed `1ccc470870`: 174 existing tests per
  version; 1,070 full controller decisions/event outputs and 369 full final-plan
  plus diagnostic outputs exactly equal. Finite floats compared using hex, not
  an approximate tolerance. Trace SHA-256:
  `b54320f56ebf561fbe518cc4b6488e1aa51bc2e77e1a073d3ef6cf38d09da52c`.
- Nine new tests exercise the actual registry-selected backend publish methods,
  real SP publishing and real FinalPlanArbitrator. They check current-cycle
  plan/SP agreement, STOP attribution, Off transparency and publication order.
  Fault injections that swap ordering or replace final aTarget with base aTarget
  fail these tests. MPC initialization/update/solver quality is not covered by
  this publish-only fixture.
- Ruff and diff checks pass. Translation syntax checks pass; pre-existing PO
  header metadata warnings remain unchanged.

## Intentionally unchanged

No threshold tuning, new strategies, MPC target injection, physical lead
rewriting, vehicle CAN output changes, schema field removal/reordering, AGNOS
upgrade, Panda flashing or eGPU/model changes. Do not claim an onroad safety or
performance guarantee from synthetic tests. The small snapshot/unused-jerk
performance candidates remain deferred: no measured bottleneck justifies extra
interface complexity or numerical changes in this patch.
