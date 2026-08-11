from opendbc.car.can_definitions import CanData
from opendbc.car.common.conversions import Conversions as CV


SPEED_BUTTON_ADDRESS = 0x3C2
VEHICLE_BUS = 1
TEMPLATE_TIMEOUT_NS = 1_500_000_000
MIN_TX_INTERVAL_NS = 500_000_000
FEEDBACK_TIMEOUT_NS = 1_200_000_000
TARGET_STABLE_NS = 500_000_000
MANUAL_RESUME_GESTURE_NS = 1_000_000_000


def signed_wheel_tick(data: bytes) -> int:
  raw = data[3] & 0x3F
  return raw - 0x40 if raw & 0x20 else raw


def is_speed_button_frame(data: bytes) -> bool:
  return len(data) == 8 and (data[0] & 0x03) == 1


def build_speed_tick(template: bytes, direction: int) -> bytes:
  if not is_speed_button_frame(template) or signed_wheel_tick(template) != 0:
    raise ValueError("invalid Tesla 0x3C2 idle template")
  if direction not in (-1, 1):
    raise ValueError("speed sync tick must be -1 or +1")
  data = bytearray(template)
  data[3] = (data[3] & 0xC0) | (direction & 0x3F)
  return bytes(data)


class SpeedSyncController:
  def __init__(self, configured: bool):
    self.configured = configured
    self.template: bytes | None = None
    self.template_nanos = 0
    self.manual_adjustment_counter = 0
    self.resume_gesture_counter = 0
    self._manual_direction = 0
    self._manual_direction_nanos = 0
    self._seen_manual_counter = 0
    self._seen_resume_counter = 0
    self.manual_override = False
    self.target_candidate: int | None = None
    self.target_candidate_nanos = 0
    self.last_tx_nanos = 0
    self.pending_direction = 0
    self.pending_display_speed = 0
    self.pending_since_nanos = 0
    self.feedback_blocked_signature: tuple[int, int] | None = None
    self._status = {"state": "disabled" if not configured else "idle", "configured": configured}

  def observe(self, monotonic_nanos: int, address: int, data: bytes, source: int) -> None:
    if address != SPEED_BUTTON_ADDRESS or source != VEHICLE_BUS:
      return
    data = bytes(data)
    if not is_speed_button_frame(data):
      return
    tick = signed_wheel_tick(data)
    if tick == 0:
      self.template = data
      self.template_nanos = int(monotonic_nanos)
      return

    direction = 1 if tick > 0 else -1
    now_nanos = int(monotonic_nanos)
    self.manual_adjustment_counter += 1
    if (self._manual_direction == -direction and self._manual_direction_nanos and
        now_nanos - self._manual_direction_nanos <= MANUAL_RESUME_GESTURE_NS):
      self.resume_gesture_counter += 1
      self._manual_direction = 0
      self._manual_direction_nanos = 0
    else:
      self._manual_direction = direction
      self._manual_direction_nanos = now_nanos

  def _clear_pending(self) -> None:
    self.pending_direction = 0
    self.pending_display_speed = 0
    self.pending_since_nanos = 0

  def _reset_target(self) -> None:
    self.target_candidate = None
    self.target_candidate_nanos = 0
    self.feedback_blocked_signature = None
    self._clear_pending()

  @staticmethod
  def _display_speed(speed_mps: float, units: str) -> int:
    factor = CV.MS_TO_MPH if units == "MPH" else CV.MS_TO_KPH
    return round(float(speed_mps) * factor)

  def _set_status(self, state: str, **values) -> None:
    self._status = {"state": state, "configured": self.configured, "manual_override": self.manual_override, **values}

  def update(self, CC, CS, target_mps: float, target_valid: bool, now_nanos: int) -> list[CanData]:
    now_nanos = int(now_nanos)
    units = getattr(CS, "tesla_speed_units", "KPH")
    current_display = self._display_speed(CS.out.cruiseState.speed, units)
    target_display = self._display_speed(target_mps, units) if target_valid else 0

    if self.manual_adjustment_counter != self._seen_manual_counter:
      resumed = self.resume_gesture_counter != self._seen_resume_counter
      self._seen_manual_counter = self.manual_adjustment_counter
      self._seen_resume_counter = self.resume_gesture_counter
      self.manual_override = not resumed
      self._reset_target()

    blocked_reason = None
    if not self.configured:
      blocked_reason = "disabled"
    elif getattr(CS, "tesla_autopilot_active", False):
      blocked_reason = "tesla_ap_active"
    elif not CC.enabled or not CC.longActive:
      blocked_reason = "longitudinal_inactive"
    elif CC.cruiseControl.cancel or not CS.out.cruiseState.enabled:
      blocked_reason = "cruise_inactive"
    elif CS.out.brakePressed:
      blocked_reason = "brake_pressed"
    elif not target_valid:
      blocked_reason = "target_invalid"
    elif self.manual_override:
      blocked_reason = "manual_override"

    if blocked_reason is not None:
      self._reset_target()
      self._set_status("blocked", reason=blocked_reason, current=current_display, target=target_display, unit=units)
      return []

    if self.target_candidate != target_display:
      self.target_candidate = target_display
      self.target_candidate_nanos = now_nanos
      self.feedback_blocked_signature = None
      self._clear_pending()
      self._set_status("stabilizing", current=current_display, target=target_display, unit=units)
      return []
    if now_nanos - self.target_candidate_nanos < TARGET_STABLE_NS:
      self._set_status("stabilizing", current=current_display, target=target_display, unit=units)
      return []

    signature = (target_display, current_display)
    if self.pending_direction:
      feedback_delta = current_display - self.pending_display_speed
      feedback_received = feedback_delta * self.pending_direction > 0
      if not feedback_received and now_nanos - self.pending_since_nanos < FEEDBACK_TIMEOUT_NS:
        self._set_status("waiting_feedback", current=current_display, target=target_display, unit=units)
        return []
      self._clear_pending()
      if not feedback_received:
        self.feedback_blocked_signature = signature

    if self.feedback_blocked_signature is not None:
      if signature == self.feedback_blocked_signature:
        self._set_status("blocked", reason="feedback_timeout", current=current_display, target=target_display, unit=units)
        return []
      self.feedback_blocked_signature = None

    remaining = target_display - current_display
    if remaining == 0:
      self._set_status("synced", current=current_display, target=target_display, unit=units)
      return []
    if self.last_tx_nanos and now_nanos - self.last_tx_nanos < MIN_TX_INTERVAL_NS:
      self._set_status("rate_limited", current=current_display, target=target_display, unit=units, remaining=remaining)
      return []
    if self.template is None or now_nanos - self.template_nanos > TEMPLATE_TIMEOUT_NS:
      self._set_status("blocked", reason="template_stale", current=current_display, target=target_display, unit=units)
      return []

    direction = 1 if remaining > 0 else -1
    data = build_speed_tick(self.template, direction)
    self.last_tx_nanos = now_nanos
    self.pending_direction = direction
    self.pending_display_speed = current_display
    self.pending_since_nanos = now_nanos
    self._set_status("tick_sent", current=current_display, target=target_display, unit=units,
                     direction=direction, remaining=remaining)
    return [CanData(SPEED_BUTTON_ADDRESS, data, VEHICLE_BUS)]

  def status(self) -> dict:
    return dict(self._status)
