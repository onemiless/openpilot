#!/usr/bin/env python3
import datetime
import socket
import struct
import subprocess
import time
from typing import NoReturn

import cereal.messaging as messaging
from openpilot.common.time_helpers import min_date, MAX_DATE, system_time_valid
from openpilot.common.swaglog import cloudlog
from openpilot.common.params import Params
from openpilot.common.gps import get_gps_location_service

ALIYUN_NTP_HOST = "ntp.aliyun.com"
NTP_PORT = 123
NTP_TIMEOUT = 5.0
NTP_PACKET_DELTA = 2208988800
NTP_SYNC_INTERVAL = 60.0
NTP_INITIAL_RETRY_INTERVAL = 10.0
GPS_STALE_SECONDS = 2.0


def set_time(new_time):
  diff = datetime.datetime.now(datetime.UTC).replace(tzinfo=None) - new_time
  if abs(diff) < datetime.timedelta(seconds=10):
    cloudlog.debug(f"Time diff too small: {diff}")
    return

  cloudlog.debug(f"Setting time to {new_time}")
  try:
    subprocess.run(f"TZ=UTC date -s '{new_time}'", shell=True, check=True)
  except subprocess.CalledProcessError:
    cloudlog.exception("timed.failed_setting_time")


def get_ntp_time(host: str = ALIYUN_NTP_HOST) -> datetime.datetime | None:
  msg = b'\x1b' + 47 * b'\0'
  try:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
      sock.settimeout(NTP_TIMEOUT)
      sock.sendto(msg, (host, NTP_PORT))
      data, _ = sock.recvfrom(48)
  except OSError:
    cloudlog.exception("timed.failed_fetching_aliyun_time")
    return None

  if len(data) < 48:
    cloudlog.warning("timed.aliyun_time_short_response")
    return None

  seconds, fraction = struct.unpack("!II", data[40:48])
  unix_seconds = seconds - NTP_PACKET_DELTA + fraction / 2**32
  new_time = datetime.datetime.fromtimestamp(unix_seconds, datetime.UTC).replace(tzinfo=None)
  if new_time < min_date() or new_time > MAX_DATE:
    cloudlog.warning(f"timed.aliyun_time_invalid: {new_time}")
    return None

  return new_time


def maybe_sync_from_ntp(last_ntp_attempt: float) -> float:
  now = time.monotonic()
  ntp_retry_interval = NTP_SYNC_INTERVAL if system_time_valid() else NTP_INITIAL_RETRY_INTERVAL
  if now - last_ntp_attempt < ntp_retry_interval:
    return last_ntp_attempt

  ntp_time = get_ntp_time()
  if ntp_time is not None:
    set_time(ntp_time)

  return now


def main() -> NoReturn:
  """
    timed has two responsibilities:
    - getting the current time from GPS
    - publishing the time in the logs

    AGNOS will also use NTP to update the time. If GPS is unavailable, timed
    falls back to Aliyun NTP when the network is reachable.
  """

  params = Params()
  gps_location_service = get_gps_location_service(params)
  last_ntp_attempt = -NTP_INITIAL_RETRY_INTERVAL

  pm = messaging.PubMaster(['clocks'])
  sm = messaging.SubMaster([gps_location_service])
  while True:
    sm.update(1000)

    msg = messaging.new_message('clocks')
    msg.valid = system_time_valid()
    msg.clocks.wallTimeNanos = time.time_ns()
    pm.send('clocks', msg)

    gps = sm[gps_location_service]
    gps_time = datetime.datetime.fromtimestamp(gps.unixTimestampMillis / 1000., datetime.UTC).replace(tzinfo=None)
    gps_fresh = sm.updated[gps_location_service] and (time.monotonic() - sm.logMonoTime[gps_location_service] / 1e9) <= GPS_STALE_SECONDS
    if not gps_fresh:
      last_ntp_attempt = maybe_sync_from_ntp(last_ntp_attempt)
      continue
    if not gps.hasFix:
      last_ntp_attempt = maybe_sync_from_ntp(last_ntp_attempt)
      continue
    if gps_time < min_date() or gps_time > MAX_DATE:
      continue

    set_time(gps_time)
    time.sleep(10)

if __name__ == "__main__":
  main()
