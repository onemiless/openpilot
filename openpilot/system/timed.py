#!/usr/bin/env python3
import datetime
import subprocess
import time
from typing import NoReturn

import openpilot.cereal.messaging as messaging
from openpilot.common.time_helpers import min_date, MAX_DATE, system_time_valid
from openpilot.common.swaglog import cloudlog
from openpilot.common.params import Params
from openpilot.common.gps import get_gps_location_service


LAST_KNOWN_TIME_PARAM = "LastKnownGoodTime"
LAST_KNOWN_TIME_FALLBACK_PARAMS = (LAST_KNOWN_TIME_PARAM, "LastUpdateTime")
LAST_KNOWN_TIME_WRITE_INTERVAL = datetime.timedelta(hours=6)
LAST_KNOWN_TIME_CHECK_INTERVAL_S = 5 * 60


def _normalize_datetime(value) -> datetime.datetime | None:
  if not isinstance(value, datetime.datetime):
    return None
  if value.tzinfo is not None:
    return value.astimezone(datetime.UTC).replace(tzinfo=None)
  return value


def _valid_persisted_time(value) -> datetime.datetime | None:
  value = _normalize_datetime(value)
  return value if value is not None and min_date() < value < MAX_DATE else None


def set_time(new_time):
  diff = datetime.datetime.now(datetime.UTC).replace(tzinfo=None) - new_time
  if abs(diff) < datetime.timedelta(seconds=10):
    cloudlog.debug(f"Time diff too small: {diff}")
    return

  cloudlog.debug(f"Setting time to {new_time}")
  try:
    subprocess.run(["sudo", "date", "-u", "-s", new_time.strftime("%Y-%m-%d %H:%M:%S")], check=True)
  except subprocess.CalledProcessError:
    cloudlog.exception("timed.failed_setting_time")


def restore_persisted_time(params: Params) -> bool:
  if system_time_valid():
    return False

  candidates = [_valid_persisted_time(params.get(key)) for key in LAST_KNOWN_TIME_FALLBACK_PARAMS]
  restore_time = max((candidate for candidate in candidates if candidate is not None), default=None)
  if restore_time is None:
    cloudlog.warning("No valid persisted wall clock is available")
    return False

  cloudlog.warning(f"Restoring invalid system clock from persisted time {restore_time}")
  set_time(restore_time)
  return True


def persist_known_good_time(params: Params, now: datetime.datetime | None = None) -> bool:
  if not system_time_valid():
    return False

  now = _normalize_datetime(now or datetime.datetime.now())
  if now is None or not min_date() < now < MAX_DATE:
    return False

  previous = _valid_persisted_time(params.get(LAST_KNOWN_TIME_PARAM))
  if previous is not None and now - previous < LAST_KNOWN_TIME_WRITE_INTERVAL:
    return False

  params.put(LAST_KNOWN_TIME_PARAM, now, block=False)
  return True


def main() -> NoReturn:
  """
    timed has two responsibilities:
    - getting the current time from GPS
    - publishing the time in the logs

    AGNOS will also use NTP to update the time.
  """

  params = Params()
  restore_persisted_time(params)
  gps_location_service = get_gps_location_service(params)

  pm = messaging.PubMaster(['clocks'])
  sm = messaging.SubMaster([gps_location_service])
  next_persist_check = 0.0
  while True:
    sm.update(1000)

    if time.monotonic() >= next_persist_check:
      persist_known_good_time(params)
      next_persist_check = time.monotonic() + LAST_KNOWN_TIME_CHECK_INTERVAL_S

    msg = messaging.new_message('clocks')
    msg.valid = system_time_valid()
    msg.clocks.wallTimeNanos = time.time_ns()
    pm.send('clocks', msg)

    gps = sm[gps_location_service]
    gps_time = datetime.datetime.fromtimestamp(gps.unixTimestampMillis / 1000., datetime.UTC).replace(tzinfo=None)
    if not sm.updated[gps_location_service] or (time.monotonic() - sm.logMonoTime[gps_location_service] / 1e9) > 2.0:
      continue
    if not gps.hasFix:
      continue
    if gps_time < min_date() or gps_time > MAX_DATE:
      continue

    set_time(gps_time)
    time.sleep(10)

if __name__ == "__main__":
  main()
