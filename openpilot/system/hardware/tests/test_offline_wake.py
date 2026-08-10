import os
from pathlib import Path
from types import SimpleNamespace

from panda import Panda

from openpilot.system.hardware import offline_wake
from openpilot.system.hardware import hardwared


class FakeParams:
  def __init__(self) -> None:
    self.removed: list[str] = []
    self.writes: list[tuple[str, object, bool]] = []
    self.values: dict[str, object] = {}

  def remove(self, key: str) -> None:
    self.removed.append(key)

  def put_bool(self, key: str, value: bool, block: bool = False) -> None:
    self.writes.append((key, value, block))
    self.values[key] = value

  def put(self, key: str, value, block: bool = False) -> None:
    self.writes.append((key, value, block))
    self.values[key] = value

  def get(self, key: str):
    return self.values.get(key)


def panda_state(*, counts=(0, 0, 0), uptime=1, faults=(), power_save_enabled=False,
                bus_off=(False, False, False), error_passive=(False, False, False)):
  can_states = [
    SimpleNamespace(totalRxCnt=count, busOff=off, errorPassive=passive)
    for count, off, passive in zip(counts, bus_off, error_passive, strict=True)
  ]
  return SimpleNamespace(
    uptime=uptime,
    faults=faults,
    powerSaveEnabled=power_save_enabled,
    canState0=can_states[0],
    canState1=can_states[1],
    canState2=can_states[2],
  )


def test_shutdown_path_uses_strict_can_gate() -> None:
  shutdown_path = Path(hardwared.__file__).read_text().split("# Check if we need to shut down", 1)[1].split(
    "msg.deviceState.started", 1
  )[0]

  assert "if shutdown_requested:" in shutdown_path
  assert "can_shutdown_gate.ready" in shutdown_path


def test_can_shutdown_gate_requires_300_seconds_of_zero_rx() -> None:
  gate = offline_wake.CanShutdownGate(quiet_s=300.0, max_sample_age_s=1000.0)

  # The captured low-rate plateau is still active CAN and must continually
  # reset the shutdown timer, regardless of ignition/offroad state.
  gate.update([panda_state(counts=(100, 1000, 100), uptime=100)], now=0.0)
  gate.update([panda_state(counts=(288, 2936, 288), uptime=101)], now=1.0)
  gate.update([panda_state(counts=(476, 4872, 476), uptime=102)], now=2.0)
  assert not gate.ready(now=301.0)

  # Once every decoded physical source is truly quiet, 299.999 seconds is not
  # enough and 300 seconds is sufficient.
  gate.update([panda_state(counts=(477, 4873, 477), uptime=103)], now=3.0)
  assert not gate.ready(now=302.999)
  gate.update([panda_state(counts=(477, 4873, 477), uptime=403)], now=303.0)
  assert gate.ready(now=303.0)


def test_can_shutdown_gate_resets_on_any_physical_frame_fault_or_panda_reset() -> None:
  gate = offline_wake.CanShutdownGate(quiet_s=300.0, max_sample_age_s=1000.0)
  gate.update([panda_state(counts=(10, 20, 10), uptime=100)], now=0.0)
  gate.update([panda_state(counts=(10, 20, 10), uptime=400)], now=300.0)
  assert gate.ready(now=300.0)

  gate.update([panda_state(counts=(10, 21, 10), uptime=401)], now=301.0)
  assert not gate.ready(now=301.0)
  gate.update([panda_state(counts=(10, 21, 10), uptime=701, faults=("interruptRateCan2",))], now=601.0)
  assert not gate.ready(now=601.0)
  gate.update([panda_state(counts=(0, 0, 0), uptime=1)], now=602.0)
  assert not gate.ready(now=602.0)


def test_can_shutdown_gate_requires_all_rx_enabled_and_fresh_health() -> None:
  gate = offline_wake.CanShutdownGate(quiet_s=300.0, max_sample_age_s=1000.0)
  gate.update([panda_state(power_save_enabled=True)], now=0.0)
  gate.update([panda_state(power_save_enabled=True, uptime=301)], now=300.0)
  assert not gate.ready(now=300.0)

  gate.update([panda_state(uptime=302)], now=301.0)
  gate.update([panda_state(uptime=602)], now=601.0)
  assert gate.ready(now=601.0)

  fresh_gate = offline_wake.CanShutdownGate(quiet_s=1.0, max_sample_age_s=2.0)
  fresh_gate.update([panda_state()], now=0.0)
  assert not fresh_gate.ready(now=3.0)


def test_wake_can_activity_covers_all_physical_vehicle_buses() -> None:
  class CanMessage:
    def __init__(self, src: int):
      self.src = src

  for src in (0, 1, 2):
    assert offline_wake.wake_can_activity([CanMessage(src)])

  assert not offline_wake.wake_can_activity([CanMessage(128), CanMessage(129), CanMessage(130)])
  assert not offline_wake.wake_can_activity([])


def test_can_activity_diagnostics_track_each_physical_bus() -> None:
  class CanMessage:
    def __init__(self, src: int):
      self.src = src

  tracker = offline_wake.CanActivityTracker(now=10.0)
  tracker.update([CanMessage(0), CanMessage(0), CanMessage(2), CanMessage(129)], now=12.0)

  assert tracker.snapshot(now=15.0) == {
    0: {"frames": 2, "last_activity_s": 3.0},
    1: {"frames": 0, "last_activity_s": 5.0},
    2: {"frames": 1, "last_activity_s": 3.0},
  }


