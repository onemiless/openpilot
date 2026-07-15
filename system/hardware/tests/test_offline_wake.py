import os
import time
from concurrent.futures import ThreadPoolExecutor

from openpilot.system.hardware import offline_wake


class FakeParams:
  def __init__(self):
    self.removed = []
    self.written = []

  def remove(self, key):
    self.removed.append(key)

  def put_bool(self, key, value, block=False):
    self.written.append((key, value, block))


def test_acknowledge_panda_wake_monitor():
  params = FakeParams()

  offline_wake.acknowledge_panda_wake_monitor(params)

  assert params.removed == ["PandaWakeMonitorRequest"]
  assert params.written == [("PandaWakeMonitorAck", True, True)]


def test_offline_wake_debug_log(tmp_path, monkeypatch):
  log_path = tmp_path / "offline_wake_debug.log"
  monkeypatch.setattr(offline_wake, "OFFLINE_WAKE_DEBUG_LOG", str(log_path))

  offline_wake.offline_wake_debug_log("test-process", "wake event")

  assert log_path.read_text().endswith(" test-process wake event\n")


def test_bootkick_test_pending_is_visible_to_all_checkers(tmp_path, monkeypatch):
  sentinel = tmp_path / "panda_bootkick_test_pending"
  sentinel.touch()
  monkeypatch.setattr(offline_wake, "PANDA_BOOTKICK_TEST_SENTINEL", str(sentinel))

  with ThreadPoolExecutor(max_workers=8) as executor:
    results = list(executor.map(lambda _: offline_wake.panda_bootkick_test_pending(), range(32)))

  assert all(results)
  assert sentinel.exists()


def test_expired_bootkick_test_sentinel_is_removed_once(tmp_path, monkeypatch):
  sentinel = tmp_path / "panda_bootkick_test_pending"
  sentinel.touch()
  expired = (time.time_ns() / 1e9) - offline_wake.PANDA_BOOTKICK_TEST_TTL - 1
  os.utime(sentinel, (expired, expired))
  monkeypatch.setattr(offline_wake, "PANDA_BOOTKICK_TEST_SENTINEL", str(sentinel))

  with ThreadPoolExecutor(max_workers=8) as executor:
    results = list(executor.map(lambda _: offline_wake.panda_bootkick_test_pending(), range(32)))

  assert not any(results)
  assert not sentinel.exists()


def test_clear_bootkick_test_sentinel_is_single_consumer(tmp_path, monkeypatch):
  sentinel = tmp_path / "panda_bootkick_test_pending"
  sentinel.touch()
  monkeypatch.setattr(offline_wake, "PANDA_BOOTKICK_TEST_SENTINEL", str(sentinel))

  with ThreadPoolExecutor(max_workers=8) as executor:
    results = list(executor.map(lambda _: offline_wake.clear_panda_bootkick_test_sentinel(), range(32)))

  assert results.count(True) == 1
  assert not sentinel.exists()
