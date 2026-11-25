#!/usr/bin/env python3
"""Packed Tesla RX -> freshly compiled safety -> tick acceptance; no physical CAN."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from opendbc.car.structs import CarParams
from opendbc.car.tesla.values import TeslaSafetyFlags
from opendbc.safety.tests.libsafety import libsafety_py
from opendbc.safety.tests.test_tesla import TestTeslaStockSafety
from opendbc.sunnypilot.car.tesla.values import TeslaSafetyFlagsSP


def run(output):
  root = Path(__file__).resolve().parents[2]
  safety = libsafety_py.libsafety
  cases = []
  for protocol in (0, TeslaSafetyFlags.FSD_14, TeslaSafetyFlags.STEERING_3_BIT):
    for flags in (0, TeslaSafetyFlagsSP.HAS_VEHICLE_BUS, TeslaSafetyFlagsSP.AUTO_SPEED_LIMIT,
                  TeslaSafetyFlagsSP.HAS_VEHICLE_BUS | TeslaSafetyFlagsSP.AUTO_SPEED_LIMIT):
      safety.set_current_safety_param_sp(flags)
      fixture = TestTeslaStockSafety()
      fixture.SAFETY_PARAM = protocol
      fixture.setUp()
      assert safety.get_current_safety_mode() == CarParams.SafetyModel.tesla
      frames = [fixture._long_control_msg(0, bus=2, counter=1),
                fixture._angle_cmd_msg(0, False, increment_timer=False, bus=2),
                fixture._speed_msg(0), fixture._speed_msg_2(0), fixture._angle_meas_msg(0),
                fixture._user_brake_msg(False), fixture._pcm_status_msg(False),
                fixture.packer.make_can_msg_safety("UI_warning", 0, {"buckleStatus": 1})]
      if flags & TeslaSafetyFlagsSP.HAS_VEHICLE_BUS:
        frames.append(fixture.packer_adas.make_can_msg_safety("UI_status2", 1, {"UI_activeTouchPoints": 0}))
      if flags & TeslaSafetyFlagsSP.AUTO_SPEED_LIMIT:
        frames.append(fixture._speed_wheel_msg())
      safety.set_timer(1_000_000)
      assert all(safety.safety_rx_hook(frame) for frame in frames)
      assert safety.safety_config_valid()
      safety.set_controls_allowed(True)
      safety.safety_tick()
      timely = bool(safety.get_controls_allowed())
      safety.set_controls_allowed(True)
      safety.set_timer(7_000_001)
      safety.safety_tick()
      stale_blocked = not safety.get_controls_allowed()
      cases.append({"protocol": int(protocol), "flags": int(flags), "rx_count": len(frames),
                    "timely_allowed": timely, "stale_blocked": stale_blocked})
  safety.set_current_safety_param_sp(0)
  result = {"passed": all(c["timely_allowed"] and c["stale_blocked"] for c in cases),
            "scope": "synthetic packed RX through compiled C safety; no hardware/physical CAN",
            "root": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
            "opendbc": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root / "opendbc_repo", text=True).strip(),
            "safety_sha256": hashlib.sha256((root / "opendbc_repo/opendbc/safety/safety.h").read_bytes()).hexdigest(), "cases": cases}
  output.parent.mkdir(parents=True, exist_ok=True)
  output.write_text(json.dumps(result, indent=2) + "\n")
  print(json.dumps({"artifact": str(output), "passed": result["passed"], "cases": len(cases)}))
  return result["passed"]


if __name__ == "__main__":
  parser = argparse.ArgumentParser()
  parser.add_argument("--output", type=Path, required=True)
  raise SystemExit(0 if run(parser.parse_args().output) else 1)
