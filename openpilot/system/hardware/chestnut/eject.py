#!/usr/bin/env python3
"""Prepare a Chestnut-connected eGPU for physical removal while offroad."""
import argparse
import json
import os
import sys
import time
from pathlib import Path

from openpilot.system.hardware.chestnut.flash import VBUS_PATH, claim_interface, find_runtime_chestnut


DETACH_TIMEOUT = 20.0
DETACH_PENDING_EXIT_CODE = 75  # EX_TEMPFAIL: the accepted USB remove is still converging
RECOVERY_DISCONNECT_TIMEOUT = 5.0
RECOVERY_ENUM_TIMEOUT = 15.0
RECOVERY_VBUS_OFF_TIME = 2.0


class DetachPendingError(RuntimeError):
  pass


def _wait_disconnected(timeout: float = DETACH_TIMEOUT) -> bool:
  deadline = time.monotonic() + timeout
  while time.monotonic() < deadline:
    path, _, _ = find_runtime_chestnut()
    if path is None:
      return True
    time.sleep(0.1)
  return False


def _runtime_speed_mbps() -> tuple[str | None, int]:
  path, _, _ = find_runtime_chestnut()
  if path is None:
    return None, 0
  try:
    return path, int((Path(path) / "speed").read_text())
  except (OSError, ValueError):
    return path, 0


def recover_low_speed_link() -> dict[str, object]:
  """Power-cycle a runtime device that fell back below SuperSpeed.

  The caller owns the offroad/no-user qualification. This helper deliberately
  does not claim the interface: offroad chestnut_statusd may have it open, and
  the VBUS transition is the operation required to reset the failed USB link.
  """
  path, speed_before = _runtime_speed_mbps()
  if path is None:
    raise RuntimeError("eGPU is not connected")
  if speed_before >= 5000:
    return {"state": "already-ready", "speed_before": speed_before, "speed_after": speed_before}

  vbus = Path(VBUS_PATH)
  if not vbus.exists():
    raise RuntimeError("eGPU VBUS control is unavailable")

  disconnected = False
  try:
    vbus.write_text("0\n")
    disconnected = _wait_disconnected(RECOVERY_DISCONNECT_TIMEOUT)
    time.sleep(RECOVERY_VBUS_OFF_TIME)
  finally:
    vbus.write_text("1\n")

  deadline = time.monotonic() + RECOVERY_ENUM_TIMEOUT
  speed_after = 0
  while time.monotonic() < deadline:
    _, speed_after = _runtime_speed_mbps()
    if speed_after >= 5000:
      return {
        "state": "recovered", "disconnected": disconnected,
        "speed_before": speed_before, "speed_after": speed_after,
      }
    time.sleep(0.2)
  raise RuntimeError(f"eGPU re-enumerated below SuperSpeed ({speed_after} Mbps)")


def safe_eject() -> bool:
  """Exclusively claim Chestnut, then power it down when VBUS is controllable.

  Returns whether VBUS was switched off. On externally powered C3XL adapters a
  False return means the bridge is idle and safe for the user to unplug. Do not
  write the device's sysfs ``remove`` node: an ASM2464 that remains externally
  powered may not re-enumerate after that host-only detach until its power is
  physically cycled.
  """
  path, _, _ = find_runtime_chestnut()
  if path is None:
    raise RuntimeError("eGPU is not connected")

  # Claiming the interface is the safety barrier. It fails with EBUSY if modeld,
  # a compiler, or a diagnostic process is still using the bridge.
  fd = claim_interface(path)
  os.close(fd)

  vbus = Path(VBUS_PATH)
  powered_off = vbus.exists()
  if powered_off:
    vbus.write_text("0\n")
    if not _wait_disconnected():
      raise DetachPendingError("eGPU detach is still pending")
  return powered_off


def main() -> int:
  parser = argparse.ArgumentParser(description="safely detach the Chestnut eGPU")
  parser.add_argument("--recover-low-speed", action="store_true")
  args = parser.parse_args()
  if args.recover_low_speed:
    try:
      from openpilot.common.params import Params
      if not Params().get_bool("IsOffroad"):
        raise RuntimeError("low-speed recovery requires offroad confirmation")
      print(json.dumps(recover_low_speed_link(), sort_keys=True), flush=True)
      return 0
    except Exception as e:
      print(e, file=sys.stderr, flush=True)
      return 1
  try:
    powered_off = safe_eject()
  except DetachPendingError as e:
    print(e, file=sys.stderr, flush=True)
    return DETACH_PENDING_EXIT_CODE
  print("powered-off" if powered_off else "safe-to-unplug", flush=True)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
