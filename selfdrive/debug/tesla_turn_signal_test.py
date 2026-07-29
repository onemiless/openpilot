#!/usr/bin/env python3
import argparse
import sys
import time

import cereal.messaging as messaging
from cereal import car

from openpilot.common.params import Params
from openpilot.selfdrive.pandad import can_list_to_can_capnp
from opendbc.car.tesla.teslacan import SCCM_TURN_IDLE, SCCM_TURN_LEFT, SCCM_TURN_RIGHT, create_sccm_left_stalk


SCCM_LEFT_STALK_ADDRESS = 0x249
VEHICLE_BUS = 1
ACTIVE_FRAMES = 3
RELEASE_FRAMES = 2
FRAME_INTERVAL_S = 0.05


def validation_guard(CS, CC) -> str | None:
  if CS.gearShifter != car.CarState.GearShifter.park:
    return "vehicle is not in Park"
  if not CS.standstill or abs(CS.vEgo) >= 0.1:
    return "vehicle is not stationary"
  if not CS.brakePressed:
    return "brake pedal is not pressed"
  if CS.cruiseState.enabled:
    return "cruise is enabled"
  if CC.enabled or CC.latActive or CC.longActive:
    return "openpilot/sunnypilot controls are active"
  return None


def wait_for_safe_state(sm: messaging.SubMaster, timeout_s: float = 10.0):
  deadline = time.monotonic() + timeout_s
  reason = "car state unavailable"
  while time.monotonic() < deadline:
    sm.update(100)
    if sm.all_checks(["carState", "carControl"]):
      reason = validation_guard(sm["carState"], sm["carControl"])
      if reason is None:
        return sm["carState"], sm["carControl"]
  raise RuntimeError(reason)


def wait_for_stalk_counter(can_sock: messaging.SubSocket, timeout_s: float = 3.0) -> int:
  deadline = time.monotonic() + timeout_s
  while time.monotonic() < deadline:
    event = messaging.recv_one_or_none(can_sock)
    if event is None:
      continue
    for frame in event.can:
      if frame.address == SCCM_LEFT_STALK_ADDRESS and frame.src == VEHICLE_BUS and len(frame.dat) == 4:
        return int(frame.dat[1] & 0xF)
  raise RuntimeError("no 0x249 SCCM_leftStalk frame received on bus 1")


def send_validation_pulse(direction: str) -> bool:
  if not Params().get_bool("TeslaTurnSignalValidation"):
    raise RuntimeError("TeslaTurnSignalValidation is disabled; enable it offroad and restart")

  turn_state = SCCM_TURN_LEFT if direction == "left" else SCCM_TURN_RIGHT
  sm = messaging.SubMaster(["carState", "carControl"])
  can_sock = messaging.sub_sock("can", timeout=100)
  sendcan = messaging.pub_sock("sendcan")

  wait_for_safe_state(sm)
  counter = wait_for_stalk_counter(can_sock)
  sequence = [turn_state] * ACTIVE_FRAMES + [SCCM_TURN_IDLE] * RELEASE_FRAMES
  print(f"sending {direction} validation pulse from counter {counter} on bus {VEHICLE_BUS}")

  for state in sequence:
    CS, CC = wait_for_safe_state(sm, timeout_s=1.0)
    reason = validation_guard(CS, CC)
    if reason is not None:
      raise RuntimeError(reason)
    counter = (counter + 1) % 16
    msg = create_sccm_left_stalk(state, counter)
    sendcan.send(can_list_to_can_capnp([msg], msgtype="sendcan"))
    print(f"state={state} counter={counter} data={msg.dat.hex()}")
    time.sleep(FRAME_INTERVAL_S)

  expected_field = "leftBlinker" if direction == "left" else "rightBlinker"
  deadline = time.monotonic() + 2.0
  while time.monotonic() < deadline:
    sm.update(100)
    if bool(getattr(sm["carState"], expected_field)):
      print(f"PASS: carState.{expected_field}=true")
      return True
  print(f"FAIL: no carState.{expected_field} feedback observed")
  return False


def main() -> int:
  parser = argparse.ArgumentParser(description="Stationary Tesla 0x249 turn-signal CAN validation")
  parser.add_argument("direction", choices=("left", "right"))
  args = parser.parse_args()
  try:
    return 0 if send_validation_pulse(args.direction) else 2
  except RuntimeError as error:
    print(f"BLOCKED: {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
  raise SystemExit(main())
