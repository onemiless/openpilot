from subprocess import CompletedProcess

from openpilot.selfdrive.debug.device_hotspot import HOTSPOT_URL, hotspot_status, set_hotspot_enabled


class FakeRunner:
  def __init__(self, active: bool = False):
    self.active = active
    self.commands = []

  def __call__(self, command, **_kwargs):
    self.commands.append(command)
    if "--active" in command:
      return CompletedProcess(command, 0, "Hotspot:wlan0\n" if self.active else "office:wlan0\n", "")
    if "up" in command:
      self.active = True
    elif "down" in command:
      self.active = False
    return CompletedProcess(command, 0, "", "")


def test_hotspot_state_and_switching():
  runner = FakeRunner()
  assert not hotspot_status(runner)["active"]
  assert set_hotspot_enabled(True, runner)["active"]
  assert set_hotspot_enabled(False, runner)["active"] is False
  assert hotspot_status(runner)["url"] == HOTSPOT_URL
