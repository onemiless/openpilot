#!/usr/bin/env python3
"""Safely quiesce the C3XL USBGPU before cutting UT3G external power."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import time


PRODUCT = "custom ed4e39b7-CLEAN"
OFFICIAL_USB_IDS = ((0xADD1, 0x0001), (0x3801, 0x0001))
DUAL_USB_IDS = ((0xADD1, 0x0002),)
DUAL_PRODUCT_RE = re.compile(r"custom [0-9a-f]{8}-UT3G-DUAL")
LTSSM = 0xB450
PCIE_L0 = 0x78
IS_OFFROAD = Path("/data/params/d/IsOffroad")


class SafePowerOffError(RuntimeError):
  pass


def offroad_confirmed(path: Path = IS_OFFROAD) -> bool:
  try:
    return path.exists() and path.read_bytes().replace(b"\0", b"").strip() == b"1"
  except OSError:
    return False


def require_offroad(path: Path = IS_OFFROAD) -> None:
  if not offroad_confirmed(path):
    raise SafePowerOffError("C3XL is not confirmed offroad")


def conflicting_processes(proc_root: Path = Path("/proc")) -> list[dict]:
  conflicts = []
  for entry in proc_root.iterdir():
    if not entry.name.isdigit() or int(entry.name) == os.getpid():
      continue
    try:
      command = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", errors="replace").strip()
    except OSError:
      continue
    if any(marker in command for marker in ("modeld", "ModelState", "DEV=USB+AMD")):
      conflicts.append({"pid": int(entry.name), "command": command[:300]})
  return sorted(conflicts, key=lambda item: item["pid"])


def wait_for_gpu_users(*, proc_root: Path = Path("/proc"), offroad_path: Path = IS_OFFROAD,
                       sleeper=time.sleep) -> None:
  while True:
    require_offroad(offroad_path)
    if not conflicting_processes(proc_root):
      return
    sleeper(0.1)


def safe_power_off(usb, sleeper=time.sleep, before_f3=None, *, post_f3_samples: int = 4) -> dict:
  if post_f3_samples < 1:
    raise ValueError("post_f3_samples must be positive")
  if usb.product != PRODUCT and DUAL_PRODUCT_RE.fullmatch(usb.product) is None:
    raise SafePowerOffError(f"unexpected product {usb.product!r}")
  before = bytes(usb.control_read(0xE4, 1, value=LTSSM, timeout=2000))[0]
  if before != PCIE_L0:
    return {
      "schema": "ut3g-safe-f3-poweroff-v1",
      "state": "already-not-l0",
      "ltssm_before": before,
      "ltssm_after": before,
      "f3_writes": 0,
      "persistent_writes": 0,
      "safe_to_cut_external_power": True,
    }
  if before_f3 is not None:
    before_f3()
  usb.control_write(0xF3, value=0, timeout=10_000)
  samples = []
  for index in range(post_f3_samples):
    samples.append(bytes(usb.control_read(0xE4, 1, value=LTSSM, timeout=2000))[0])
    if index + 1 < post_f3_samples:
      sleeper(1.0)
  if PCIE_L0 in samples:
    raise SafePowerOffError(f"PCIe returned to L0 during verification: {samples!r}")
  after = samples[-1]
  return {
    "schema": "ut3g-safe-f3-poweroff-v1",
    "state": "f3-powered-off",
    "ltssm_before": before,
    "ltssm_after": after,
    "f3_writes": 1,
    "verification_seconds": post_f3_samples - 1,
    "ltssm_samples": samples,
    "persistent_writes": 0,
    "safe_to_cut_external_power": True,
  }


def main() -> int:
  parser = argparse.ArgumentParser(description="safely power down the Chestnut PCIe link")
  parser.add_argument("--wait-for-users", action="store_true",
                      help="wait offroad until modeld and other named AMD users exit")
  parser.add_argument("--fast-release-after-f3", action="store_true",
                      help="use one immediate LTSSM check instead of the manual three-second verification")
  args = parser.parse_args()
  if args.fast_release_after_f3 and not args.wait_for_users:
    parser.error("--fast-release-after-f3 requires --wait-for-users")

  if os.geteuid() != 0:
    raise SafePowerOffError("run as root so libusb can claim the device")
  require_offroad()
  if args.wait_for_users:
    wait_for_gpu_users()
  conflicts = conflicting_processes()
  if conflicts:
    raise SafePowerOffError(f"GPU users are still running: {conflicts!r}")

  from tinygrad.runtime.support.usb import USB3
  devices = [(device, usb_id) for usb_id in OFFICIAL_USB_IDS + DUAL_USB_IDS
             for device in USB3.list_devices(*usb_id)]
  if len(devices) != 1:
    raise SafePowerOffError(f"expected one supported USBGPU device, found {len(devices)}")
  device, usb_id = devices[0]
  usb = USB3(device[0])
  if usb_id in DUAL_USB_IDS and DUAL_PRODUCT_RE.fullmatch(usb.product) is None:
    raise SafePowerOffError(f"unexpected dual product {usb.product!r}")
  if usb_id in OFFICIAL_USB_IDS and usb.product != PRODUCT:
    raise SafePowerOffError(f"unexpected official product {usb.product!r}")

  def verify_still_safe() -> None:
    require_offroad()
    if users := conflicting_processes():
      raise SafePowerOffError(f"GPU users started before F3 poweroff: {users!r}")

  samples = 1 if args.fast_release_after_f3 else 4
  print(json.dumps(safe_power_off(usb, before_f3=verify_still_safe, post_f3_samples=samples), sort_keys=True))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
