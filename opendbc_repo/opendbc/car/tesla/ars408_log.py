import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from openpilot.system.hardware.hw import Paths


ARS408_LOG_DIRECTORY = "ars408"
ARS408_DEBUG_LOG_FILENAME = "ars408_debug.log"
ARS408_ERROR_LOG_FILENAME = "ars408_error.log"
ARS408_LOG_MAX_BYTES = 2 * 1024 * 1024
ARS408_LOG_BACKUP_COUNT = 10


class _BelowWarningFilter(logging.Filter):
  def filter(self, record: logging.LogRecord) -> bool:
    return record.levelno < logging.WARNING


def ars408_log_paths() -> tuple[Path, Path]:
  root = os.environ.get("ARS408_LOG_ROOT", Paths.swaglog_root())
  log_directory = Path(root) / ARS408_LOG_DIRECTORY
  return log_directory / ARS408_DEBUG_LOG_FILENAME, log_directory / ARS408_ERROR_LOG_FILENAME


def get_ars408_logger() -> logging.Logger:
  logger = logging.getLogger("ars408")
  if getattr(logger, "_ars408_configured", False):
    return logger

  logger.setLevel(logging.DEBUG)
  logger.propagate = False

  debug_log_path, error_log_path = ars408_log_paths()
  try:
    debug_log_path.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
      "%(asctime)s.%(msecs)03d %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S",
    )

    debug_handler = RotatingFileHandler(
      debug_log_path, maxBytes=ARS408_LOG_MAX_BYTES, backupCount=ARS408_LOG_BACKUP_COUNT, delay=True,
    )
    debug_handler.setLevel(logging.DEBUG)
    debug_handler.addFilter(_BelowWarningFilter())
    debug_handler.setFormatter(formatter)
    logger.addHandler(debug_handler)

    error_handler = RotatingFileHandler(
      error_log_path, maxBytes=ARS408_LOG_MAX_BYTES, backupCount=ARS408_LOG_BACKUP_COUNT, delay=True,
    )
    error_handler.setLevel(logging.WARNING)
    error_handler.setFormatter(formatter)
    logger.addHandler(error_handler)
  except OSError:
    # Radar operation must not fail only because its diagnostic storage is unavailable.
    logger.addHandler(logging.NullHandler())

  logger._ars408_configured = True
  return logger


ars408_log = get_ars408_logger()
