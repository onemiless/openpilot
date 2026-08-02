import pytest

from openpilot.selfdrive.debug.device_terminal import run_command, terminal_status


class FakeParams:
  def __init__(self, enabled=True, onroad=False, token="test-token"):
    self.enabled = enabled
    self.onroad = onroad
    self.values = {"WebTerminalToken": token}

  def get_bool(self, key):
    return {"WebTerminalEnabled": self.enabled, "IsOnroad": self.onroad}[key]

  def get(self, key):
    return self.values.get(key)

  def put(self, key, value, block=True):
    self.values[key] = value


def test_terminal_runs_command_after_authorization():
  result = run_command("printf terminal-ok", "test-token", FakeParams())
  assert result == {"exit_code": 0, "timed_out": False, "output": "terminal-ok"}


def test_terminal_rejects_invalid_token_or_onroad_execution():
  with pytest.raises(PermissionError):
    run_command("true", "wrong", FakeParams())
  with pytest.raises(PermissionError):
    run_command("true", "test-token", FakeParams(onroad=True))
  assert terminal_status(FakeParams(enabled=False)) == {"enabled": False, "onroad": False}
