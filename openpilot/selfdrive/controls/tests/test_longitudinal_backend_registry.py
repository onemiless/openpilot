import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from openpilot.common.params import Params
from openpilot.selfdrive.controls.lib.longitudinal_backends.registry import (
  BACKENDS, PARAM_SPECS, BackendId, ApplyMode, get_backend, ordered_backends, validate_registry,
)
from openpilot.selfdrive.controls.lib.longitudinal_backends.tuning import (
  CONFIG_PARAM, MIGRATION_MARKER_PARAM, default_snapshot, load_snapshot, migrate_legacy_config, parse_snapshot,
  ramp_dataclass, resolve_tuning, snapshot_from_legacy, write_snapshot,
)
from openpilot.selfdrive.controls.lib.longitudinal_backends.session import ACTIVE_BACKEND_PARAM, latch_active_backend
from openpilot.selfdrive.controls.lib.longitudinal_backends.tn_no_dec.longcontrol_policy import TNStoppingPolicy
from openpilot.selfdrive.controls.lib.longitudinal_backends.tn_no_dec.planner_sp import LongitudinalPlannerSP
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.tuning_presets import MPC_OFFICIAL_VALUES


class FakeParams:
  def __init__(self, values=None):
    self.values = values or {}
    self.puts = []

  def get(self, key, return_default=False):
    del return_default
    return self.values.get(key)

  def put(self, key, value, block=False):
    del block
    self.puts.append((key, value))
    self.values[key] = value

  def get_bool(self, key):
    return bool(self.values.get(key))

  def put_bool(self, key, value, block=False):
    self.put(key, bool(value), block)


@dataclass(frozen=True)
class FakeTuning:
  t_follow_standard: float
  accel_personality_enabled: bool = False


def test_registry_has_stable_order_and_fallback():
  assert [backend.id for backend in ordered_backends()] == [0, 1, 2]
  assert get_backend(0).id == BackendId.OFFICIAL
  assert get_backend(1).id == BackendId.EXPERIMENTAL
  assert get_backend(2).id == BackendId.TN_NO_DEC
  assert get_backend(None).id == BackendId.OFFICIAL
  assert get_backend("bad").id == BackendId.OFFICIAL
  validate_registry()


def test_runtime_schema_does_not_expose_solver_structure():
  forbidden = {"PARAM_DIM", "X_DIM", "U_DIM", "COST_DIM", "N", "T_IDXS", "MODEL_NAME"}
  assert not forbidden & {spec.id for spec in PARAM_SPECS}
  assert all(spec.apply_mode not in (ApplyMode.BUILD, ApplyMode.RESTART) for spec in PARAM_SPECS)


def test_snapshot_is_written_as_one_atomic_param():
  params = FakeParams()
  snapshot = default_snapshot(revision=7)
  write_snapshot(params, snapshot)
  assert len(params.puts) == 1
  assert params.puts[0][0] == CONFIG_PARAM
  assert load_snapshot(params) == snapshot


def test_legacy_defaults_migrate_without_numeric_drift():
  params = FakeParams({"MpcTuningProfile": 0})
  snapshot = snapshot_from_legacy(params)
  experimental = resolve_tuning(snapshot, BACKENDS[BackendId.EXPERIMENTAL]).native_values
  assert experimental["x_ego_obstacle_cost"] == MPC_OFFICIAL_VALUES["MpcXObstacleCost"] / 100.0
  assert experimental["comfort_brake"] == MPC_OFFICIAL_VALUES["MpcComfortBrake"] / 100.0
  assert experimental["stop_distance"] == MPC_OFFICIAL_VALUES["MpcStopDistance"] / 100.0
  assert experimental["t_follow_standard"] == MPC_OFFICIAL_VALUES["MpcTFollowStandard"] / 100.0


def test_one_shot_migration_preserves_legacy_sp_solver_fixed_values():
  params = FakeParams({"MpcTuningProfile": 2})
  snapshot = migrate_legacy_config(params)
  official = resolve_tuning(snapshot, BACKENDS[BackendId.OFFICIAL]).native_values
  assert official["comfort_brake"] == 2.5
  assert official["stop_distance"] == 6.0
  assert params.values[MIGRATION_MARKER_PARAM] is True
  assert migrate_legacy_config(params) == snapshot


@pytest.mark.parametrize("mutation", [
  lambda cfg: cfg.update(revision=-1),
  lambda cfg: cfg["shared"].update({"following.time.standard_s": float("nan")}),
  lambda cfg: cfg["shared"].update({"following.time.standard_s": 99.0}),
  lambda cfg: cfg["families"]["acados_long_v1"].update({"PARAM_DIM": 8}),
])
def test_invalid_revision_is_rejected_as_a_whole(mutation):
  config = default_snapshot(revision=3).to_dict()
  mutation(config)
  with pytest.raises(ValueError):
    parse_snapshot(json.dumps(config))


def test_following_time_order_is_validated():
  config = default_snapshot(revision=3).to_dict()
  config["shared"].update({
    "following.time.relaxed_s": 1.0,
    "following.time.standard_s": 1.5,
    "following.time.aggressive_s": 1.2,
  })
  with pytest.raises(ValueError, match="aggressive <= standard <= relaxed"):
    parse_snapshot(config)


def test_active_backend_is_latched_across_process_restarts():
  params = Params()
  params.put("LongitudinalPlannerMode", int(BackendId.TN_NO_DEC), block=True)
  assert latch_active_backend(params) == BackendId.TN_NO_DEC
  params.put("LongitudinalPlannerMode", int(BackendId.OFFICIAL), block=True)
  assert latch_active_backend(params) == BackendId.TN_NO_DEC
  assert params.get(ACTIVE_BACKEND_PARAM) == int(BackendId.TN_NO_DEC)


def test_ramped_and_hot_native_values_have_distinct_lifecycle():
  backend = BACKENDS[BackendId.TN_NO_DEC]
  current = FakeTuning(t_follow_standard=1.45, accel_personality_enabled=False)
  target = FakeTuning(t_follow_standard=2.45, accel_personality_enabled=True)
  stepped = ramp_dataclass(current, target, backend, 1.0)
  assert stepped.t_follow_standard == pytest.approx(1.65)
  assert stepped.accel_personality_enabled is True


def test_tn_no_dec_has_no_dynamic_experimental_controller_dependency():
  root = Path(__file__).parents[1] / "lib" / "longitudinal_backends" / "tn_no_dec"
  source = "\n".join(path.read_text() for path in root.rglob("*.py"))
  assert "DynamicExperimental" not in source
  assert "self.dec" not in source
  assert "dynamic_experimental_control" not in source.lower()
  assert "dynamic_experimental_control" not in BACKENDS[BackendId.TN_NO_DEC].capabilities
  planner = LongitudinalPlannerSP.__new__(LongitudinalPlannerSP)
  assert planner.is_e2e({"selfdriveState": SimpleNamespace(experimentalMode=True)}) is True


def test_tn_stopping_policy_fails_safe_on_invalid_inputs():
  policy = TNStoppingPolicy()
  cs = SimpleNamespace(vEgo=float("nan"), aEgo=0.0, standstill=False)
  assert policy.stopping_decel_rate(cs, -0.5, -0.2) == 1.0
