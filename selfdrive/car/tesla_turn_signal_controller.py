import json
import os
import threading
import time

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
ACTION_FRAME_COUNT = 5
TEMPLATE_MAX_AGE_NS = 1_500_000_000
ECHO_TIMEOUT_NS = 1_200_000_000
SESSION_TIMEOUT_NS = 8_000_000_000
FEEDBACK_AFTER_CANCEL_NS = 500_000_000
REQUEST_PARAM = "TeslaTurnSignalTestRequest"
RESULT_PARAM = "TeslaTurnSignalTestResult"
VALIDATION_LOG_PATH = "/data/tesla_turn_signal_validation.log"
VALIDATION_LOG_PREFIX = "[TESLA-TURN-SIGNAL-VALIDATION-v3]"
MAX_LOG_BYTES = 2 * 1024 * 1024

_UI_WARNING_MESSAGE = DBC("tesla_model3_party").name_to_msg["UI_warning"]
_FRONT_LIGHTING_MESSAGE = DBC("tesla_model3_vehicle").name_to_msg["ID3F5VCFRONT_lighting"]


def source_details(source: int) -> tuple[int, str]:
  if source >= 0xC0:
    return source - 0xC0, "rejected"
  if source >= 0x80:
    return source - 0x80, "txEcho"
  return source, "rx"


def tesla_body_controls_checksum(data: bytes | bytearray) -> int:
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
          tesla_body_controls_checksum(data) == data[7] and decode_body_controls(data)["turn_request"] == 0)


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


def persist_validation_records(records: list[dict], log_path: str = VALIDATION_LOG_PATH) -> None:
  if not records:
    return
  try:
    if os.path.exists(log_path) and os.path.getsize(log_path) > MAX_LOG_BYTES:
      os.replace(log_path, f"{log_path}.1")
    lines = "".join(json.dumps(record, sort_keys=True, default=str) + "\n" for record in records)
    with open(log_path, "a", encoding="utf-8") as log_file:
      log_file.write(lines)
  except OSError:
    pass


