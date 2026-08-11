from dataclasses import dataclass, field

from cereal import log
from opendbc.can.dbc import DBC
from opendbc.can.parser import get_raw_value
from opendbc.car.can_definitions import CanData


TURN_SIGNAL_ADDRESS = 0x3E9
UI_WARNING_ADDRESS = 0x311
FRONT_LIGHTING_ADDRESS = 0x3F5
VEHICLE_BUS = 1
PARTY_BUS = 0
TEMPLATE_TIMEOUT_NS = 1_500_000_000
ECHO_TIMEOUT_NS = 1_200_000_000
FEEDBACK_TIMEOUT_NS = 2_500_000_000
CANCEL_FEEDBACK_TIMEOUT_NS = 1_500_000_000
CANCEL_SEND_TIMEOUT_NS = 1_500_000_000
CANCEL_TOTAL_TIMEOUT_NS = 5_000_000_000
SESSION_TIMEOUT_NS = 12_000_000_000
CONTEXT_TIMEOUT_NS = 1_000_000_000
MAX_CANCEL_ATTEMPTS = 3

_TURN_REQUEST = {"left": 1, "right": 2, "cancel": 3}
_UI_WARNING = DBC("tesla_model3_party").name_to_msg["UI_warning"]
_FRONT_LIGHTING = DBC("tesla_model3_vehicle").name_to_msg["ID3F5VCFRONT_lighting"]


def can_source(source: int) -> tuple[int, str]:
  if source >= 0xC0:
    return source - 0xC0, "rejected"
  if source >= 0x80:
    return source - 0x80, "txEcho"
  return source, "rx"


def body_controls_checksum(data: bytes | bytearray) -> int:
  if len(data) != 8:
    raise ValueError("Tesla 0x3E9 must be 8 bytes")
  return (0xE9 + 0x03 + sum(data[:7])) & 0xFF


def decode_body_controls(data: bytes) -> dict[str, int]:
  if len(data) != 8:
    raise ValueError("Tesla 0x3E9 must be 8 bytes")
  return {
    "request": data[1] & 0x03,
    "reason": (data[2] >> 1) & 0x0F,
    "counter": (data[6] >> 4) & 0x0F,
    "checksum": data[7],
  }


def is_idle_template(address: int, source: int, data: bytes) -> bool:
  return (address == TURN_SIGNAL_ADDRESS and source == VEHICLE_BUS and len(data) == 8 and
          decode_body_controls(data)["request"] == 0 and body_controls_checksum(data) == data[7])


def build_turn_frame(template: bytes, direction: str) -> bytes:
  if direction not in _TURN_REQUEST:
    raise ValueError(f"invalid turn direction: {direction}")
  if not is_idle_template(TURN_SIGNAL_ADDRESS, VEHICLE_BUS, template):
    raise ValueError("invalid Tesla 0x3E9 idle template")

  data = bytearray(template)
  data[1] = (data[1] & 0xFC) | _TURN_REQUEST[direction]
  reason = 4 if direction == "cancel" else 8
  data[2] = (data[2] & 0xE1) | (reason << 1)
  next_counter = (decode_body_controls(template)["counter"] + 1) & 0x0F
  data[6] = (data[6] & 0x0F) | (next_counter << 4)
  data[7] = body_controls_checksum(data)
  return bytes(data)


def _blinker_feedback(address: int, data: bytes, direction: str) -> bool | None:
  if address == UI_WARNING_ADDRESS and len(data) == 7:
    signal = "leftBlinkerBlinking" if direction == "left" else "rightBlinkerBlinking"
    return int(get_raw_value(data, _UI_WARNING.sigs[signal])) in (1, 2)
  if address == FRONT_LIGHTING_ADDRESS and len(data) == 8:
    signal = "VCFRONT_turnSignalLeftStatus" if direction == "left" else "VCFRONT_turnSignalRightStatus"
    return int(get_raw_value(data, _FRONT_LIGHTING.sigs[signal])) == 1
  return None


@dataclass
class TurnSignalSession:
  test_id: str
  direction: str
  started_nanos: int
  origin: str = "web_test"
  phase: str = "waiting_vehicle_feedback"
  last_context_nanos: int = 0
  lane_change_started: bool = False
  cancel_requested: bool = False
  cancel_requested_nanos: int = 0
  cancel_reason: str | None = None
  action_frames_sent: int = 0
  action_frames_echoed: int = 0
  cancel_attempts: int = 0
  cancel_echoed: bool = False
  feedback: bool = False
  tx_echo: bool = False
  rejected: bool = False
  used_template_generation: int = -1
  awaiting_data: bytes | None = None
  awaiting_phase: str | None = None
  awaiting_since_nanos: int = 0
  finalize_nanos: int = 0
  events: list[dict] = field(default_factory=list)


