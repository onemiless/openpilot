from __future__ import annotations

import pytest

from openpilot.sunnypilot.companion.params_api import ParamAccess


class FakeParams:
  def __init__(self) -> None:
    self.values = {"ExperimentalMode": False, "ShareData": True, "SpeedFromPCM": False}

  def get_bool(self, name: str) -> bool:
    return self.values.get(name, False)

  def put_bool(self, name: str, value: bool) -> None:
    self.values[name] = value


def test_reads_only_allowlisted_params_as_app_compatible_ints():
  access = ParamAccess(FakeParams(), lambda: True)
  assert access.read(["ExperimentalMode", "ShareData"]) == {"ExperimentalMode": 0, "ShareData": 1}
  with pytest.raises(PermissionError):
    access.read(["DongleId"])


def test_writes_bool_params_only_while_offroad():
  params = FakeParams()
  access = ParamAccess(params, lambda: True)
  access.write("ExperimentalMode", 1)
  assert params.values["ExperimentalMode"]
  with pytest.raises(PermissionError):
    access.write("DongleId", "replacement")

  access = ParamAccess(params, lambda: False)
  with pytest.raises(PermissionError, match="onroad"):
    access.write("ExperimentalMode", 0)
  assert params.values["ExperimentalMode"]


@pytest.mark.parametrize("value, expected", [(True, True), (False, False), (1, True), (0, False), ("true", True), ("0", False)])
def test_writable_value_normalization(value, expected):
  params = FakeParams()
  ParamAccess(params, lambda: True).write("ShareData", value)
  assert params.values["ShareData"] is expected


def test_rejects_ambiguous_values():
  with pytest.raises(ValueError):
    ParamAccess(FakeParams(), lambda: True).write("ShareData", 2)
