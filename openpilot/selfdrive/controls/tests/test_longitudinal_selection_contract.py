from openpilot.selfdrive.controls.lib.longitudinal_backends.registry import BackendId, get_backend
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.modes import (
  LONGITUDINAL_PLANNER_EXPERIMENTAL,
  LONGITUDINAL_PLANNER_OFFICIAL,
  LONGITUDINAL_PLANNER_LABELS,
)
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.tuning_presets import (
  MPC_CRAZYMAX_VALUES,
  MPC_PROFILE_CUSTOM,
  MPC_PROFILE_DEFAULT,
  MPC_OFFICIAL_VALUES,
  MPC_PROFILE_LABELS,
  MPC_PROFILES,
  MPC_PROFILE_CRAZYMAX,
  get_mpc_tuning_profile,
  get_profile_values,
  save_profile_values,
  write_live_values,
)
from openpilot.selfdrive.controls.lib.longitudinal_backends.tuning import load_snapshot, resolve_tuning


def test_stable_backend_ids_match_user_facing_implementations():
  official = get_backend(0)
  experimental = get_backend(1)

  assert official.id == BackendId.OFFICIAL == LONGITUDINAL_PLANNER_OFFICIAL
  assert official.label == LONGITUDINAL_PLANNER_LABELS[LONGITUDINAL_PLANNER_OFFICIAL] == "Official"
  assert official.planner_module.endswith("longitudinal_planner_local")
  assert official.solver.model_name == "long"

  assert experimental.id == BackendId.EXPERIMENTAL == LONGITUDINAL_PLANNER_EXPERIMENTAL
  assert experimental.label == LONGITUDINAL_PLANNER_LABELS[LONGITUDINAL_PLANNER_EXPERIMENTAL] == "Experimental"
  assert experimental.planner_module.endswith("longitudinal_planner_official")
  assert experimental.solver.model_name == "long_official"


def test_crazymax_defaults_are_an_independent_verified_preset():
  # The verified Moumou baseline currently uses the same numerical constants as
  # upstream. It remains a parameter preset, not a planner implementation.
  assert MPC_CRAZYMAX_VALUES == MPC_OFFICIAL_VALUES
  assert MPC_CRAZYMAX_VALUES is not MPC_OFFICIAL_VALUES
  assert MPC_PROFILE_LABELS == {
    MPC_PROFILE_DEFAULT: "Default",
    MPC_PROFILE_CRAZYMAX: "CrazyMax",
    MPC_PROFILE_CUSTOM: "Custom",
  }
  assert MPC_PROFILES[MPC_PROFILE_CRAZYMAX] is MPC_CRAZYMAX_VALUES


class FakeParams:
  def __init__(self, values=None):
    self.values = values or {}

  def get(self, key, return_default=False):
    del return_default
    return self.values.get(key)

  def put(self, key, value, block=False):
    del block
    self.values[key] = value


def test_custom_starts_from_each_planners_default_and_is_saved_independently():
  params = FakeParams()
  official = get_backend(0)
  experimental = get_backend(1)

  official_custom = get_profile_values(params, MPC_PROFILE_CUSTOM, official)
  experimental_custom = get_profile_values(params, MPC_PROFILE_CUSTOM, experimental)
  assert official_custom == get_profile_values(params, MPC_PROFILE_DEFAULT, official)
  assert experimental_custom == get_profile_values(params, MPC_PROFILE_DEFAULT, experimental)

  official_custom["MpcJerkCost"] = 625
  save_profile_values(params, MPC_PROFILE_CUSTOM, official_custom, official)
  assert get_profile_values(params, MPC_PROFILE_CUSTOM, official)["MpcJerkCost"] == 625
  assert get_profile_values(params, MPC_PROFILE_CUSTOM, experimental)["MpcJerkCost"] != 625


def test_runtime_custom_overrides_only_the_selected_planner():
  params = FakeParams({"LongitudinalPlannerMode": 0, "MpcTuningProfile": MPC_PROFILE_DEFAULT})
  official = get_backend(0)
  experimental = get_backend(1)
  custom = get_profile_values(params, MPC_PROFILE_CUSTOM, official)
  custom["MpcJerkCost"] = 625
  save_profile_values(params, MPC_PROFILE_CUSTOM, custom, official)
  write_live_values(params, custom, selected_profile=MPC_PROFILE_CUSTOM, backend=official)

  snapshot = load_snapshot(params)
  assert snapshot is not None
  assert resolve_tuning(snapshot, official).native_values["j_ego_cost"] == 6.25
  assert resolve_tuning(snapshot, experimental).native_values["j_ego_cost"] == 5.0


def test_legacy_custom_profile_is_migrated_without_losing_values():
  legacy_values = {**MPC_OFFICIAL_VALUES, "MpcJerkCost": 650}
  params = FakeParams({**legacy_values, "LongitudinalPlannerMode": 1, "MpcTuningProfile": 3})
  assert get_mpc_tuning_profile(params) == MPC_PROFILE_CUSTOM
  assert params.values["MpcTuningProfile"] == MPC_PROFILE_CUSTOM
  assert get_profile_values(params, MPC_PROFILE_CUSTOM, get_backend(1))["MpcJerkCost"] == 650
