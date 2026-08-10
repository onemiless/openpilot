from openpilot.common.hardware.tici import hardware
from openpilot.system.hardware import offline_wake


class FakeParams:
  def __init__(self, acknowledged: bool):
    self.acknowledged = acknowledged
    self.transaction = "12345678"
    self.removed = []
    self.writes = []

  def get(self, key: str):
    if key == "PandaWakeMonitorTxn":
      return self.transaction
    if key == "PandaWakeMonitorAck":
      return self.transaction if self.acknowledged else None
    raise AssertionError(key)

  def remove(self, key: str) -> None:
    self.removed.append(key)

  def put_bool(self, key: str, value: bool, block: bool = False) -> None:
    self.writes.append((key, value, block))


class FakePanda:
  committed = 0

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

  def set_host_session(self, host_session: int):
    assert host_session != 0

  def health(self):
    return {"faults": 0, "fault_status": 0, "rx_buffer_overflow": 0}

  def can_health(self, can_number: int):
    assert can_number in (0, 1, 2)
    return {"bus_off": False, "error_passive": False, "total_rx_lost_cnt": 0}

  def commit_wake_monitor(self, transaction: int):
    type(self).committed += 1
    return {
      "magic": offline_wake.PANDA_WAKE_MONITOR_STATUS_MAGIC,
      "transaction": transaction,
      "state": offline_wake.PANDA_WAKE_MONITOR_COMMITTED_STATE,
      "flags": offline_wake.PANDA_WAKE_MONITOR_STATUS_FLAG_RX_ARMED |
               offline_wake.PANDA_WAKE_MONITOR_STATUS_FLAG_CAN_HEALTHY,
    }


def install_fakes(monkeypatch, params: FakeParams, panda_cls=FakePanda):
  import openpilot.common.params as params_module
  import panda as panda_module

  monkeypatch.setattr(params_module, "Params", lambda: params)
  monkeypatch.setattr(panda_module, "Panda", panda_cls)
  monkeypatch.setattr(hardware, "panda_bootkick_test_pending", lambda: False)
  monkeypatch.setattr(hardware, "current_host_session", lambda: 0x87654321)


def test_shutdown_commits_prepared_transaction_exactly_once(monkeypatch):
  params = FakeParams(acknowledged=True)
  FakePanda.committed = 0
  install_fakes(monkeypatch, params)

  assert hardware.request_internal_panda_wake_monitor()
  assert FakePanda.committed == 1
  assert params.removed == []
  assert params.writes == []


def test_shutdown_rejects_old_ack_if_panda_is_unreachable(monkeypatch):
  class SleepingPanda(FakePanda):
    @classmethod
    def list(cls):
      return []

  params = FakeParams(acknowledged=True)
  install_fakes(monkeypatch, params, SleepingPanda)

  assert not hardware.request_internal_panda_wake_monitor()
  assert params.writes == []


def test_shutdown_without_ack_requires_responsive_internal_panda(monkeypatch):
  class MissingPanda(FakePanda):
    @classmethod
    def list(cls):
      return []

  params = FakeParams(acknowledged=False)
  install_fakes(monkeypatch, params, MissingPanda)

  assert not hardware.request_internal_panda_wake_monitor()


def test_stale_ack_never_reaches_commit(monkeypatch):
  params = FakeParams(acknowledged=True)
  params.transaction = "12345678"
  install_fakes(monkeypatch, params)
  original_get = params.get

  def stale_ack(key: str):
    return "87654321" if key == "PandaWakeMonitorAck" else original_get(key)

  params.get = stale_ack
  FakePanda.committed = 0

  assert not hardware.request_internal_panda_wake_monitor()
  assert FakePanda.committed == 0


def test_existing_ack_does_not_hide_failed_rearm_of_responsive_panda(monkeypatch):
  class UnconfirmedPanda(FakePanda):
    def commit_wake_monitor(self, transaction: int):
      return {
        "magic": offline_wake.PANDA_WAKE_MONITOR_STATUS_MAGIC,
        "transaction": transaction,
        "state": offline_wake.PANDA_WAKE_MONITOR_PREPARED_STATE,
        "flags": offline_wake.PANDA_WAKE_MONITOR_STATUS_FLAG_RX_ARMED |
                 offline_wake.PANDA_WAKE_MONITOR_STATUS_FLAG_CAN_HEALTHY,
      }

  params = FakeParams(acknowledged=True)
  install_fakes(monkeypatch, params, UnconfirmedPanda)

  assert not hardware.request_internal_panda_wake_monitor()


def test_shutdown_rejects_panda_can_fault_before_commit(monkeypatch):
  class FaultedPanda(FakePanda):
    def health(self):
      return {"faults": 1 << 3, "fault_status": 1}

  params = FakeParams(acknowledged=True)
  FakePanda.committed = 0
  install_fakes(monkeypatch, params, FaultedPanda)

  assert not hardware.request_internal_panda_wake_monitor()
  assert FakePanda.committed == 0


def test_shutdown_rejects_rx_fifo_loss_before_commit(monkeypatch):
  class LostFramePanda(FakePanda):
    def can_health(self, can_number: int):
      health = super().can_health(can_number)
      health["total_rx_lost_cnt"] = 1 if can_number == 1 else 0
      return health

  params = FakeParams(acknowledged=True)
  FakePanda.committed = 0
  install_fakes(monkeypatch, params, LostFramePanda)

  assert not hardware.request_internal_panda_wake_monitor()
  assert FakePanda.committed == 0


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