class TeslaTurnSignalRealtimeController:
  def __init__(self, configured: bool):
    self.configured = configured
    self._lock = threading.Lock()
    self._active = None
    self._completed: list[tuple[dict, list[dict]]] = []
    self._template = None
    self._template_nanos = 0
    self._template_generation = 0

  def _record_locked(self, event: str, now_nanos: int, **values) -> None:
    if self._active is None:
      return
    self._active["records"].append({
      "prefix": VALIDATION_LOG_PREFIX,
      "test_id": self._active["test_id"],
      "wall_time_ns": time.time_ns(),
      "monotonic_ns": int(now_nanos),
      "direction": self._active["direction"],
      "event": event,
      **values,
    })

  def _finish_locked(self, result: str, now_nanos: int, **extra) -> None:
    if self._active is None:
      return
    session = self._active
    payload = {
      "test_id": session["test_id"],
      "direction": session["direction"],
      "result": result,
      "feedback": session["feedback"],
      "tx_echo": session["tx_echo"],
      "rejected": session["rejected"],
      "action_frames_sent": session["action_frames_sent"],
      "cancel_sent": session["cancel_sent"],
      **extra,
    }
    self._record_locked("test_finished", now_nanos, **{key: value for key, value in payload.items() if key != "test_id"})
    self._completed.append((payload, session["records"]))
    self._active = None

  def submit_request(self, test_id: str, direction: str, now_nanos: int) -> bool:
    if direction not in ("left", "right"):
      raise ValueError(f"unsupported turn request: {direction}")
    with self._lock:
      if not self.configured:
        records = [{
          "prefix": VALIDATION_LOG_PREFIX,
          "test_id": test_id,
          "wall_time_ns": time.time_ns(),
          "monotonic_ns": int(now_nanos),
          "direction": direction,
          "event": "test_finished",
          "result": "BLOCKED",
          "error": "TeslaTurnSignalValidation was not enabled when card initialized",
        }]
        result = {
          "test_id": test_id, "direction": direction, "result": "BLOCKED", "feedback": False,
          "tx_echo": False, "rejected": False, "action_frames_sent": 0, "cancel_sent": False,
        }
        self._completed.append((result, records))
        return False
      if self._active is not None:
        result = {
          "test_id": test_id, "direction": direction, "result": "BUSY", "feedback": False,
          "tx_echo": False, "rejected": False, "action_frames_sent": 0, "cancel_sent": False,
        }
        self._completed.append((result, []))
        return False

      self._active = {
        "test_id": test_id,
        "direction": direction,
        "started_nanos": int(now_nanos),
        "used_template_generation": -1,
        "awaiting_data": None,
        "awaiting_phase": None,
        "awaiting_since_nanos": 0,
        "action_frames_sent": 0,
        "cancel_sent": False,
        "feedback": False,
        "tx_echo": False,
        "rejected": False,
        "finalize_nanos": 0,
        "records": [],
      }
      self._record_locked("test_started", now_nanos, address=hex(DAS_BODY_CONTROLS_ADDRESS), execution="card_realtime")
      return True

  def observe_frame(self, monotonic_nanos: int, address: int, data: bytes, source: int) -> None:
    if address not in (DAS_BODY_CONTROLS_ADDRESS, UI_WARNING_ADDRESS, FRONT_LIGHTING_ADDRESS):
      return
    data = bytes(data)
    with self._lock:
      if is_original_body_controls_frame(address, source, data):
        self._template = data
        self._template_nanos = int(monotonic_nanos)
        self._template_generation += 1

      if self._active is None:
        return

      bus, can_direction = source_details(source)
      if address == DAS_BODY_CONTROLS_ADDRESS and data == self._active["awaiting_data"]:
        if can_direction == "rejected":
          self._active["rejected"] = True
          self._record_locked("body_controls_observation", monotonic_nanos, source=source, bus=bus,
                              can_direction=can_direction, data=data.hex(), decoded=decode_body_controls(data))
          self._finish_locked("PANDA_REJECTED", monotonic_nanos)
          return
        if can_direction == "txEcho":
          phase = self._active["awaiting_phase"]
          self._active["tx_echo"] = True
          self._active["awaiting_data"] = None
          self._active["awaiting_phase"] = None
          self._record_locked("body_controls_observation", monotonic_nanos, source=source, bus=bus,
                              can_direction=can_direction, phase=phase, data=data.hex(), decoded=decode_body_controls(data))
          if phase == "cancel":
            if self._active["feedback"]:
              self._finish_locked("PASS", monotonic_nanos)
            else:
              self._active["finalize_nanos"] = int(monotonic_nanos) + FEEDBACK_AFTER_CANCEL_NS
          return

      decoded = None
      if address == UI_WARNING_ADDRESS and bus == PARTY_BUS and can_direction == "rx" and len(data) == 7:
        decoded = decode_ui_warning(data)
      elif address == FRONT_LIGHTING_ADDRESS and bus == VEHICLE_BUS and can_direction == "rx" and len(data) == 8:
        decoded = decode_front_lighting(data)
      if decoded is not None and decoded[f"{self._active['direction']}_blinker"] and not self._active["feedback"]:
        self._active["feedback"] = True
        self._record_locked("vehicle_feedback", monotonic_nanos, source=source, bus=bus, data=data.hex(), decoded=decoded)
        if self._active["finalize_nanos"]:
          self._finish_locked("PASS", monotonic_nanos)

  def take_can_sends(self, now_nanos: int) -> list[CanData]:
    with self._lock:
      if self._active is None or self._active["awaiting_data"] is not None:
        return []
      if self._active["finalize_nanos"] or self._template is None:
        return []
      if self._template_generation == self._active["used_template_generation"]:
        return []
      if int(now_nanos) - self._template_nanos > TEMPLATE_MAX_AGE_NS:
        return []

      phase = "action" if self._active["action_frames_sent"] < ACTION_FRAME_COUNT else "cancel"
      direction = self._active["direction"] if phase == "action" else "cancel"
      counter = (decode_body_controls(self._template)["counter"] + 1) % 16
      data = create_body_control_frame(self._template, direction, counter)
      self._record_locked("baseline_frame", now_nanos, source=VEHICLE_BUS, bus=VEHICLE_BUS,
                          data=self._template.hex(), decoded=decode_body_controls(self._template),
                          template_generation=self._template_generation)
      self._active["used_template_generation"] = self._template_generation
      self._active["awaiting_data"] = data
      self._active["awaiting_phase"] = phase
      self._active["awaiting_since_nanos"] = int(now_nanos)
      if phase == "action":
        self._active["action_frames_sent"] += 1
      else:
        self._active["cancel_sent"] = True
      self._record_locked("frame_submitted", now_nanos, phase=phase, request=TURN_REQUESTS[direction],
                          reason=CANCEL_TURN_REASON if phase == "cancel" else ACTIVE_TURN_REASON,
                          counter=counter, bus=VEHICLE_BUS, data=data.hex(),
                          frame_index=self._active["action_frames_sent"] if phase == "action" else None,
                          frame_count=ACTION_FRAME_COUNT if phase == "action" else None)
      return [CanData(DAS_BODY_CONTROLS_ADDRESS, data, VEHICLE_BUS)]

  def advance_time(self, now_nanos: int) -> None:
    with self._lock:
      if self._active is None:
        return
      now_nanos = int(now_nanos)
      if self._active["finalize_nanos"] and now_nanos >= self._active["finalize_nanos"]:
        self._finish_locked("NO_VEHICLE_FEEDBACK", now_nanos)
      elif (self._active["awaiting_data"] is not None and
            now_nanos - self._active["awaiting_since_nanos"] >= ECHO_TIMEOUT_NS):
        self._finish_locked("NO_TX_ECHO", now_nanos)
      elif now_nanos - self._active["started_nanos"] >= SESSION_TIMEOUT_NS:
        result = "NO_FRESH_TEMPLATE" if self._active["action_frames_sent"] == 0 else "TIMEOUT"
        self._finish_locked(result, now_nanos)

  def drain_completed(self) -> list[tuple[dict, list[dict]]]:
    with self._lock:
      completed = self._completed
      self._completed = []
      return completed

  def service_params(self, params, now_nanos: int | None = None, log_path: str = VALIDATION_LOG_PATH) -> None:
    now_nanos = time.monotonic_ns() if now_nanos is None else int(now_nanos)
    request = params.get(REQUEST_PARAM)
    if request is not None:
      params.remove(REQUEST_PARAM)
      try:
        self.submit_request(str(request["test_id"]), str(request["direction"]), now_nanos)
      except (KeyError, TypeError, ValueError):
        pass

    for result, records in self.drain_completed():
      persist_validation_records(records, log_path)
      params.put(RESULT_PARAM, result)
