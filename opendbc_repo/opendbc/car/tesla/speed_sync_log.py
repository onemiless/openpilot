import json
import logging
import os
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from openpilot.system.hardware.hw import Paths


LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 10


def get_speed_sync_logger() -> logging.Logger:
  logger = logging.getLogger("tesla.speed_sync")
  if getattr(logger, "_speed_sync_configured", False):
    return logger

  logger.setLevel(logging.DEBUG)
  logger.propagate = False
  root = Path(os.environ.get("TESLA_SPEED_SYNC_LOG_ROOT", Paths.swaglog_root()))
  path = root / "tesla_speed_sync" / "speed_sync.jsonl"
  try:
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT, delay=True)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
  except OSError:
    logger.addHandler(logging.NullHandler())
  logger._speed_sync_configured = True
  return logger


def log_speed_sync(logger: logging.Logger, event: str, *, warning: bool = False, **values) -> None:
  payload = {"event": event, "wall_time_ns": time.time_ns(), **values}
  message = json.dumps(payload, separators=(",", ":"), sort_keys=True, default=str)
  (logger.warning if warning else logger.info)(message)
