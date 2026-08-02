import pytest

from openpilot.selfdrive.debug.device_terminal import change_password, run_command, terminal_status


class FakeParams:
  def __init__(self, enabled=True, onroad=False, password="test-password"):
    self.enabled = enabled
    self.onroad = onroad
    self.values = {"WebTerminalPassword": password}

  def get_bool(self, key):
    return {"WebTerminalEnabled": self.enabled, "IsOnroad": self.onroad}[key]

  def get(self, key, return_default=False):
    return self.values.get(key)

  def put(self, key, value, block=True):
    self.values[key] = value


def test_terminal_runs_command_after_authorization():
  result = run_command("printf terminal-ok", "test-password", FakeParams())
  assert result == {"exit_code": 0, "timed_out": False, "output": "terminal-ok"}


def test_terminal_rejects_invalid_password_or_onroad_execution():
  with pytest.raises(PermissionError):
    run_command("true", "wrong", FakeParams())
  with pytest.raises(PermissionError):
    run_command("true", "test-password", FakeParams(onroad=True))
  assert terminal_status(FakeParams(enabled=False)) == {"enabled": False, "onroad": False}


def test_terminal_password_can_be_changed():
  params = FakeParams()
  change_password("test-password", "new-password", params)
  assert params.values["WebTerminalPassword"] == "new-password"

  with pytest.raises(PermissionError):
    change_password("wrong", "another-password", params)
