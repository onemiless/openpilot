#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time
import uuid

import cereal.messaging as messaging

from openpilot.common.params import Params
from openpilot.selfdrive.pandad import can_list_to_can_capnp
from opendbc.can.dbc import DBC
from opendbc.can.parser import get_raw_value
from opendbc.car.tesla.teslacan import SCCM_TURN_IDLE, SCCM_TURN_LEFT, SCCM_TURN_RIGHT, create_sccm_left_stalk


SCCM_LEFT_STALK_ADDRESS = 0x249
UI_WARNING_ADDRESS = 0x311
VEHICLE_BUS = 1
PARTY_BUS = 0
ACTIVE_FRAMES = 3
RELEASE_FRAMES = 2
FRAME_INTERVAL_S = 0.05
VALIDATION_LOG_PATH = "/data/tesla_turn_signal_validation.log"
VALIDATION_LOG_PREFIX = "[TESLA-TURN-SIGNAL-VALIDATION-v1]"
MAX_LOG_BYTES = 2 * 1024 * 1024
_UI_WARNING_MESSAGE = DBC("tesla_model3_party").name_to_msg["UI_warning"]


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


def decode_ui_warning(data: bytes) -> dict[str, int | bool]:
  left_state = int(get_raw_value(data, _UI_WARNING_MESSAGE.sigs["leftBlinkerBlinking"]))
  right_state = int(get_raw_value(data, _UI_WARNING_MESSAGE.sigs["rightBlinkerBlinking"]))
  return {
    "left_blinker": left_state in (1, 2),
    "right_blinker": right_state in (1, 2),
    "left_blinker_state": left_state,
    "right_blinker_state": right_state,
  }


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


def observe_can(can_sock: messaging.SubSocket, recorder: ValidationRecorder, duration_s: float,
                expected_direction: str) -> tuple[bool, bool, bool]:
  feedback = False
  tx_echo = False
  rejected = False
  deadline = time.monotonic() + duration_s
  while time.monotonic() < deadline:
    event = messaging.recv_one_or_none(can_sock)
    if event is None:
      continue
    for frame in event.can:
      bus, can_direction = source_details(int(frame.src))
      if frame.address == SCCM_LEFT_STALK_ADDRESS and len(frame.dat) == 4:
        tx_echo |= can_direction == "txEcho"
        rejected |= can_direction == "rejected"
        recorder.record("can_observation", source=int(frame.src), bus=bus, can_direction=can_direction,
                        data=frame.dat.hex(), counter=int(frame.dat[1] & 0xF), turn_state=int(frame.dat[2] & 0xF))
      elif frame.address == UI_WARNING_ADDRESS and bus == PARTY_BUS and can_direction == "rx" and len(frame.dat) == 7:
        decoded = decode_ui_warning(frame.dat)
        feedback |= bool(decoded[f"{expected_direction}_blinker"])
        recorder.record("ui_warning_observation", source=int(frame.src), bus=bus, data=frame.dat.hex(), decoded=decoded)
  return feedback, tx_echo, rejected


def send_validation_pulse(direction: str, log_path: str = VALIDATION_LOG_PATH) -> bool:
  recorder = ValidationRecorder(direction, log_path)
  recorder.record("test_started")
  try:
    if not Params().get_bool("TeslaTurnSignalValidation"):
      raise RuntimeError("TeslaTurnSignalValidation is disabled; enable it offroad and restart")

    turn_state = SCCM_TURN_LEFT if direction == "left" else SCCM_TURN_RIGHT
    can_sock = messaging.sub_sock("can", timeout=10)
    sendcan = messaging.pub_sock("sendcan")

    recorder.record("can_path_started", python_state_checks=False, panda_safety_enforced=True)
    counter = wait_for_stalk_counter(can_sock, recorder)
    sequence = [turn_state] * ACTIVE_FRAMES + [SCCM_TURN_IDLE] * RELEASE_FRAMES
    print(f"test_id={recorder.test_id} sending {direction} validation pulse from counter {counter} on bus {VEHICLE_BUS}")

    feedback = False
    tx_echo = False
    rejected = False
    for state in sequence:
      counter = (counter + 1) % 16
      msg = create_sccm_left_stalk(state, counter)
      recorder.record("frame_sent", state=state, counter=counter, bus=VEHICLE_BUS, data=msg.dat.hex())
      sendcan.send(can_list_to_can_capnp([msg], msgtype="sendcan"))
      print(f"state={state} counter={counter} data={msg.dat.hex()}")
      observed_feedback, observed_echo, observed_rejected = observe_can(can_sock, recorder, FRAME_INTERVAL_S, direction)
      feedback |= observed_feedback
      tx_echo |= observed_echo
      rejected |= observed_rejected

    observed_feedback, observed_echo, observed_rejected = observe_can(can_sock, recorder, 2.0, direction)
    feedback |= observed_feedback
    tx_echo |= observed_echo
    rejected |= observed_rejected

    if feedback:
      recorder.record("test_finished", result="PASS", feedback=True, tx_echo=tx_echo, rejected=rejected)
      print(f"PASS: UI_warning reports {direction} blinker; log={log_path}; test_id={recorder.test_id}")
      return True

    result = "PANDA_REJECTED" if rejected and not tx_echo else "NO_VEHICLE_FEEDBACK" if tx_echo else "NO_TX_ECHO"
    recorder.record("test_finished", result=result, feedback=False, tx_echo=tx_echo, rejected=rejected)
    print(f"FAIL: {result}; log={log_path}; test_id={recorder.test_id}")
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
