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
from opendbc.car.can_definitions import CanData


DAS_BODY_CONTROLS_ADDRESS = 0x3E9
UI_WARNING_ADDRESS = 0x311
FRONT_LIGHTING_ADDRESS = 0x3F5
VEHICLE_BUS = 1
PARTY_BUS = 0
TURN_REQUESTS = {"left": 1, "right": 2, "cancel": 3}
ACTIVE_TURN_REASON = 8
CANCEL_TURN_REASON = 4
VALIDATION_LOG_PATH = "/data/tesla_turn_signal_validation.log"
VALIDATION_LOG_PREFIX = "[TESLA-TURN-SIGNAL-VALIDATION-v2]"
MAX_LOG_BYTES = 2 * 1024 * 1024
ACTION_FRAME_COUNT = 5
ACTION_OBSERVE_S = 0.2
_UI_WARNING_MESSAGE = DBC("tesla_model3_party").name_to_msg["UI_warning"]
_FRONT_LIGHTING_MESSAGE = DBC("tesla_model3_vehicle").name_to_msg["ID3F5VCFRONT_lighting"]


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


def tesla_body_controls_checksum(data: bytes) -> int:
  if len(data) != 8:
    raise ValueError("0x3E9 DAS_bodyControls must contain 8 bytes")
  return (0xE9 + 0x03 + sum(data[:7])) & 0xFF


def decode_body_controls(data: bytes) -> dict[str, int | bool]:
  if len(data) != 8:
    raise ValueError("0x3E9 DAS_bodyControls must contain 8 bytes")
  return {
    "turn_request": data[1] & 0x3,
    "turn_request_reason": (data[2] >> 1) & 0xF,
    "autopilot_active": bool(data[3] & 0x1),
    "acc_active": bool((data[3] >> 5) & 0x1),
    "counter": (data[6] >> 4) & 0xF,
    "checksum": data[7],
  }


def is_original_body_controls_frame(address: int, source: int, data: bytes) -> bool:
  return (address == DAS_BODY_CONTROLS_ADDRESS and source == VEHICLE_BUS and len(data) == 8 and
          tesla_body_controls_checksum(data) == data[7])


def create_validation_can_socket() -> messaging.SubSocket:
  # CAN is a high-rate stream. Keep only the freshest batch so this diagnostic
  # cannot build a backlog that starves real-time control processes.
  return messaging.sub_sock("can", conflate=True, timeout=100)


def create_body_control_frame(original_frame: bytes, direction: str, counter: int) -> bytes:
  if direction not in TURN_REQUESTS:
    raise ValueError(f"unsupported turn request: {direction}")
  if not 0 <= counter <= 15:
    raise ValueError(f"invalid DAS_bodyControls counter: {counter}")
  if not is_original_body_controls_frame(DAS_BODY_CONTROLS_ADDRESS, VEHICLE_BUS, original_frame):
    raise ValueError("original 0x3E9 RX template has invalid length or checksum")

  data = bytearray(original_frame)
  data[1] = (data[1] & 0xFC) | TURN_REQUESTS[direction]
  reason = CANCEL_TURN_REASON if direction == "cancel" else ACTIVE_TURN_REASON
  data[2] = (data[2] & 0xE1) | ((reason & 0xF) << 1)
  data[6] = (data[6] & 0x0F) | ((counter & 0xF) << 4)
  data[7] = tesla_body_controls_checksum(data)
  return bytes(data)


def decode_ui_warning(data: bytes) -> dict[str, int | bool]:
  left_state = int(get_raw_value(data, _UI_WARNING_MESSAGE.sigs["leftBlinkerBlinking"]))
  right_state = int(get_raw_value(data, _UI_WARNING_MESSAGE.sigs["rightBlinkerBlinking"]))
  return {
    "left_blinker": left_state in (1, 2),
    "right_blinker": right_state in (1, 2),
    "left_blinker_state": left_state,
    "right_blinker_state": right_state,
  }


def decode_front_lighting(data: bytes) -> dict[str, int | bool]:
  left_state = int(get_raw_value(data, _FRONT_LIGHTING_MESSAGE.sigs["VCFRONT_turnSignalLeftStatus"]))
  right_state = int(get_raw_value(data, _FRONT_LIGHTING_MESSAGE.sigs["VCFRONT_turnSignalRightStatus"]))
  return {
    "left_blinker": left_state == 1,
    "right_blinker": right_state == 1,
    "left_blinker_state": left_state,
    "right_blinker_state": right_state,
  }


