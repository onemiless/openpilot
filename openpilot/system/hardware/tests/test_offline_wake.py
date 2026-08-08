import os
from pathlib import Path

from panda import Panda

from openpilot.system.hardware import offline_wake
from openpilot.system.hardware import hardwared


class FakeParams:
  def __init__(self) -> None:
    self.removed: list[str] = []
    self.writes: list[tuple[str, bool, bool]] = []

  def remove(self, key: str) -> None:
    self.removed.append(key)

  def put_bool(self, key: str, value: bool, block: bool = False) -> None:
    self.writes.append((key, value, block))


def test_shutdown_is_not_blocked_by_sleeping_vehicle_can() -> None:
  shutdown_path = Path(hardwared.__file__).read_text().split("# Check if we need to shut down", 1)[1].split(
    "msg.deviceState.started", 1
  )[0]

  assert "if shutdown_requested:" in shutdown_path
  assert "can_shutdown_gate.ready" not in shutdown_path


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

  offline_wake.acknowledge_panda_wake_monitor(params)

  assert params.removed == ["PandaWakeMonitorRequest"]
  assert params.writes == [("PandaWakeMonitorAck", True, True)]


def test_wake_monitor_ready_requires_firmware_magic_and_armed_stage() -> None:
  ready = {"magic": offline_wake.PANDA_WAKE_DEBUG_MAGIC, "stage": offline_wake.PANDA_WAKE_MONITOR_ARMED_STAGE}

  assert offline_wake.panda_wake_monitor_ready(ready)
  assert not offline_wake.panda_wake_monitor_ready({**ready, "stage": 0x31})
  assert not offline_wake.panda_wake_monitor_ready({**ready, "magic": 0})
  assert not offline_wake.panda_wake_monitor_ready(None)
  assert offline_wake.PANDA_WAKE_DEBUG_MAGIC == Panda.WAKE_DEBUG_MAGIC
  assert offline_wake.PANDA_WAKE_MONITOR_ARMED_STAGE == Panda.WAKE_MONITOR_ARMED_STAGE


def test_debug_log_is_created_automatically(tmp_path, monkeypatch) -> None:
  log_path = tmp_path / "offline_wake_debug.log"
  monkeypatch.setattr(offline_wake, "OFFLINE_WAKE_DEBUG_LOG", str(log_path))

  offline_wake.offline_wake_debug_log("test", "wake monitor armed")

  assert log_path.exists()
  assert "test wake monitor armed" in log_path.read_text()


def test_hardwared_fallback_reenables_heartbeat_before_arming(monkeypatch) -> None:
  import panda as panda_module

  events = []

  class RequestParams(FakeParams):
    def get_bool(self, key: str) -> bool:
      assert key == "PandaWakeMonitorAck"
      return False

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

    def send_heartbeat(self, engaged: bool, engaged_mads: bool):
      assert not engaged
      assert not engaged_mads
      events.append("heartbeat")

    def enable_deepsleep(self):
      events.append("arm")

    def wake_debug(self):
      return {"magic": offline_wake.PANDA_WAKE_DEBUG_MAGIC, "stage": offline_wake.PANDA_WAKE_MONITOR_ARMED_STAGE}

  params = RequestParams()
  times = iter((0.0, 3.0))
  monkeypatch.setattr(hardwared, "Params", lambda: params)
  monkeypatch.setattr(hardwared, "panda_bootkick_test_pending", lambda: False)
  monkeypatch.setattr(hardwared.time, "monotonic", lambda: next(times))
  monkeypatch.setattr(panda_module, "Panda", InternalPanda)

  assert hardwared.request_panda_deepsleep()
  assert events == ["heartbeat", "arm"]
  assert params.writes[-1] == ("PandaWakeMonitorAck", True, True)


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