class TurnSignalController:
  def __init__(self, configured: bool, *, auto_configured: bool = False):
    self.test_configured = configured
    self.auto_configured = auto_configured
    self.session: TurnSignalSession | None = None
    self.template: bytes | None = None
    self.template_nanos = 0
    self.template_generation = 0
    self._completed: list[dict] = []
    self._auto_session_counter = 0

  def _finish(self, result: str, now_nanos: int, **extra) -> None:
    if self.session is None:
      return
    session = self.session
    self._completed.append({
      "test_id": session.test_id,
      "origin": session.origin,
      "direction": session.direction,
      "result": result,
      "feedback": session.feedback,
      "tx_echo": session.tx_echo,
      "rejected": session.rejected,
      "action_frames_sent": session.action_frames_sent,
      "cancel_sent": session.cancel_attempts > 0,
      "cancel_attempts": session.cancel_attempts,
      "cancel_reason": session.cancel_reason,
      "lane_change_started": session.lane_change_started,
      "finished_nanos": int(now_nanos),
      **extra,
    })
    self.session = None

  def submit(self, test_id: str, direction: str, now_nanos: int) -> bool:
    if direction not in ("left", "right"):
      raise ValueError(f"invalid turn direction: {direction}")
    if not self.test_configured:
      self._completed.append({"test_id": test_id, "direction": direction, "result": "BLOCKED",
                              "error": "EnableTeslaTools was disabled when card initialized"})
      return False
    if self.session is not None:
      self._completed.append({"test_id": test_id, "direction": direction, "result": "BUSY"})
      return False
    self.session = TurnSignalSession(test_id=test_id, direction=direction, started_nanos=int(now_nanos))
    return True

  def _start_automatic(self, direction: str, now_nanos: int) -> None:
    self._auto_session_counter += 1
    self.session = TurnSignalSession(
      test_id=f"auto-lane-change-{self._auto_session_counter}",
      direction=direction,
      started_nanos=int(now_nanos),
      origin="automatic_lane_change",
    )

  def _request_cancel(self, reason: str, now_nanos: int) -> None:
    if self.session is None or self.session.cancel_requested:
      return
    if self.session.action_frames_sent == 0:
      self._finish("CANCELLED_BEFORE_SEND", now_nanos, requested_cancel_reason=reason)
      return
    self.session.cancel_requested = True
    self.session.cancel_requested_nanos = int(now_nanos)
    self.session.cancel_reason = reason
    self.session.phase = "cancelling"

  def cancel(self, test_id: str | None, now_nanos: int) -> bool:
    if self.session is None or (test_id is not None and test_id != self.session.test_id):
      return False
    self._request_cancel("web_cancel", now_nanos)
    return True

  def update_lane_change_context(self, now_nanos: int, *, valid: bool, state: int, direction: int,
                                 lateral_active: bool, brake_pressed: bool,
                                 vehicle_left_blinker: bool = False,
                                 vehicle_right_blinker: bool = False,
                                 automatic_direction: str = "none") -> None:
    now_nanos = int(now_nanos)
    vehicle_blinker_active = vehicle_left_blinker or vehicle_right_blinker
    if (self.session is None and self.auto_configured and valid and lateral_active and not brake_pressed and
        state in (log.LaneChangeState.preLaneChange, log.LaneChangeState.laneChangeStarting) and
        not vehicle_blinker_active):
      if direction == log.LaneChangeDirection.left and automatic_direction == "left":
        self._start_automatic("left", now_nanos)
      elif direction == log.LaneChangeDirection.right and automatic_direction == "right":
        self._start_automatic("right", now_nanos)

    if self.session is None or self.session.cancel_requested:
      return
    if brake_pressed:
      self._request_cancel("brake_pressed", now_nanos)
      return
    if not lateral_active:
      self._request_cancel("lateral_inactive", now_nanos)
      return
    if not valid:
      reference = self.session.last_context_nanos or self.session.started_nanos
      if now_nanos - reference >= CONTEXT_TIMEOUT_NS:
        self._request_cancel("lane_change_context_stale", now_nanos)
      return

    self.session.last_context_nanos = now_nanos
    requested = log.LaneChangeDirection.left if self.session.direction == "left" else log.LaneChangeDirection.right
    if state in (log.LaneChangeState.preLaneChange, log.LaneChangeState.laneChangeStarting) and direction != requested:
      self._request_cancel("lane_change_direction_mismatch", now_nanos)
    elif state == log.LaneChangeState.preLaneChange:
      if self.session.lane_change_started:
        self._request_cancel("lane_change_cycle_complete", now_nanos)
      else:
        self.session.phase = "waiting_sp_start"
    elif state == log.LaneChangeState.laneChangeStarting:
      self.session.lane_change_started = True
      self.session.phase = "lane_changing"
    elif state == log.LaneChangeState.laneChangeFinishing and self.session.lane_change_started:
      self.session.phase = "lane_change_finishing"
    elif state == log.LaneChangeState.off and self.session.lane_change_started:
      self._request_cancel("lane_change_complete", now_nanos)
    elif (state == log.LaneChangeState.off and self.session.origin == "automatic_lane_change"):
      self._request_cancel("lane_change_aborted", now_nanos)

  def observe(self, monotonic_nanos: int, address: int, data: bytes, source: int) -> None:
    data = bytes(data)
    if is_idle_template(address, source, data):
      self.template = data
      self.template_nanos = int(monotonic_nanos)
      self.template_generation += 1
    if self.session is None:
      return

    bus, direction = can_source(source)
    if address == TURN_SIGNAL_ADDRESS and data == self.session.awaiting_data:
      phase = self.session.awaiting_phase
      if direction == "rejected":
        self.session.rejected = True
        self.session.awaiting_data = None
        self.session.awaiting_phase = None
        if phase == "action" and self.session.action_frames_echoed:
          self._request_cancel("action_panda_rejected", monotonic_nanos)
        elif phase == "cancel" and self.session.cancel_attempts > 1:
          self.session.cancel_echoed = True
          self.session.phase = "confirming_cancel"
          self.session.finalize_nanos = int(monotonic_nanos) + CANCEL_FEEDBACK_TIMEOUT_NS
        else:
          self._finish("PANDA_REJECTED", monotonic_nanos)
        return
      if direction == "txEcho":
        self.session.tx_echo = True
        self.session.awaiting_data = None
        self.session.awaiting_phase = None
        if phase == "action":
          self.session.action_frames_echoed += 1
        else:
          self.session.cancel_echoed = True
          self.session.phase = "confirming_cancel"
          self.session.finalize_nanos = int(monotonic_nanos) + CANCEL_FEEDBACK_TIMEOUT_NS
        return

    feedback_bus = PARTY_BUS if address == UI_WARNING_ADDRESS else VEHICLE_BUS
    if direction != "rx" or bus != feedback_bus:
      return
    active = _blinker_feedback(address, data, self.session.direction)
    if active is True and not self.session.feedback:
      self.session.feedback = True
      if not self.session.cancel_requested:
        self.session.phase = "waiting_sp_start"
    elif (active is False and address == FRONT_LIGHTING_ADDRESS and self.session.feedback and
          self.session.cancel_echoed):
      self._finish("PASS", monotonic_nanos)

  def take_can_sends(self, now_nanos: int, *, cancel_only: bool = False) -> list[CanData]:
    if self.session is None or self.session.awaiting_data is not None:
      return []
    if cancel_only and not self.session.cancel_requested:
      return []
    if self.session.finalize_nanos or self.template is None:
      return []
    if self.session.used_template_generation == self.template_generation:
      return []
    if int(now_nanos) - self.template_nanos > TEMPLATE_TIMEOUT_NS:
      return []

    phase = "cancel" if self.session.cancel_requested else "action"
    direction = "cancel" if phase == "cancel" else self.session.direction
    data = build_turn_frame(self.template, direction)
    self.session.used_template_generation = self.template_generation
    self.session.awaiting_data = data
    self.session.awaiting_phase = phase
    self.session.awaiting_since_nanos = int(now_nanos)
    if phase == "action":
      self.session.action_frames_sent += 1
    else:
      self.session.cancel_attempts += 1
    return [CanData(TURN_SIGNAL_ADDRESS, data, VEHICLE_BUS)]

  def advance_time(self, now_nanos: int) -> None:
    if self.session is None:
      return
    now_nanos = int(now_nanos)
    if self.session.finalize_nanos and now_nanos >= self.session.finalize_nanos:
      self._finish("CANCEL_NOT_CONFIRMED", now_nanos)
    elif self.session.awaiting_data is not None and now_nanos - self.session.awaiting_since_nanos >= ECHO_TIMEOUT_NS:
      if self.session.awaiting_phase == "action":
        self.session.awaiting_data = None
        self.session.awaiting_phase = None
        self._request_cancel("action_tx_echo_timeout", now_nanos)
      elif self.session.cancel_attempts < MAX_CANCEL_ATTEMPTS:
        self.session.awaiting_data = None
        self.session.awaiting_phase = None
      else:
        self._finish("NO_TX_ECHO", now_nanos)
    elif (self.session.cancel_requested and self.session.cancel_attempts == 0 and
          now_nanos - self.session.cancel_requested_nanos >= CANCEL_SEND_TIMEOUT_NS):
      self._finish("CANCEL_NOT_SENT", now_nanos)
    elif (not self.session.cancel_requested and not self.session.feedback and
          now_nanos - self.session.started_nanos >= FEEDBACK_TIMEOUT_NS):
      self._request_cancel("vehicle_feedback_timeout", now_nanos)
    elif (self.session.cancel_requested and
          now_nanos - self.session.cancel_requested_nanos >= CANCEL_TOTAL_TIMEOUT_NS):
      self._finish("CANCEL_TIMEOUT", now_nanos)
    elif now_nanos - self.session.started_nanos >= SESSION_TIMEOUT_NS:
      self._request_cancel("session_timeout", now_nanos)

  def status(self) -> dict | None:
    if self.session is None:
      return None
    return {
      "test_id": self.session.test_id,
      "origin": self.session.origin,
      "direction": self.session.direction,
      "phase": self.session.phase,
      "feedback": self.session.feedback,
      "tx_echo": self.session.tx_echo,
      "action_frames_sent": self.session.action_frames_sent,
      "cancel_requested": self.session.cancel_requested,
      "cancel_reason": self.session.cancel_reason,
    }

  def drain_completed(self) -> list[dict]:
    completed = self._completed
    self._completed = []
    return completed
