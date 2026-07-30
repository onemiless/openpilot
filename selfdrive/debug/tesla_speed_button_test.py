#!/usr/bin/env python3
import argparse
from enum import StrEnum
import json
import os
import sys
import time
import uuid

import cereal.messaging as messaging

from openpilot.common.params import Params
from openpilot.selfdrive.pandad import can_list_to_can_capnp
from opendbc.car.can_definitions import CanData


STW_ACTION_REQUEST_ADDRESS = 0x238
VEHICLE_BUS = 1
VALIDATION_LOG_PATH = "/data/tesla_speed_button_validation.log"
VALIDATION_LOG_PREFIX = "[TESLA-SPEED-BUTTON-VALIDATION-v1]"
MAX_LOG_BYTES = 2 * 1024 * 1024
FRAME_INTERVAL_S = 0.20


class SpeedButtonAction(StrEnum):
  idle = "idle"
  increase = "increase"
  decrease = "decrease"
  unknown = "unknown"


_NORMALIZED_SPEED_STATES = {
  SpeedButtonAction.idle: 0,
  SpeedButtonAction.increase: 16,
  SpeedButtonAction.decrease: 32,
}


def tesla_stw_checksum(data: bytes) -> int:
  if len(data) != 8:
    raise ValueError("0x238 STW_ACTN_RQ must contain 8 bytes")
  return (0x38 + 0x02 + sum(data[:7])) & 0xFF


def is_original_vehicle_speed_frame(address: int, source: int, data: bytes) -> bool:
  return address == STW_ACTION_REQUEST_ADDRESS and source == VEHICLE_BUS and len(data) == 8


def decode_original_speed_button_state(first_byte: int) -> SpeedButtonAction:
  if (first_byte & 0xC0) != 0x80:
    return SpeedButtonAction.unknown
  normalized_state = (first_byte & 0x3F) ^ 0x30
  for action, state in _NORMALIZED_SPEED_STATES.items():
    if normalized_state == state:
      return action
  return SpeedButtonAction.unknown


def create_speed_button_frame(original_idle_frame: bytes, action: SpeedButtonAction, counter: int) -> bytes:
  if len(original_idle_frame) != 8 or tesla_stw_checksum(original_idle_frame) != original_idle_frame[7]:
    raise ValueError("original 0x238 RX template has invalid length or checksum")
  if decode_original_speed_button_state(original_idle_frame[0]) != SpeedButtonAction.idle:
    raise ValueError("original 0x238 RX template is not an inverse-encoded idle frame")
  if action not in _NORMALIZED_SPEED_STATES:
    raise ValueError(f"unsupported speed-button action: {action}")

  data = bytearray(original_idle_frame)
  raw_state = _NORMALIZED_SPEED_STATES[action] ^ 0x30
  data[0] = (data[0] & 0xC0) | raw_state
  data[6] = ((counter & 0xF) << 4) | (data[6] & 0xF)
  data[7] = tesla_stw_checksum(data)
  return bytes(data)