def test_acknowledge_wake_monitor_replaces_request_with_blocking_ack() -> None:
  params = FakeParams()

  offline_wake.acknowledge_panda_wake_monitor(params, 0x12345678)

  assert params.removed == ["PandaWakeMonitorRequest"]
  assert params.writes == [("PandaWakeMonitorAck", "12345678", True)]


def test_wake_monitor_ack_requires_the_current_transaction() -> None:
  params = FakeParams()
  params.values["PandaWakeMonitorAck"] = "12345678"

  assert offline_wake.panda_wake_monitor_acknowledged(params, 0x12345678)
  assert not offline_wake.panda_wake_monitor_acknowledged(params, 0x87654321)


def test_wake_monitor_ready_requires_firmware_magic_and_armed_stage() -> None:
  ready = {"magic": offline_wake.PANDA_WAKE_DEBUG_MAGIC, "stage": offline_wake.PANDA_WAKE_MONITOR_ARMED_STAGE}

  assert offline_wake.panda_wake_monitor_ready(ready)
  assert not offline_wake.panda_wake_monitor_ready({**ready, "stage": 0x31})
  assert not offline_wake.panda_wake_monitor_ready({**ready, "magic": 0})
  assert not offline_wake.panda_wake_monitor_ready(None)
  assert offline_wake.PANDA_WAKE_DEBUG_MAGIC == Panda.WAKE_DEBUG_MAGIC
  assert offline_wake.PANDA_WAKE_MONITOR_ARMED_STAGE == Panda.WAKE_MONITOR_ARMED_STAGE


def test_transaction_status_requires_exact_transaction_and_state() -> None:
  status = {
    "magic": offline_wake.PANDA_WAKE_MONITOR_STATUS_MAGIC,
    "transaction": 0x12345678,
    "state": offline_wake.PANDA_WAKE_MONITOR_PREPARED_STATE,
  }

  assert offline_wake.panda_wake_monitor_status_ready(
    status, 0x12345678, offline_wake.PANDA_WAKE_MONITOR_PREPARED_STATE
  )
  assert not offline_wake.panda_wake_monitor_status_ready(
    status, 0x87654321, offline_wake.PANDA_WAKE_MONITOR_PREPARED_STATE
  )
  assert not offline_wake.panda_wake_monitor_status_ready(
    status, 0x12345678, offline_wake.PANDA_WAKE_MONITOR_COMMITTED_STATE
  )


def test_debug_log_is_created_automatically(tmp_path, monkeypatch) -> None:
  log_path = tmp_path / "offline_wake_debug.log"
  monkeypatch.setattr(offline_wake, "OFFLINE_WAKE_DEBUG_LOG", str(log_path))

  offline_wake.offline_wake_debug_log("test", "wake monitor armed")

  assert log_path.exists()
  assert "test wake monitor armed" in log_path.read_text()


def test_hardwared_fallback_prepares_single_flight_transaction_without_synthetic_heartbeat(monkeypatch) -> None:
  import panda as panda_module

  events = []

  class RequestParams(FakeParams):
    pass

  class InternalPanda:
    @classmethod
    def list(cls):
      return ["internal"]

    def __init__(self, serial: str, disable_checks: bool):
      assert serial == "internal"
      assert not disable_checks

    def __enter__(self):
      return self

    def __exit__(self, exc_type, exc, traceback):
      return False

    def is_internal(self):
      return True

    def prepare_wake_monitor(self, transaction: int):
      events.append(("prepare", transaction))
      return {
        "magic": offline_wake.PANDA_WAKE_MONITOR_STATUS_MAGIC,
        "transaction": transaction,
        "state": offline_wake.PANDA_WAKE_MONITOR_PREPARED_STATE,
        "flags": offline_wake.PANDA_WAKE_MONITOR_STATUS_FLAG_RX_ARMED |
                 offline_wake.PANDA_WAKE_MONITOR_STATUS_FLAG_CAN_HEALTHY,
      }

  params = RequestParams()
  times = iter((0.0, 3.0))
  monkeypatch.setattr(hardwared, "Params", lambda: params)
  monkeypatch.setattr(hardwared, "panda_bootkick_test_pending", lambda: False)
  monkeypatch.setattr(hardwared.time, "monotonic", lambda: next(times))
  monkeypatch.setattr(panda_module, "Panda", InternalPanda)

  assert hardwared.request_panda_deepsleep(0x12345678)
  assert events == [("prepare", 0x12345678)]
  assert ("PandaWakeMonitorTxn", "12345678", True) in params.writes
  assert params.writes[-1] == ("PandaWakeMonitorAck", "12345678", True)


def test_recent_bootkick_sentinel_is_pending(tmp_path, monkeypatch) -> None:
  sentinel = tmp_path / "panda_bootkick_test_pending"
  sentinel.touch()
  monkeypatch.setattr(offline_wake, "PANDA_BOOTKICK_TEST_SENTINEL", str(sentinel))
  monkeypatch.setattr(offline_wake, "PANDA_BOOTKICK_TEST_TTL", 60.0)

  assert offline_wake.panda_bootkick_test_pending()
  assert sentinel.exists()


def test_expired_bootkick_sentinel_is_removed(tmp_path, monkeypatch) -> None:
  sentinel = tmp_path / "panda_bootkick_test_pending"
  sentinel.touch()
  os.utime(sentinel, (1.0, 1.0))
  monkeypatch.setattr(offline_wake, "PANDA_BOOTKICK_TEST_SENTINEL", str(sentinel))
  monkeypatch.setattr(offline_wake, "PANDA_BOOTKICK_TEST_TTL", 1.0)

  assert not offline_wake.panda_bootkick_test_pending()
  assert not sentinel.exists()
