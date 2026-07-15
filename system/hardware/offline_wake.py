import fcntl
import os
import time
from collections.abc import Generator
from contextlib import contextmanager


OFFLINE_WAKE_DEBUG_LOG = "/data/offline_wake_debug.log"
PANDA_BOOTKICK_TEST_SENTINEL = "/data/panda_bootkick_test_pending"
PANDA_BOOTKICK_TEST_TTL = 10 * 60
OFFLINE_SHUTDOWN_CAN_QUIET_S = 10.0
OFFLINE_SHUTDOWN_CAN_MAX_WAIT_S = 30.0


class CanShutdownGate:
  def __init__(self, quiet_s: float = OFFLINE_SHUTDOWN_CAN_QUIET_S,
               max_wait_s: float = OFFLINE_SHUTDOWN_CAN_MAX_WAIT_S, now: float | None = None) -> None:
    self.quiet_s = quiet_s
    self.max_wait_s = max_wait_s
    self.last_activity = time.monotonic() if now is None else now
    self.requested_since: float | None = None

  def update(self, active: bool, now: float | None = None) -> None:
    if active:
      self.last_activity = time.monotonic() if now is None else now

  def reset_request(self) -> None:
    self.requested_since = None

  def quiet_duration(self, now: float | None = None) -> float:
    current_time = time.monotonic() if now is None else now
    return max(0.0, current_time - self.last_activity)

  def wait_duration(self, now: float | None = None) -> float:
    if self.requested_since is None:
      return 0.0
    current_time = time.monotonic() if now is None else now
    return max(0.0, current_time - self.requested_since)

  def ready(self, force: bool = False, now: float | None = None) -> bool:
    current_time = time.monotonic() if now is None else now
    if self.requested_since is None:
      self.requested_since = current_time
    quiet = self.quiet_duration(current_time) >= self.quiet_s
    wait_expired = self.wait_duration(current_time) >= self.max_wait_s
    return force or quiet or wait_expired


def acknowledge_panda_wake_monitor(params) -> None:
  params.remove("PandaWakeMonitorRequest")
  params.put_bool("PandaWakeMonitorAck", True, block=True)


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
