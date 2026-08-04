import os

from openpilot.system.hardware import offline_wake


class FakeParams:
  def __init__(self) -> None:
    self.removed: list[str] = []
    self.writes: list[tuple[str, bool, bool]] = []

  def remove(self, key: str) -> None:
    self.removed.append(key)

  def put_bool(self, key: str, value: bool, block: bool = False) -> None:
    self.writes.append((key, value, block))


def test_shutdown_gate_requires_continuous_quiet_period() -> None:
  gate = offline_wake.CanShutdownGate(quiet_s=5.0, now=10.0)

  assert not gate.ready(now=14.9)
  assert gate.ready(now=15.0)

  gate.update(active=True, now=16.0)
  assert not gate.ready(now=20.9)
  assert gate.ready(now=21.0)


def test_shutdown_gate_force_bypasses_quiet_period() -> None:
  gate = offline_wake.CanShutdownGate(quiet_s=300.0, now=100.0)

  assert gate.ready(force=True, now=100.0)


def test_acknowledge_wake_monitor_replaces_request_with_blocking_ack() -> None:
  params = FakeParams()

  offline_wake.acknowledge_panda_wake_monitor(params)

  assert params.removed == ["PandaWakeMonitorRequest"]
  assert params.writes == [("PandaWakeMonitorAck", True, True)]


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
