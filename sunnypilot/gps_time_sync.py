#!/usr/bin/env python3
"""
GPS time sync — sets system clock from GPS on first fix after boot.
Runs once then exits.
"""

import subprocess
import time
from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog

import cereal.messaging as messaging

# Prefer gpsLocationExternal (u-blox), fall back to gpsLocation
SERVICES = ["gpsLocationExternal", "gpsLocation"]


def set_system_time(unix_seconds: int) -> bool:
  try:
    subprocess.run(
      ["sudo", "date", "-s", f"@{unix_seconds}"],
      check=True, capture_output=True, timeout=5,
    )
    return True
  except Exception as e:
    cloudlog.warning(f"GPS time sync: failed to set system time: {e}")
    return False


def main():
  params = Params()

  # Skip if time already reasonable (previously synced or kept by RTC)
  if time.time() > 1740000000:  # roughly mid-Feb 2025
    return

  # Skip if already attempted this boot (param cleared on manager start)
  if params.get_bool("GpsTimeSyncDone"):
    return

  socks = {s: messaging.sub_sock(s, timeout=100) for s in SERVICES}

  cloudlog.info("GPS time sync: waiting for GPS fix...")

  start = time.monotonic()
  while time.monotonic() - start < 300:  # 5 minute timeout
    for name, sock in socks.items():
      for event in messaging.drain_sock(sock):
        gps = getattr(event, name, None)
        if gps is None:
          continue

        # Valid fix: non-zero coordinates
        if gps.latitude == 0.0 and gps.longitude == 0.0:
          continue

        ts_ms = gps.unixTimestampMillis
        if not ts_ms or ts_ms <= 0:
          continue

        ts_s = int(ts_ms // 1000)
        # Sanity: must be between Jan 2025 and Jan 2035
        if ts_s < 1735689600 or ts_s > 2051222400:
          continue

        cloudlog.info(f"GPS time sync: got fix from {name}, "
                      f"timestamp={ts_s} ({time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(ts_s))} UTC)")

        if set_system_time(ts_s):
          params.put_bool_nonblocking("GpsTimeSyncDone", True)
          cloudlog.info("GPS time sync: system clock set successfully")
          return

    time.sleep(1.0)

  cloudlog.warning("GPS time sync: timed out waiting for GPS fix")


if __name__ == "__main__":
  main()
