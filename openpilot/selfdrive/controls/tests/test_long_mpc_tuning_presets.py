from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.tuning_presets import (
  MPC_PRESET_CURRENT, MPC_PRESET_CUSTOM, MPC_PRESET_MOUMOU, MPC_PRESETS, MPC_TUNING_KEYS, apply_preset, get_preset_values,
  save_preset_values,
)


class FakeParams:
  def __init__(self, values=None):
    self.values = dict(values or {})

  def get(self, key, return_default=False):
    del return_default
    return self.values.get(key)

  def put(self, key, value, block=False):
    del block
    self.values[key] = value


def test_builtin_presets_apply_all_live_values() -> None:
  params = FakeParams()

  values = apply_preset(params, MPC_PRESET_CURRENT)

  assert values == MPC_PRESETS[MPC_PRESET_CURRENT]
  assert params.values["MpcTuningPreset"] == MPC_PRESET_CURRENT
  assert {key: params.values[key] for key in MPC_TUNING_KEYS} == values


def test_saved_preset_values_override_only_known_keys() -> None:
  params = FakeParams({
    "MpcTuningMoumouValues": '{"MpcStopDistance": 725, "unknown": 1}',
  })

  values = get_preset_values(params, MPC_PRESET_MOUMOU)

  assert values["MpcStopDistance"] == 725
  assert "unknown" not in values
  assert values["MpcComfortBrake"] == MPC_PRESETS[MPC_PRESET_MOUMOU]["MpcComfortBrake"]


def test_custom_preset_preserves_current_live_values() -> None:
  live_values = {key: index + 100 for index, key in enumerate(MPC_TUNING_KEYS)}
  params = FakeParams(live_values)

  assert apply_preset(params, MPC_PRESET_CUSTOM) == live_values
  assert {key: params.values[key] for key in MPC_TUNING_KEYS} == live_values
  assert params.values["MpcTuningPreset"] == MPC_PRESET_CUSTOM


def test_custom_values_are_not_saved_over_builtin_presets() -> None:
  live_values = {key: index + 100 for index, key in enumerate(MPC_TUNING_KEYS)}
  params = FakeParams(live_values)

  save_preset_values(params, MPC_PRESET_CUSTOM, live_values)

  assert set(params.values) == set(MPC_TUNING_KEYS)