class ValidationRecorder:
  def __init__(self, action: SpeedButtonAction, log_path: str = VALIDATION_LOG_PATH):
    self.action = action
    self.log_path = log_path
    self.test_id = uuid.uuid4().hex[:12]
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
      "action": self.action.value,
      "event": event,
      **values,
    }
    try:
      with open(self.log_path, "a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(record, sort_keys=True, default=str) + "\n")
        log_file.flush()
    except OSError:
      pass


def wait_for_original_idle_template(can_sock: messaging.SubSocket, recorder: ValidationRecorder,
                                    timeout_s: float = 5.0) -> bytes:
  deadline = time.monotonic() + timeout_s
  while time.monotonic() < deadline:
    event = messaging.recv_one_or_none(can_sock)
    if event is None:
      continue
    for frame in event.can:
      data = bytes(frame.dat)
      if not is_original_vehicle_speed_frame(int(frame.address), int(frame.src), data):
        continue
      checksum_valid = tesla_stw_checksum(data) == data[7]
      action = decode_original_speed_button_state(data[0]) if checksum_valid else SpeedButtonAction.unknown
      recorder.record("original_rx_observation", source=int(frame.src), bus=VEHICLE_BUS, data=data.hex(),
                      checksum_valid=checksum_valid, decoded_action=action.value)
      if checksum_valid and action == SpeedButtonAction.idle:
        recorder.record("original_rx_template_selected", source=int(frame.src), bus=VEHICLE_BUS, data=data.hex(),
                        counter=(data[6] >> 4) & 0xF)
        return data
  raise RuntimeError("no fresh checksum-valid inverse-encoded idle 0x238 frame received on bus 1")


def latest_cruise_speed(car_state_sock: messaging.SubSocket, duration_s: float) -> float | None:
  latest = None
  deadline = time.monotonic() + duration_s
  while time.monotonic() < deadline:
    event = messaging.recv_one_or_none(car_state_sock)
    if event is not None:
      latest = float(event.carState.cruiseState.speedCluster)
  return latest


def observe_transmission(can_sock: messaging.SubSocket, recorder: ValidationRecorder,
                         duration_s: float) -> tuple[bool, bool]:
  tx_echo = False
  rejected = False
  deadline = time.monotonic() + duration_s
  while time.monotonic() < deadline:
    event = messaging.recv_one_or_none(can_sock)
    if event is None:
      continue
    for frame in event.can:
      if int(frame.address) != STW_ACTION_REQUEST_ADDRESS or len(frame.dat) != 8:
        continue
      source = int(frame.src)
      if source == VEHICLE_BUS:
        recorder.record("original_rx_observation", source=source, bus=VEHICLE_BUS, data=frame.dat.hex())
      elif source == VEHICLE_BUS + 0x80:
        tx_echo = True
        recorder.record("transmission_echo", source=source, bus=VEHICLE_BUS, data=frame.dat.hex())
      elif source == VEHICLE_BUS + 0xC0:
        rejected = True
        recorder.record("transmission_rejected", source=source, bus=VEHICLE_BUS, data=frame.dat.hex())
  return tx_echo, rejected


def run_validation(action: SpeedButtonAction, log_path: str = VALIDATION_LOG_PATH) -> int:
  recorder = ValidationRecorder(action, log_path)
  recorder.record("test_started", analysis_source="original_rx_only")
  try:
    if not Params().get_bool("TeslaSpeedButtonValidation"):
      raise RuntimeError("TeslaSpeedButtonValidation is disabled; enable it offroad and restart")

    can_sock = messaging.sub_sock("can", timeout=10)
    car_state_sock = messaging.sub_sock("carState", timeout=10)
    sendcan = messaging.pub_sock("sendcan")

    original_idle = wait_for_original_idle_template(can_sock, recorder)
    before_speed = latest_cruise_speed(car_state_sock, 0.4)
    counter = (original_idle[6] >> 4) & 0xF
    action_data = create_speed_button_frame(original_idle, action, (counter + 1) % 16)
    release_data = create_speed_button_frame(original_idle, SpeedButtonAction.idle, (counter + 2) % 16)

    any_tx_echo = False
    for phase, data in (("action", action_data), ("release", release_data)):
      recorder.record("frame_submitted", phase=phase, bus=VEHICLE_BUS, data=data.hex(),
                      counter=(data[6] >> 4) & 0xF)
      sendcan.send(can_list_to_can_capnp([CanData(STW_ACTION_REQUEST_ADDRESS, data, VEHICLE_BUS)], msgtype="sendcan"))
      tx_echo, rejected = observe_transmission(can_sock, recorder, FRAME_INTERVAL_S)
      any_tx_echo |= tx_echo
      if rejected and not tx_echo:
        recorder.record("test_finished", result="PANDA_REJECTED", before_speed=before_speed)
        print(f"FAIL: Panda rejected {phase} frame; log={log_path}; test_id={recorder.test_id}")
        return 2

    if not any_tx_echo:
      recorder.record("test_finished", result="NO_TX_ECHO", before_speed=before_speed)
      print(f"FAIL: no Panda transmission echo; log={log_path}; test_id={recorder.test_id}")
      return 2

    after_speed = latest_cruise_speed(car_state_sock, 2.0)
    changed_correctly = None
    if before_speed is not None and after_speed is not None:
      delta = after_speed - before_speed
      changed_correctly = delta > 0.1 if action == SpeedButtonAction.increase else delta < -0.1
      if abs(delta) > 0.1 and not changed_correctly:
        recorder.record("test_finished", result="WRONG_DIRECTION", before_speed=before_speed,
                        after_speed=after_speed, delta=delta)
        message = f"FAIL: set speed changed in the wrong direction ({delta * 3.6:+.1f} km/h); log={log_path}; test_id={recorder.test_id}"
        print(message)
        return 2

    result = "PASS" if changed_correctly else "SENT_CHECK_VEHICLE_UI"
    recorder.record("test_finished", result=result, before_speed=before_speed, after_speed=after_speed)
    if changed_correctly:
      message = f"PASS: set speed changed from {before_speed * 3.6:.1f} to {after_speed * 3.6:.1f} km/h; log={log_path}; test_id={recorder.test_id}"
      print(message)
      return 0

    message = f"SENT: inspect the vehicle set-speed display; no reliable carState speed edge was observed; log={log_path}; test_id={recorder.test_id}"
    print(message)
    return 3
  except (RuntimeError, ValueError) as error:
    recorder.record("test_finished", result="BLOCKED", error=str(error))
    print(f"BLOCKED: {error}", file=sys.stderr)
    return 1


def main() -> int:
  parser = argparse.ArgumentParser(description="Tesla RX-template speed-button CAN validation")
  parser.add_argument("action", choices=(SpeedButtonAction.increase.value, SpeedButtonAction.decrease.value))
  args = parser.parse_args()
  return run_validation(SpeedButtonAction(args.action))


if __name__ == "__main__":
  raise SystemExit(main())
