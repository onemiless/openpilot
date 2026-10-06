# TN highway comfort candidate

The implementation lives on `dev-sp` in `tn_no_dec/long_mpc.py`. Its review
switch, `LongitudinalMpc.high_speed_comfort_enabled`, defaults to `False`.
This commit records tested code; it does not enable it for normal driving.

When explicitly enabled for replay, the candidate blends the configured
comfort-braking assumption toward 1.8 m/s² over 15–25 m/s. Available lead
distance controls the blend, so already-close leads retain the original
assumption. It preserves actuator deceleration limits, following time,
persistent tuning, other backends, and zero-cruise/forced-deceleration policy.

Validation completed on 2026-10-06:

- 39 paired closed-loop scenarios, disabled equivalence, and independent
  repeat hashes. The hypothetical vehicle is not a calibrated Tesla model.
- Far slower-lead cases established light deceleration about five seconds
  earlier; peak deceleration changed from about 0.382 to 0.268 m/s².
- Close-lead cases retained the original initial peak and jerk; steady
  following gaps, low-speed, no-lead, and non-TN comparisons were preserved.
- C3 native replay of segments 79–81 and 103–105: 7,200 candidate steps,
  primary/final solver success, no fallback, and active Params unchanged.
- Forced-deceleration and zero-cruise preservation were checked through the
  actual planner, publisher, and LongControl.

Evidence and repeat commands are retained in
`/Users/mile/.codex/visualizations/2026/10/06/tn-comfort-native/REPORT.md`
and `../tn-implementation/candidate_comfort/RESULT.md`. Their manifests
identify inputs, sources, dependencies, and outputs. The C3 used recording
commit `2d6e33332e0567c17bbb8f1626ddcd8de00efa52`; its compatibility overlay
has the same update-method AST as this implementation.

The candidate can also react earlier to a false visual lead. Recorded-ego
replay is not closed-loop vehicle evidence, and neither establishes road
acceptance. Keep normal-driving activation separate from this source commit.
Rollback uses `git revert` on this commit, not a branch switch or hard reset.
