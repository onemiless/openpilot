from openpilot.selfdrive.controls.lib.longitudinal_backends.registry import BackendId, get_backend
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.modes import (
  LONGITUDINAL_PLANNER_CRAZYMAX,
  LONGITUDINAL_PLANNER_DEFAULT,
  LONGITUDINAL_PLANNER_LABELS,
)
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.tuning_presets import (
  MPC_CRAZYMAX_VALUES,
  MPC_OFFICIAL_VALUES,
  MPC_PROFILE_LABELS,
  MPC_PROFILES,
  MPC_PROFILE_CRAZYMAX,
)


def test_stable_backend_ids_match_user_facing_implementations():
  default = get_backend(0)
  crazymax = get_backend(1)

  assert default.id == BackendId.DEFAULT == LONGITUDINAL_PLANNER_DEFAULT
  assert default.label == LONGITUDINAL_PLANNER_LABELS[LONGITUDINAL_PLANNER_DEFAULT] == "Default"
  assert default.planner_module.endswith("longitudinal_planner_local")
  assert default.solver.model_name == "long"

  assert crazymax.id == BackendId.CRAZYMAX == LONGITUDINAL_PLANNER_CRAZYMAX
  assert crazymax.label == LONGITUDINAL_PLANNER_LABELS[LONGITUDINAL_PLANNER_CRAZYMAX] == "CrazyMax"
  assert crazymax.planner_module.endswith("longitudinal_planner_official")
  assert crazymax.solver.model_name == "long_official"


def test_crazymax_defaults_are_an_independent_verified_preset():
  # The verified Moumou baseline currently uses the same numerical constants as
  # upstream. Keep a separate object so either implementation can evolve without
  # silently falling back to the other profile.
  assert MPC_CRAZYMAX_VALUES == MPC_OFFICIAL_VALUES
  assert MPC_CRAZYMAX_VALUES is not MPC_OFFICIAL_VALUES
  assert MPC_PROFILE_LABELS[MPC_PROFILE_CRAZYMAX] == "Moumou Baseline"
  assert MPC_PROFILES[MPC_PROFILE_CRAZYMAX] is MPC_CRAZYMAX_VALUES
