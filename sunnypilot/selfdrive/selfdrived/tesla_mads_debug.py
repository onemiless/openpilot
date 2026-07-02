import json
import os
import threading
import time
from collections.abc import Mapping, Sequence


TESLA_MADS_DEBUG_PATH = "/data/tesla_mads_debug.log"
_MAX_LOG_BYTES = 1024 * 1024
_LOG_LOCK = threading.Lock()


def _safe_value(value):
  if isinstance(value, (str, int, float, bool)) or value is None:
    return value
  if isinstance(value, bytes):
    return value.hex()
  if isinstance(value, Mapping):
    return {str(k): _safe_value(v) for k, v in value.items()}
  if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
    return [_safe_value(v) for v in value]
  if hasattr(value, "to_dict"):
    try:
      return _safe_value(value.to_dict())
    except Exception:
      pass
  return str(value)


def _append_tesla_mads_debug(record: dict) -> None:
  try:
    with _LOG_LOCK:
      if os.path.exists(TESLA_MADS_DEBUG_PATH) and os.path.getsize(TESLA_MADS_DEBUG_PATH) > _MAX_LOG_BYTES:
        os.replace(TESLA_MADS_DEBUG_PATH, f"{TESLA_MADS_DEBUG_PATH}.1")
      with open(TESLA_MADS_DEBUG_PATH, "a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(_safe_value(record), sort_keys=True, default=str) + "\n")
  except OSError:
    pass


def log_tesla_mads_debug(source: str, event: str, *, sync: bool = False, **values) -> None:
  record = {
    "wall_time": time.time(),
    "monotonic_ns": time.monotonic_ns(),
    "source": source,
    "event": event,
    **values,
  }
  if sync:
    _append_tesla_mads_debug(record)
  else:
    threading.Thread(target=_append_tesla_mads_debug, args=(record,), daemon=True).start()


def clear_tesla_mads_debug_logs() -> None:
  for path in (TESLA_MADS_DEBUG_PATH, f"{TESLA_MADS_DEBUG_PATH}.1"):
    try:
      os.remove(path)
    except FileNotFoundError:
      pass
    except OSError:
      pass