def wait_for_body_controls_template(can_sock: messaging.SubSocket, recorder: ValidationRecorder,
                                    timeout_s: float = 3.0) -> bytes:
  deadline = time.monotonic() + timeout_s
  while time.monotonic() < deadline:
    event = messaging.recv_one_or_none(can_sock)
    if event is None:
      continue
    for frame in event.can:
      data = bytes(frame.dat)
      if not is_original_body_controls_frame(int(frame.address), int(frame.src), data):
        continue
      decoded = decode_body_controls(data)
      recorder.record("baseline_frame", source=int(frame.src), bus=VEHICLE_BUS, data=data.hex(), decoded=decoded)
      if decoded["turn_request"] == 0:
        return data
  raise RuntimeError("no fresh checksum-valid idle 0x3E9 DAS_bodyControls frame received on bus 1")


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
      data = bytes(frame.dat)
      if frame.address == DAS_BODY_CONTROLS_ADDRESS and len(data) == 8:
        tx_echo |= can_direction == "txEcho"
        rejected |= can_direction == "rejected"
        if can_direction != "rx":
          recorder.record("body_controls_observation", source=int(frame.src), bus=bus, can_direction=can_direction,
                          data=data.hex(), decoded=decode_body_controls(data),
                          checksum_valid=tesla_body_controls_checksum(data) == data[7])
      elif frame.address == UI_WARNING_ADDRESS and bus == PARTY_BUS and can_direction == "rx" and len(data) == 7:
        decoded = decode_ui_warning(data)
        expected_feedback = bool(decoded[f"{expected_direction}_blinker"])
        if expected_feedback and not feedback:
          recorder.record("ui_warning_observation", source=int(frame.src), bus=bus, data=data.hex(), decoded=decoded)
        feedback |= expected_feedback
      elif frame.address == FRONT_LIGHTING_ADDRESS and bus == VEHICLE_BUS and can_direction == "rx" and len(data) == 8:
        decoded = decode_front_lighting(data)
        expected_feedback = bool(decoded[f"{expected_direction}_blinker"])
        if expected_feedback and not feedback:
          recorder.record("front_lighting_observation", source=int(frame.src), bus=bus, data=data.hex(), decoded=decoded)
        feedback |= expected_feedback
  return feedback, tx_echo, rejected


def send_validation_pulse(direction: str, log_path: str = VALIDATION_LOG_PATH) -> bool:
  recorder = ValidationRecorder(direction, log_path)
  recorder.record("test_started", address=hex(DAS_BODY_CONTROLS_ADDRESS))
  try:
    if not Params().get_bool("TeslaTurnSignalValidation"):
      raise RuntimeError("TeslaTurnSignalValidation is disabled; enable it offroad and restart")

    can_sock = create_validation_can_socket()
    sendcan = messaging.pub_sock("sendcan")

    feedback = False
    tx_echo = False
    rejected = False
    for frame_index in range(ACTION_FRAME_COUNT):
      original_idle = wait_for_body_controls_template(can_sock, recorder)
      counter = (decode_body_controls(original_idle)["counter"] + 1) % 16
      action_data = create_body_control_frame(original_idle, direction, counter)
      recorder.record("frame_submitted", phase="action", frame_index=frame_index + 1,
                      frame_count=ACTION_FRAME_COUNT, request=TURN_REQUESTS[direction],
                      reason=ACTIVE_TURN_REASON, counter=counter, bus=VEHICLE_BUS, data=action_data.hex())
      sendcan.send(can_list_to_can_capnp([CanData(DAS_BODY_CONTROLS_ADDRESS, action_data, VEHICLE_BUS)], msgtype="sendcan"))
      frame_feedback, frame_echo, frame_rejected = observe_can(can_sock, recorder, ACTION_OBSERVE_S, direction)
      feedback |= frame_feedback
      tx_echo |= frame_echo
      rejected |= frame_rejected

    cancel_echo = False
    cancel_rejected = False
    try:
      cancel_template = wait_for_body_controls_template(can_sock, recorder, timeout_s=1.0)
      cancel_counter = (decode_body_controls(cancel_template)["counter"] + 1) % 16
      cancel_data = create_body_control_frame(cancel_template, "cancel", cancel_counter)
      recorder.record("frame_submitted", phase="cancel", request=TURN_REQUESTS["cancel"],
                      reason=CANCEL_TURN_REASON, counter=cancel_counter, bus=VEHICLE_BUS, data=cancel_data.hex())
      sendcan.send(can_list_to_can_capnp([CanData(DAS_BODY_CONTROLS_ADDRESS, cancel_data, VEHICLE_BUS)], msgtype="sendcan"))
      cancel_feedback, cancel_echo, cancel_rejected = observe_can(can_sock, recorder, 0.5, direction)
      feedback |= cancel_feedback
    except RuntimeError as error:
      recorder.record("cancel_skipped", error=str(error))

    if feedback:
      recorder.record("test_finished", result="PASS", feedback=True, tx_echo=tx_echo, rejected=rejected,
                      cancel_echo=cancel_echo, cancel_rejected=cancel_rejected)
      print(f"PASS: vehicle reports {direction} blinker; log={log_path}; test_id={recorder.test_id}")
      return True

    result = "PANDA_REJECTED" if rejected and not tx_echo else "NO_VEHICLE_FEEDBACK" if tx_echo else "NO_TX_ECHO"
    recorder.record("test_finished", result=result, feedback=False, tx_echo=tx_echo, rejected=rejected,
                    cancel_echo=cancel_echo, cancel_rejected=cancel_rejected)
    print(f"FAIL: {result}; log={log_path}; test_id={recorder.test_id}")
    return False
  except (RuntimeError, ValueError) as error:
    recorder.record("test_finished", result="BLOCKED", error=str(error))
    raise RuntimeError(str(error)) from error


def main() -> int:
  parser = argparse.ArgumentParser(description="Tesla DAS_bodyControls turn-signal validation")
  parser.add_argument("direction", choices=("left", "right"))
  args = parser.parse_args()
  try:
    return 0 if send_validation_pulse(args.direction) else 2
  except RuntimeError as error:
    print(f"BLOCKED: {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
  raise SystemExit(main())
