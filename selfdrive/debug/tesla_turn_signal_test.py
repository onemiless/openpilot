#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time
import uuid

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
VALIDATION_LOG_PATH = "/data/tesla_turn_signal_validation.log"
VALIDATION_LOG_PREFIX = "[TESLA-TURN-SIGNAL-VALIDATION-v1]"
MAX_LOG_BYTES = 2 * 1024 * 1024


class ValidationRecorder:
  def __init__(self, direction: str, log_path: str = VALIDATION_LOG_PATH, test_id: str | None = None):
    self.direction = direction
    self.log_path = log_path
    self.test_id = test_id or uuid.uuid4().hex[:12]
    try:
      if os.path.exists(log_path) and os.path.getsize(log_path) > MAX_LOG_BYTES:
        os.replace(log_path, f"{log_path}.1")
    except OSError:
      pass

  def record(self, event: str, **values) -> None:
    record = {
      "prefix": VALIDATION_LOG_PREFIX,
      "test_id": self.test_id,
      "wall_time_ns": time.time_ns(),
      "monotonic_ns": time.monotonic_ns(),
      "direction": self.direction,
      "event": event,
      **values,
    }
    try:
      with open(self.log_path, "a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(record, sort_keys=True, default=str) + "\n")
        log_file.flush()
    except OSError:
      pass


def source_details(source: int) -> tuple[int, str]:
  if source >= 0xC0:
    return source - 0xC0, "rejected"
  if source >= 0x80:
    return source - 0x80, "txEcho"
  return source, "rx"


def validation_guard(CS, CC, device_started: bool = False) -> str | None:
  if device_started:
    return "device is not in Settings/Offroad state"
  if CS.gearShifter != car.CarState.GearShifter.park:
    return "vehicle is not in Park"
  if not CS.standstill or abs(CS.vEgo) >= 0.1:
    return "vehicle is not stationary"
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
    if sm.all_checks(["carState", "carControl", "deviceState"]):
      reason = validation_guard(sm["carState"], sm["carControl"], bool(sm["deviceState"].started))
      if reason is None:
        return sm["carState"], sm["carControl"]
  raise RuntimeError(reason)


def wait_for_stalk_counter(can_sock: messaging.SubSocket, recorder: ValidationRecorder, timeout_s: float = 3.0) -> int:
  deadline = time.monotonic() + timeout_s
  while time.monotonic() < deadline:
    event = messaging.recv_one_or_none(can_sock)
    if event is None:
      continue
    for frame in event.can:
      if frame.address == SCCM_LEFT_STALK_ADDRESS and frame.src == VEHICLE_BUS and len(frame.dat) == 4:
        counter = int(frame.dat[1] & 0xF)
        recorder.record("baseline_frame", source=int(frame.src), bus=VEHICLE_BUS, data=frame.dat.hex(), counter=counter,
                        turn_state=int(frame.dat[2] & 0xF))
        return counter
  raise RuntimeError("no 0x249 SCCM_leftStalk frame received on bus 1")


def observe_can(can_sock: messaging.SubSocket, recorder: ValidationRecorder, duration_s: float) -> None:
  deadline = time.monotonic() + duration_s
  while time.monotonic() < deadline:
    event = messaging.recv_one_or_none(can_sock)
    if event is None:
      continue
    for frame in event.can:
      if frame.address != SCCM_LEFT_STALK_ADDRESS or len(frame.dat) != 4:
        continue
      bus, can_direction = source_details(int(frame.src))
      recorder.record("can_observation", source=int(frame.src), bus=bus, can_direction=can_direction,
                      data=frame.dat.hex(), counter=int(frame.dat[1] & 0xF), turn_state=int(frame.dat[2] & 0xF))


def send_validation_pulse(direction: str, log_path: str = VALIDATION_LOG_PATH) -> bool:
  recorder = ValidationRecorder(direction, log_path)
  recorder.record("test_started")
  try:
    if not Params().get_bool("TeslaTurnSignalValidation"):
      raise RuntimeError("TeslaTurnSignalValidation is disabled; enable it offroad and restart")

    turn_state = SCCM_TURN_LEFT if direction == "left" else SCCM_TURN_RIGHT
    sm = messaging.SubMaster(["carState", "carControl", "deviceState"])
    can_sock = messaging.sub_sock("can", timeout=10)
    sendcan = messaging.pub_sock("sendcan")

    CS, CC = wait_for_safe_state(sm)
    recorder.record("guard_passed", device_started=bool(sm["deviceState"].started), gear=str(CS.gearShifter),
                    standstill=bool(CS.standstill), v_ego=float(CS.vEgo), brake_pressed=bool(CS.brakePressed),
                    cruise_enabled=bool(CS.cruiseState.enabled),
                    controls_enabled=bool(CC.enabled), lateral_active=bool(CC.latActive), longitudinal_active=bool(CC.longActive))
    counter = wait_for_stalk_counter(can_sock, recorder)
    sequence = [turn_state] * ACTIVE_FRAMES + [SCCM_TURN_IDLE] * RELEASE_FRAMES
    print(f"test_id={recorder.test_id} sending {direction} validation pulse from counter {counter} on bus {VEHICLE_BUS}")

    for state in sequence:
      CS, CC = wait_for_safe_state(sm, timeout_s=1.0)
      reason = validation_guard(CS, CC, bool(sm["deviceState"].started))
      if reason is not None:
        raise RuntimeError(reason)
      counter = (counter + 1) % 16
      msg = create_sccm_left_stalk(state, counter)
      recorder.record("frame_sent", state=state, counter=counter, bus=VEHICLE_BUS, data=msg.dat.hex())
      sendcan.send(can_list_to_can_capnp([msg], msgtype="sendcan"))
      print(f"state={state} counter={counter} data={msg.dat.hex()}")
      observe_can(can_sock, recorder, FRAME_INTERVAL_S)

    expected_field = "leftBlinker" if direction == "left" else "rightBlinker"
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
      sm.update(100)
      feedback = bool(getattr(sm["carState"], expected_field))
      if feedback:
        recorder.record("test_finished", result="PASS", feedback_field=expected_field, feedback=True)
        print(f"PASS: carState.{expected_field}=true; log={log_path}; test_id={recorder.test_id}")
        return True
    recorder.record("test_finished", result="FAIL", feedback_field=expected_field, feedback=False)
    print(f"FAIL: no carState.{expected_field} feedback observed; log={log_path}; test_id={recorder.test_id}")
    return False
  except RuntimeError as error:
    recorder.record("test_finished", result="BLOCKED", error=str(error))
    raise


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
