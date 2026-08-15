from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.tuning_presets import (
  MPC_OFFICIAL_VALUES, MPC_PROFILE_CUSTOM, MPC_PROFILE_DEFAULT, MPC_TUNING_KEYS,
  apply_profile, get_profile_values, save_profile_values,
)
from openpilot.selfdrive.controls.lib.longitudinal_backends.tuning import CONFIG_PARAM, default_snapshot
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import LongMpcTuning, read_long_mpc_tuning


class FakeParams:
  def __init__(self, values=None):
    self.values = values or {}

  def get(self, key, return_default=False):
    del return_default
    return self.values.get(key)

  def put(self, key, value, block=False):
    del block
    self.values[key] = value


def test_default_profile_is_official_and_immutable():
  params = FakeParams()
  assert get_profile_values(params, MPC_PROFILE_DEFAULT) == MPC_OFFICIAL_VALUES
  tuned = {**MPC_OFFICIAL_VALUES, "MpcJerkCost": 650}
  save_profile_values(params, MPC_PROFILE_DEFAULT, tuned)
  assert get_profile_values(params, MPC_PROFILE_DEFAULT)["MpcJerkCost"] == MPC_OFFICIAL_VALUES["MpcJerkCost"]


def test_apply_custom_profile_starts_from_default_and_updates_selector():
  params = FakeParams()
  values = apply_profile(params, MPC_PROFILE_CUSTOM)
  assert values == MPC_OFFICIAL_VALUES
  assert params.values["MpcTuningProfile"] == MPC_PROFILE_CUSTOM
  assert all(params.values[key] == value for key, value in values.items())


def test_custom_profile_saves_a_separate_backend_blob():
  live_values = {key: index + 100 for index, key in enumerate(MPC_TUNING_KEYS)}
  live_values.update({"MpcTFollowRelaxed": 175, "MpcTFollowStandard": 145, "MpcTFollowAggressive": 125})
  params = FakeParams()
  save_profile_values(params, MPC_PROFILE_CUSTOM, live_values)
  assert get_profile_values(params, MPC_PROFILE_CUSTOM) == live_values


def test_atomic_config_overrides_legacy_values_for_local():
  params = FakeParams(dict(MPC_OFFICIAL_VALUES))
  config = default_snapshot(revision=4).to_dict()
  config["families"]["acados_long_v1"]["mpc.jerk_cost"] = 6.25
  params.values[CONFIG_PARAM] = config
  assert read_long_mpc_tuning(params).j_ego_cost == 6.25


def test_malformed_atomic_config_keeps_last_known_good():
  params = FakeParams({CONFIG_PARAM: "{broken"})
  previous = LongMpcTuning(j_ego_cost=6.25)
  assert read_long_mpc_tuning(params, last_known_good=previous) is previous
