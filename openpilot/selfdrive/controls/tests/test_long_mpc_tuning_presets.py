from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.tuning_presets import (
  MPC_OFFICIAL_VALUES, MPC_PROFILE_CURRENT, MPC_PROFILE_CUSTOM, MPC_PROFILE_DEFAULT, MPC_PROFILES, MPC_TUNING_KEYS,
  apply_profile, get_profile_values, save_profile_values,
)


class FakeParams:
  def __init__(self, values=None):
    self.values = values or {}

  def get(self, key, return_default=False):
    del return_default
    return self.values.get(key)

  def put(self, key, value, block=False):
    del block
    self.values[key] = value


def test_default_profile_is_official_and_can_store_tuning():
  params = FakeParams()
  assert get_profile_values(params, MPC_PROFILE_DEFAULT) == MPC_OFFICIAL_VALUES
  tuned = {**MPC_OFFICIAL_VALUES, "MpcJerkCost": 650}
  save_profile_values(params, MPC_PROFILE_DEFAULT, tuned)
  assert get_profile_values(params, MPC_PROFILE_DEFAULT)["MpcJerkCost"] == 650


def test_apply_current_profile_updates_live_values_and_selector():
  params = FakeParams()
  values = apply_profile(params, MPC_PROFILE_CURRENT)
  assert values == MPC_PROFILES[MPC_PROFILE_CURRENT]
  assert params.values["MpcTuningProfile"] == MPC_PROFILE_CURRENT
  assert all(params.values[key] == value for key, value in values.items())


def test_custom_profile_reads_live_values():
  live_values = {key: index + 100 for index, key in enumerate(MPC_TUNING_KEYS)}
  params = FakeParams(live_values.copy())
  assert apply_profile(params, MPC_PROFILE_CUSTOM) == live_values
  assert params.values["MpcTuningProfile"] == MPC_PROFILE_CUSTOM


def test_custom_profile_has_no_separate_saved_blob():
  live_values = {key: index + 100 for index, key in enumerate(MPC_TUNING_KEYS)}
  params = FakeParams()
  save_profile_values(params, MPC_PROFILE_CUSTOM, live_values)
  assert params.values == {}
