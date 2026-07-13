import fcntl
import os
import time
from collections.abc import Generator
from contextlib import contextmanager


OFFLINE_WAKE_DEBUG_LOG = "/data/offline_wake_debug.log"
PANDA_BOOTKICK_TEST_SENTINEL = "/data/panda_bootkick_test_pending"
PANDA_BOOTKICK_TEST_TTL = 10 * 60


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
