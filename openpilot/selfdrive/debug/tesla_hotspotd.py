#!/usr/bin/env python3
"""Keep the C3XL Tesla-browser address aligned with the hotspot lifecycle."""
from __future__ import annotations

import subprocess
import time
from collections.abc import Callable

from openpilot.common.swaglog import cloudlog
from openpilot.selfdrive.debug.device_hotspot import hotspot_status, set_tesla_address_enabled


POLL_INTERVAL_SECONDS = 1.0


class TeslaHotspotAddressManager:
  def __init__(self, runner: Callable = subprocess.run):
    self.runner = runner
    self.address_enabled = False

  def reconcile(self) -> bool:
    status = hotspot_status(self.runner)
    if not status["available"]:
      raise RuntimeError("NetworkManager hotspot state is unavailable")

    desired = bool(status["active"])
    current = bool(status["tesla_address_ready"])
    if current != desired:
      set_tesla_address_enabled(desired, self.runner)
      cloudlog.info("Tesla hotspot address %s", "enabled" if desired else "disabled")
    self.address_enabled = desired
    return desired

  def close(self) -> None:
    try:
      set_tesla_address_enabled(False, self.runner)
    except RuntimeError:
      cloudlog.exception("Failed to remove Tesla hotspot address")
    self.address_enabled = False

  def run(self) -> None:
    last_error: str | None = None
    while True:
      try:
        self.reconcile()
        last_error = None
      except RuntimeError as error:
        message = str(error)
        if message != last_error:
          cloudlog.error("Tesla hotspot address reconciliation failed: %s", message)
          last_error = message
      time.sleep(POLL_INTERVAL_SECONDS)


def main() -> None:
  manager = TeslaHotspotAddressManager()
  try:
    manager.run()
  finally:
    manager.close()


if __name__ == "__main__":
  main()
