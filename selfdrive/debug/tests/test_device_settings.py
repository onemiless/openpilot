import pytest

from openpilot.selfdrive.debug.device_settings import get_settings, settings_snapshot, validate_and_write


class FakeParams:
  def __init__(self, onroad=False):
    self.onroad = onroad
    self.values = {}

  def get_bool(self, key):
    return self.onroad if key == "IsOnroad" else self.values.get(key, False)

  def get(self, key, return_default=False):
    return self.values.get(key, "0")

  def put_bool(self, key, value, block=True):
    self.values[key] = value

  def put(self, key, value, block=True):
    self.values[key] = value


def test_settings_are_whitelisted_and_classified():
  settings = get_settings()
  assert "TeslaApHybrid" in settings
  assert settings["TeslaApHybrid"]["offroad_only"]
  assert not settings["MpcJerkCost"]["offroad_only"]
  assert "GithubSshKeys" not in settings
  assert "SecOCKey" not in settings


def test_writes_validate_type_and_range():
  params = FakeParams()
  assert validate_and_write("TeslaAutoSpeedLimit", True, params)["value"]
  assert params.values["TeslaAutoSpeedLimit"] is True
  assert validate_and_write("MpcJerkCost", 501, params)["value"] == 501
  with pytest.raises(ValueError):
    validate_and_write("MpcJerkCost", 5001, params)
  with pytest.raises(ValueError):
    validate_and_write("TeslaAutoSpeedLimit", 1, params)
  with pytest.raises(KeyError):
    validate_and_write("GithubSshKeys", "no", params)
  assert validate_and_write("TorqueControlTune", "", params)["value"] == ""
  assert validate_and_write("TorqueControlTune", 1.0, params)["value"] == 1.0


def test_offroad_only_is_enforced_by_backend():
  params = FakeParams(onroad=True)
  with pytest.raises(PermissionError):
    validate_and_write("TeslaApHybrid", True, params)
  assert validate_and_write("MpcJerkCost", 501, params)["value"] == 501
  snapshot = settings_snapshot(params)
  assert snapshot["onroad"]
