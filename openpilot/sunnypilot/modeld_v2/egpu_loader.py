import os
import threading
import time
from collections.abc import Callable, MutableMapping


# Measured on C3XL/UT3G: LM 71.50 s, BMV3 73.54 s, TT 74.66 s,
# and BMV2 75.58 s. Keep bounded margin for cold starts and USB scheduling.
C3XL_MODEL_LOAD_TIMEOUT = 120
C3XL_TINYGRAD_CACHE_HOME = "/data/cache"

class EgpuModelLoadError(RuntimeError):
  pass


def configure_default_device(comma_hardware: bool, environment: MutableMapping[str, str] = os.environ,
                             *, c3xl: bool = False) -> None:
  """Keep default-device probing off USB AMD and persist C3XL compiler caches."""
  if comma_hardware:
    environment.setdefault("DEV", "QCOM")
  if c3xl:
    environment.setdefault("XDG_CACHE_HOME", C3XL_TINYGRAD_CACHE_HOME)


def load_with_timeout[T](load: Callable[[], T], timeout: float) -> T:
  result: list[T] = []
  error: list[Exception] = []
  done = threading.Event()

  def run() -> None:
    try:
      result.append(load())
    except Exception as exception:
      error.append(exception)
    finally:
      done.set()

  threading.Thread(target=run, name="chestnut-model-loader", daemon=True).start()
  if not done.wait(timeout):
    raise TimeoutError(f"Chestnut model load timed out after {timeout:g}s")
  if error:
    raise EgpuModelLoadError(f"Chestnut model load failed: {error[0]}") from error[0]
  return result[0]


def wait_for_link(link_up: Callable[[], bool], attempts: int = 10,
                  delay_fn: Callable[[float], None] = time.sleep) -> bool:
  if attempts < 1:
    raise ValueError("attempts must be positive")
  for attempt in range(attempts):
    if link_up():
      return True
    if attempt + 1 < attempts:
      delay_fn(1.0)
  return False
