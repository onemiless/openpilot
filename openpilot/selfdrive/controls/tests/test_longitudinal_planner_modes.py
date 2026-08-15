import inspect
import pytest

import openpilot.selfdrive.controls.lib.longitudinal_planner as planner_selector
from openpilot.selfdrive.debug.device_settings import get_settings, settings_snapshot, validate_and_write
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib import long_mpc as local_mpc
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib import long_mpc_official as official_mpc
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib import long_mpc_tn as tn_mpc
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.modes import (
  LONGITUDINAL_PLANNER_EXPERIMENTAL,
  LONGITUDINAL_PLANNER_OFFICIAL,
  LONGITUDINAL_PLANNER_TN,
  get_longitudinal_planner_mode,
)
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.tuning_presets import (
  MPC_OFFICIAL_VALUES,
  MPC_PROFILE_CRAZYMAX,
  MPC_PROFILE_CUSTOM,
  MPC_PROFILE_DEFAULT,
  OFFICIAL_MPC_TUNING_KEYS,
)


class FakeParams:
  def __init__(self, value=None):
    self.value = value

  def get(self, key, return_default=False):
    del return_default
    assert key == "LongitudinalPlannerMode"
    return self.value


class WritableParams:
  def __init__(self):
    self.values = {"CarPlatformBundle": {"brand": "tesla"}, "IsOffroad": True,
                   "LongitudinalPlannerMode": LONGITUDINAL_PLANNER_OFFICIAL, "MpcTuningProfile": MPC_PROFILE_DEFAULT}

  def get(self, key, return_default=False):
    del return_default
    return self.values.get(key)

  def get_bool(self, key):
    return bool(self.values.get(key))

  def put(self, key, value, block=False):
    del block
    self.values[key] = value


def test_default_and_invalid_planner_modes_use_default():
  assert get_longitudinal_planner_mode(FakeParams(None)) == LONGITUDINAL_PLANNER_OFFICIAL
  assert get_longitudinal_planner_mode(FakeParams("invalid")) == LONGITUDINAL_PLANNER_OFFICIAL
  assert get_longitudinal_planner_mode(FakeParams(99)) == LONGITUDINAL_PLANNER_OFFICIAL
  assert get_longitudinal_planner_mode(FakeParams(1)) == LONGITUDINAL_PLANNER_EXPERIMENTAL
  assert get_longitudinal_planner_mode(FakeParams(2)) == LONGITUDINAL_PLANNER_TN


def test_official_and_local_mpc_contracts_are_independent():
  assert official_mpc.PARAM_DIM == 8
  assert local_mpc.PARAM_DIM == 8
  assert tn_mpc.PARAM_DIM == 8
  assert len({official_mpc.MODEL_NAME, local_mpc.MODEL_NAME, tn_mpc.MODEL_NAME}) == 3
  assert official_mpc.MPC_SOURCES[-1] == official_mpc.LongitudinalPlanSource.cruise
  assert local_mpc.MPC_SOURCES == (local_mpc.LongitudinalPlanSource.lead0, local_mpc.LongitudinalPlanSource.lead1)
  assert "v_cruise" in inspect.signature(official_mpc.LongitudinalMpc.update).parameters
  assert "v_cruise" not in inspect.signature(local_mpc.LongitudinalMpc.update).parameters


def test_default_profile_uses_planner_defaults_not_legacy_saved_values():
  params = WritableParams()
  params.values["MpcTuningOfficialValues"] = {**MPC_OFFICIAL_VALUES, "MpcJerkCost": 625, "MpcTFollowStandard": 155}
  assert official_mpc.read_official_long_mpc_tuning(params).j_ego_cost == 5.0
  assert official_mpc.read_official_long_mpc_tuning(params).t_follow_standard == 1.45
  assert local_mpc.read_long_mpc_tuning(params).j_ego_cost == 5.0


def test_selector_lazy_loads_only_the_selected_planner(monkeypatch):
  loaded = []

  class FakeModule:
    LongitudinalPlanner = object

  monkeypatch.setattr(planner_selector, "import_module", lambda name: loaded.append(name) or FakeModule)
  assert planner_selector.get_planner_class(LONGITUDINAL_PLANNER_OFFICIAL) is object
  assert loaded == ["openpilot.selfdrive.controls.lib.longitudinal_planner_local"]
  loaded.clear()
  assert planner_selector.get_planner_class(LONGITUDINAL_PLANNER_EXPERIMENTAL) is object
  assert loaded == ["openpilot.selfdrive.controls.lib.longitudinal_planner_official"]


def test_web_exposes_independent_planner_and_tuning_selectors():
  settings = get_settings("tesla")
  assert [option["value"] for option in settings["LongitudinalPlannerMode"]["options"]] == [0, 1, 2]
  assert [option["label"] for option in settings["LongitudinalPlannerMode"]["options"]] == [
    "官方（默认）", "实验", "TN-NoDEC",
  ]
  assert [option["value"] for option in settings["MpcTuningProfile"]["options"]] == [
    MPC_PROFILE_DEFAULT, MPC_PROFILE_CRAZYMAX, MPC_PROFILE_CUSTOM,
  ]
  assert settings["LongitudinalPlannerMode"]["offroad_only"]
  assert not settings["MpcTuningProfile"]["offroad_only"]


def test_web_only_writes_runtime_parameters_in_custom_profile():
  params = WritableParams()
  validate_and_write("MpcTuningProfile", MPC_PROFILE_CRAZYMAX, params)
  assert params.values["MpcTuningProfile"] == MPC_PROFILE_CRAZYMAX
  assert params.values["MpcJerkCost"] == 300
  with pytest.raises(PermissionError, match="自定义"):
    validate_and_write("MpcJerkCost", 625, params)
  validate_and_write("MpcTuningProfile", MPC_PROFILE_CUSTOM, params)
  validate_and_write("MpcJerkCost", 625, params)
  assert local_mpc.read_long_mpc_tuning(params).j_ego_cost == 6.25
  validate_and_write("MpcStopDistance", 650, params)
  assert params.values["MpcStopDistance"] == 650
  assert "MpcStopDistance" in OFFICIAL_MPC_TUNING_KEYS


def test_web_enables_runtime_parameters_only_for_custom():
  params = WritableParams()
  snapshot = {setting["key"]: setting for setting in settings_snapshot(params)["settings"]}
  assert not snapshot["MpcStopDistance"]["enabled"]
  assert not snapshot["MpcJerkCost"]["enabled"]
  validate_and_write("MpcTuningProfile", MPC_PROFILE_CUSTOM, params)
  snapshot = {setting["key"]: setting for setting in settings_snapshot(params)["settings"]}
  assert snapshot["MpcStopDistance"]["enabled"]
  assert snapshot["MpcJerkCost"]["enabled"]
  params.values["LongitudinalPlannerMode"] = LONGITUDINAL_PLANNER_EXPERIMENTAL
  snapshot = {setting["key"]: setting for setting in settings_snapshot(params)["settings"]}
  assert snapshot["MpcStopDistance"]["enabled"]
