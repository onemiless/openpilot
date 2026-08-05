from openpilot.common.hardware.tici import hardware
from openpilot.system.hardware import offline_wake


class FakeParams:
  def __init__(self, acknowledged: bool):
    self.acknowledged = acknowledged
    self.removed = []
    self.writes = []

  def get_bool(self, key: str) -> bool:
    assert key == "PandaWakeMonitorAck"
    return self.acknowledged

  def remove(self, key: str) -> None:
    self.removed.append(key)

  def put_bool(self, key: str, value: bool, block: bool = False) -> None:
    self.writes.append((key, value, block))


class FakePanda:
  enabled = 0

  @classmethod
  def list(cls):
    return ["internal"]

  def __init__(self, serial: str, disable_checks: bool):
    assert serial == "internal"
    assert not disable_checks
    self.armed = False

  def __enter__(self):
    return self

  def __exit__(self, exc_type, exc, traceback):
    return False

  def is_internal(self):
    return True

  def health(self):
    return {}

  def wake_debug(self):
    stage = offline_wake.PANDA_WAKE_MONITOR_ARMED_STAGE if self.armed else 0
    return {"magic": offline_wake.PANDA_WAKE_DEBUG_MAGIC, "stage": stage}

  def send_heartbeat(self, engaged: bool, engaged_mads: bool):
    assert not engaged
    assert not engaged_mads

  def enable_deepsleep(self):
    type(self).enabled += 1
    self.armed = True


def install_fakes(monkeypatch, params: FakeParams, panda_cls=FakePanda):
  import openpilot.common.params as params_module
  import panda as panda_module

  monkeypatch.setattr(params_module, "Params", lambda: params)
  monkeypatch.setattr(panda_module, "Panda", panda_cls)
  monkeypatch.setattr(hardware, "panda_bootkick_test_pending", lambda: False)


def test_shutdown_rearms_internal_panda_even_with_existing_ack(monkeypatch):
  params = FakeParams(acknowledged=True)
  FakePanda.enabled = 0
  install_fakes(monkeypatch, params)

  assert hardware.request_internal_panda_wake_monitor()
  assert FakePanda.enabled == 1
  assert params.removed == ["PandaWakeMonitorRequest"]
  assert params.writes == [("PandaWakeMonitorAck", True, True)]


def test_shutdown_accepts_verified_preflight_if_panda_already_entered_stop(monkeypatch):
  class SleepingPanda(FakePanda):
    @classmethod
    def list(cls):
      return []

  params = FakeParams(acknowledged=True)
  install_fakes(monkeypatch, params, SleepingPanda)

  assert hardware.request_internal_panda_wake_monitor()
  assert params.writes == []


def test_shutdown_without_ack_requires_responsive_internal_panda(monkeypatch):
  class MissingPanda(FakePanda):
    @classmethod
    def list(cls):
      return []

  params = FakeParams(acknowledged=False)
  install_fakes(monkeypatch, params, MissingPanda)

  assert not hardware.request_internal_panda_wake_monitor()


def test_existing_ack_does_not_hide_failed_rearm_of_responsive_panda(monkeypatch):
  class UnconfirmedPanda(FakePanda):
    def wake_debug(self):
      return {"magic": offline_wake.PANDA_WAKE_DEBUG_MAGIC, "stage": 0}

  params = FakeParams(acknowledged=True)
  install_fakes(monkeypatch, params, UnconfirmedPanda)

  assert not hardware.request_internal_panda_wake_monitor()


def test_shutdown_skips_rearm_for_bootkick_test(monkeypatch):
  monkeypatch.setattr(hardware, "panda_bootkick_test_pending", lambda: True)

  assert hardware.request_internal_panda_wake_monitor()


def test_unconfirmed_monitor_reboots_instead_of_powering_off(monkeypatch):
  import openpilot.common.params as params_module

  class NoForceParams(FakeParams):
    def get_bool(self, key: str) -> bool:
      assert key == "ForcePowerDown"
      return False

  commands = []
  monkeypatch.setattr(hardware, "request_internal_panda_wake_monitor", lambda: False)
  monkeypatch.setattr(params_module, "Params", lambda: NoForceParams(acknowledged=False))
  monkeypatch.setattr(hardware.os, "sync", lambda: None)
  monkeypatch.setattr(hardware.subprocess, "run", lambda command, shell: commands.append((command, shell)))

  hardware.Tici.shutdown(object.__new__(hardware.Tici))

  assert commands == [("sudo reboot", True)]


def test_force_power_down_allows_unconfirmed_monitor(monkeypatch):
  import openpilot.common.params as params_module

  class ForceParams(FakeParams):
    def get_bool(self, key: str) -> bool:
      assert key == "ForcePowerDown"
      return True

  commands = []
  monkeypatch.setattr(hardware, "request_internal_panda_wake_monitor", lambda: False)
  monkeypatch.setattr(params_module, "Params", lambda: ForceParams(acknowledged=False))
  monkeypatch.setattr(hardware.os, "sync", lambda: None)
  monkeypatch.setattr(hardware.subprocess, "run", lambda command, shell: commands.append((command, shell)))

  hardware.Tici.shutdown(object.__new__(hardware.Tici))

  assert commands == [("sudo poweroff", True)]
