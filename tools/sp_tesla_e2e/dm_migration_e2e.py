#!/usr/bin/env python3
"""Actual manager initialization -> native Params -> DM session/process policy.

Simulate device identity and suppress bootlog/registration I/O; start no services.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch

from opendbc.car.structs import car
from openpilot.common.hardware import HARDWARE
from openpilot.common.params import Params, ParamKeyFlag
from openpilot.sunnypilot.hardware.driver_monitoring import driver_monitoring_enabled, latch_driver_monitoring
from openpilot.system.manager import manager
from openpilot.system.manager.process_config import managed_processes


def run(output: Path):
  results = []
  cp = car.CarParams.new_message()
  with tempfile.TemporaryDirectory() as directory:
    for profile, device_type, capable, expected in [
      ("standard", "tici", True, False),
      ("standard", "tizi", True, False),
      ("standard", "mici", True, True),
      ("c3xl", "tici", False, False),
      ("standard", "pc", True, False),
    ]:
      with patch.dict(os.environ, SUNNYPILOT_HARDWARE_PROFILE=profile), \
           patch.object(HARDWARE, "get_device_type", return_value=device_type):
        for saved in [True, False, None]:
          params = Params(str(Path(directory) / f"{profile}-{device_type}-{saved}"))
          if saved is not None:
            params.put_bool("DriverMonitoringEnabled", saved, block=True)
          params.put_bool("ActiveDriverMonitoringEnabled", not expected, block=True)
          params.put_bool("TeslaBlindspotAmbientEnabled", True, block=True)
          with patch.object(manager, "Params", return_value=params), \
               patch.object(manager, "PC", False), \
               patch.object(manager, "save_bootlog"), \
               patch.object(manager, "register", return_value="dm-migration-e2e"):
            manager.manager_init()
            assert params.get("DriverMonitoringEnabled") is expected, (profile, device_type, saved, "migration")
            assert params.get_bool("SPDriverMonitoringDefaultsMigrated")
            assert params.get("ActiveDriverMonitoringEnabled") is None
            assert latch_driver_monitoring(params) is expected
            for name in ["dmonitoringmodeld", "dmonitoringd"]:
              assert managed_processes[name].should_run(True, params, cp) is expected

            params.put_bool("DriverMonitoringEnabled", not expected, block=True)
            assert driver_monitoring_enabled(params) is expected
            manager.manager_init()
            assert params.get("DriverMonitoringEnabled") is not expected, "second startup must preserve the new user choice"
            assert latch_driver_monitoring(params) is (capable and not expected)
            for flag in [ParamKeyFlag.CLEAR_ON_MANAGER_START, ParamKeyFlag.CLEAR_ON_OFFROAD_TRANSITION, ParamKeyFlag.CLEAR_ON_IGNITION_ON]:
              params.clear_all(flag)
              assert params.get_bool("SPDriverMonitoringDefaultsMigrated")
            assert params.get_bool("TeslaBlindspotAmbientEnabled")
            params.clear_all(ParamKeyFlag.BACKUP)
            assert params.get("SPDriverMonitoringDefaultsMigrated") is None
          results.append({"profile": profile, "device_type": device_type, "old_saved": saved,
                          "migrated": expected, "one_time": True, "session_latched": True,
                          "marker_persistent_and_backed_up": True, "unrelated_setting_preserved": True})
  output.parent.mkdir(parents=True, exist_ok=True)
  output.write_text(json.dumps({"passed": True, "cases": results,
                               "head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
                               "scope": "actual manager_init/native Params/DM process predicates; simulated identity, no services or physical CAN"
                               }, indent=2) + "\n")
  print(output)


if __name__ == "__main__":
  parser = argparse.ArgumentParser()
  parser.add_argument("--output", type=Path, required=True)
  run(parser.parse_args().output)
