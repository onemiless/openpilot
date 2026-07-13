import os
import time


OFFLINE_WAKE_DEBUG_LOG = "/data/offline_wake_debug.log"
PANDA_BOOTKICK_TEST_SENTINEL = "/data/panda_bootkick_test_pending"
PANDA_BOOTKICK_TEST_TTL = 10 * 60


def offline_wake_debug_log(process: str, message: str) -> None:
  try:
    with open(OFFLINE_WAKE_DEBUG_LOG, "a") as f:
      f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {process} {message}\n")
  except Exception:
    pass


def panda_bootkick_test_pending() -> bool:
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
