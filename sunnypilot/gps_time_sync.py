#!/usr/bin/env python3
"""
GPS time sync — sets system clock from GPS satellite time.
Performs an initial sync at boot, then periodically syncs every 2 minutes
to correct any clock drift.
"""

import subprocess
import time
from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog

import cereal.messaging as messaging

SYNC_INTERVAL = 120  # periodic sync every 2 minutes
INITIAL_FIX_TIMEOUT = 300  # 5 minute timeout for first GPS fix at boot
PERIODIC_FIX_TIMEOUT = 30  # 30 second timeout for periodic fixes
MIN_TIME_DIFF = 1.0  # minimum time difference (seconds) to trigger a clock update

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


def get_gps_timestamp(timeout: float) -> int | None:
  """Wait for a valid GPS fix and return the Unix timestamp in seconds, or None on timeout."""
  socks = {s: messaging.sub_sock(s, timeout=100) for s in SERVICES}
  start = time.monotonic()
  while time.monotonic() - start < timeout:
    for name, sock in socks.items():
      for event in messaging.drain_sock(sock):
        gps = getattr(event, name, None)
        if gps is None:
          continue

        # Valid fix requires non-zero coordinates
        if gps.latitude == 0.0 and gps.longitude == 0.0:
          continue

        ts_ms = gps.unixTimestampMillis
        if not ts_ms or ts_ms <= 0:
          continue

        ts_s = int(ts_ms // 1000)
        # Sanity: must be between Jan 2025 and Jan 2035
        if ts_s < 1735689600 or ts_s > 2051222400:
          continue

        return ts_s

    time.sleep(1.0)

  return None


def main():
  params = Params()

  # Initial sync at boot — only needed if system clock is stale
  if time.time() < 1740000000 and not params.get_bool("GpsTimeSyncDone"):
    cloudlog.info("GPS time sync: system clock is stale, waiting for initial GPS fix...")
    ts = get_gps_timestamp(timeout=INITIAL_FIX_TIMEOUT)
    if ts is not None:
      cloudlog.info(f"GPS time sync: initial fix acquired, "
                    f"timestamp={ts} ({time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(ts))} UTC)")
      if set_system_time(ts):
        params.put_bool_nonblocking("GpsTimeSyncDone", True)
        cloudlog.info("GPS time sync: initial system clock set successfully")
    else:
      cloudlog.warning("GPS time sync: timed out waiting for initial GPS fix")

  # Periodic sync loop — runs every 2 minutes to correct clock drift
  while True:
    time.sleep(SYNC_INTERVAL)

    ts = get_gps_timestamp(timeout=PERIODIC_FIX_TIMEOUT)
    if ts is None:
      continue

    # Skip if system time is already accurate within threshold
    if abs(time.time() - ts) <= MIN_TIME_DIFF:
      continue

    cloudlog.info(f"GPS time sync: periodic sync, "
                  f"timestamp={ts} ({time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(ts))} UTC), "
                  f"drift={time.time() - ts:.1f}s")
    if set_system_time(ts):
      cloudlog.info("GPS time sync: system clock updated")


if __name__ == "__main__":
  main()
