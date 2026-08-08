import fcntl
import os
import time
from collections.abc import Generator
from contextlib import contextmanager


OFFLINE_WAKE_DEBUG_LOG = "/data/offline_wake_debug.log"
PANDA_BOOTKICK_TEST_SENTINEL = "/data/panda_bootkick_test_pending"
PANDA_BOOTKICK_TEST_TTL = 10 * 60
OFFLINE_WAKE_CAN_BUSES = (0, 1, 2)
PANDA_WAKE_DEBUG_MAGIC = 0x57414B48
PANDA_WAKE_MONITOR_ARMED_STAGE = 0x30


class CanActivityTracker:
  """Record sleeping-vehicle CAN for diagnostics without blocking shutdown."""
  def __init__(self, now: float | None = None) -> None:
    current_time = time.monotonic() if now is None else now
    self.frame_counts: dict[int, int] = dict.fromkeys(OFFLINE_WAKE_CAN_BUSES, 0)
    self.last_activity: dict[int, float] = dict.fromkeys(OFFLINE_WAKE_CAN_BUSES, current_time)

  def update(self, can_messages, now: float | None = None) -> None:
    current_time = time.monotonic() if now is None else now
    for message in can_messages:
      bus = int(message.src)
      if bus in self.frame_counts:
        self.frame_counts[bus] += 1
        self.last_activity[bus] = current_time

  def snapshot(self, now: float | None = None) -> dict[int, dict[str, float | int]]:
    current_time = time.monotonic() if now is None else now
    return {
      bus: {
        "frames": self.frame_counts[bus],
        "last_activity_s": max(0.0, current_time - self.last_activity[bus]),
      }
      for bus in OFFLINE_WAKE_CAN_BUSES
    }


def wake_can_activity(can_messages) -> bool:
  """Ignore Panda echo buses and track the three physical vehicle CAN buses."""
  return any(int(message.src) in OFFLINE_WAKE_CAN_BUSES for message in can_messages)


def acknowledge_panda_wake_monitor(params) -> None:
  params.remove("PandaWakeMonitorRequest")
  params.put_bool("PandaWakeMonitorAck", True, block=True)


def panda_wake_monitor_ready(wake_debug: dict | None) -> bool:
  return wake_debug is not None and wake_debug.get("magic") == PANDA_WAKE_DEBUG_MAGIC \
    and wake_debug.get("stage") == PANDA_WAKE_MONITOR_ARMED_STAGE


@contextmanager
def _panda_bootkick_test_lock() -> Generator[None, None, None]:
  lock_path = f"{PANDA_BOOTKICK_TEST_SENTINEL}.lock"
  fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
  try:
    fcntl.flock(fd, fcntl.LOCK_EX)
    yield
  finally:
    fcntl.flock(fd, fcntl.LOCK_UN)
    os.close(fd)


def offline_wake_debug_log(process: str, message: str) -> None:
  try:
    with open(OFFLINE_WAKE_DEBUG_LOG, "a") as f:
      f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {process} {message}\n")
  except Exception:
    pass


def panda_bootkick_test_pending() -> bool:
  try:
    with _panda_bootkick_test_lock():
      try:
        mtime = os.path.getmtime(PANDA_BOOTKICK_TEST_SENTINEL)
        if (time.time_ns() / 1e9) - mtime <= PANDA_BOOTKICK_TEST_TTL:
          return True
        os.remove(PANDA_BOOTKICK_TEST_SENTINEL)
      except FileNotFoundError:
        pass
  except Exception:
    pass
  return False


def clear_panda_bootkick_test_sentinel() -> bool:
  try:
    with _panda_bootkick_test_lock():
      try:
        os.remove(PANDA_BOOTKICK_TEST_SENTINEL)
        return True
      except FileNotFoundError:
        pass
  except Exception:
    pass
  return False
