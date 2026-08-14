from opendbc.car.can_definitions import CanData
from opendbc.car.common.conversions import Conversions as CV
from opendbc.car.tesla.speed_sync_log import get_speed_sync_logger, log_speed_sync


SPEED_BUTTON_ADDRESS = 0x3C2
VEHICLE_BUS = 1
TEMPLATE_TIMEOUT_NS = 1_500_000_000
MIN_TX_INTERVAL_NS = 1_000_000_000
FEEDBACK_TIMEOUT_NS = 1_200_000_000
TARGET_STABLE_NS = 500_000_000
MANUAL_RESUME_GESTURE_NS = 1_000_000_000
BATCH_SIZE = 5
BATCH_COOLDOWN_NS = 5_000_000_000


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
    self.planned_target_display: int | None = None
    self.last_current_display: int | None = None
    self.target_candidate: int | None = None
    self.target_candidate_nanos = 0
    self.last_tx_nanos = 0
    self.pending_direction = 0
    self.pending_display_speed = 0
    self.pending_since_nanos = 0
    self.feedback_blocked_signature: tuple[int, int] | None = None
    self.batch_sent = 0
    self.batch_direction = 0
    self.batch_cooldown_until_nanos = 0
    self.session_tick_count = 0
    self._session_active_prev = False
    self.log = get_speed_sync_logger()
    self._last_status_signature = None
    self._last_tx_data: bytes | None = None
    self._acc_faulted_prev = False
    self._status = {"state": "disabled" if not configured else "idle", "configured": configured}

  def observe(self, monotonic_nanos: int, address: int, data: bytes, source: int) -> None:
    if address != SPEED_BUTTON_ADDRESS:
      return
    data = bytes(data)
    if not is_speed_button_frame(data):
      return
    tick = signed_wheel_tick(data)
    if source != VEHICLE_BUS:
      if source >= 128 and tick != 0:
        log_speed_sync(self.log, "returned_3c2", monotonic_nanos=int(monotonic_nanos), source=source,
                       tick=tick, data=data.hex(),
                       last_tx_age_ms=(int(monotonic_nanos) - self.last_tx_nanos) / 1e6 if self.last_tx_nanos else None)
      return
    if tick == 0:
      self.template = data
      self.template_nanos = int(monotonic_nanos)
      return

    direction = 1 if tick > 0 else -1
    now_nanos = int(monotonic_nanos)
    self.manual_adjustment_counter += 1
    gesture = False
    if (self._manual_direction == -direction and self._manual_direction_nanos and
        now_nanos - self._manual_direction_nanos <= MANUAL_RESUME_GESTURE_NS):
      self.resume_gesture_counter += 1
      gesture = True
      self._manual_direction = 0
      self._manual_direction_nanos = 0
    else:
      self._manual_direction = direction
      self._manual_direction_nanos = now_nanos
    log_speed_sync(self.log, "manual_tick", monotonic_nanos=now_nanos, source=source,
                   direction=direction, raw_tick=tick, data=data.hex(), resume_gesture=gesture)

  def _clear_pending(self) -> None:
    self.pending_direction = 0
    self.pending_display_speed = 0
    self.pending_since_nanos = 0

  def _reset_target(self) -> None:
    self.target_candidate = None
    self.target_candidate_nanos = 0
    self.feedback_blocked_signature = None
    self.batch_sent = 0
    self.batch_direction = 0
    self.batch_cooldown_until_nanos = 0
    self._clear_pending()

  def _reset_runtime(self, *, clear_manual_override: bool) -> None:
    self._reset_target()
    self.planned_target_display = None
    self.last_current_display = None
    if clear_manual_override:
      self.manual_override = False

  @staticmethod
  def _display_speed(speed_mps: float, units: str) -> int:
    factor = CV.MS_TO_MPH if units == "MPH" else CV.MS_TO_KPH
    return round(float(speed_mps) * factor)

  def _set_status(self, state: str, **values) -> None:
    self._status = {"state": state, "configured": self.configured, "manual_override": self.manual_override, **values}
    signature = tuple(sorted(self._status.items()))
    if signature != self._last_status_signature:
      self._last_status_signature = signature
      log_speed_sync(self.log, "status", **self._status)

  def update(self, CC, CS, target_mps: float, target_valid: bool, now_nanos: int) -> list[CanData]:
    now_nanos = int(now_nanos)
    units = getattr(CS, "tesla_speed_units", "KPH")
    current_display = self._display_speed(CS.out.cruiseState.speed, units)
    target_display = self._display_speed(target_mps, units) if target_valid else 0
    session_active = bool(CC.enabled)
    if session_active and not self._session_active_prev:
      self.session_tick_count = 0
    self._session_active_prev = session_active

    acc_faulted = bool(getattr(CS.out, "accFaulted", False))
    if acc_faulted and not self._acc_faulted_prev:
      log_speed_sync(self.log, "acc_faulted", warning=True, monotonic_nanos=now_nanos,
                     last_tx_age_ms=(now_nanos - self.last_tx_nanos) / 1e6 if self.last_tx_nanos else None,
                     last_tx_data=self._last_tx_data.hex() if self._last_tx_data is not None else None,
                     current=current_display, target=target_display, unit=units,
                     manual_override=self.manual_override, cc_enabled=bool(CC.enabled),
                     cc_long_active=bool(CC.longActive), cruise_enabled=bool(CS.out.cruiseState.enabled),
                     batch_sent=self.batch_sent,
                     session_tick_count=self.session_tick_count,
                     batch_cooldown_remaining_ms=max(0, self.batch_cooldown_until_nanos - now_nanos) / 1e6)
    self._acc_faulted_prev = acc_faulted

    manual_changed = self.manual_adjustment_counter != self._seen_manual_counter
    resumed = self.resume_gesture_counter != self._seen_resume_counter
    if manual_changed:
      self._seen_manual_counter = self.manual_adjustment_counter
      self._seen_resume_counter = self.resume_gesture_counter

    blocked_reason = None
    clear_manual_override = False
    if not self.configured:
      blocked_reason = "disabled"
      clear_manual_override = True
    elif getattr(CS, "tesla_autopilot_active", False):
      blocked_reason = "tesla_ap_active"
    elif not CC.enabled:
      blocked_reason = "controls_inactive"
      clear_manual_override = True
    elif CC.cruiseControl.cancel or not CS.out.cruiseState.enabled:
      blocked_reason = "cruise_inactive"
    elif acc_faulted:
      blocked_reason = "acc_faulted"
    elif CS.out.brakePressed:
      blocked_reason = "brake_pressed"
    elif not target_valid:
      blocked_reason = "target_invalid"

    if blocked_reason is not None:
      self._reset_runtime(clear_manual_override=clear_manual_override)
      self._set_status("blocked", reason=blocked_reason, current=current_display, target=target_display, unit=units)
      return []

    target_changed = self.planned_target_display != target_display
    if target_changed:
      self.planned_target_display = target_display
      self._reset_target()

    if resumed:
      self.manual_override = False
      self._reset_target()
      log_speed_sync(self.log, "manual_resume_gesture", monotonic_nanos=now_nanos,
                     current=current_display, target=target_display, unit=units)
    elif manual_changed:
      self.manual_override = True
      self._reset_target()

    target_stable = (self.target_candidate == target_display and
                     now_nanos - self.target_candidate_nanos >= TARGET_STABLE_NS)
    external_speed_change = (self.last_current_display is not None and current_display != self.last_current_display and
                             not self.pending_direction and self.feedback_blocked_signature is None and target_stable and
                             not target_changed and not manual_changed and not resumed)
    self.last_current_display = current_display
    if external_speed_change:
      self.manual_override = True
      self._reset_target()

    if self.manual_override:
      self._set_status("blocked", reason="manual_override", current=current_display, target=target_display, unit=units)
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
      feedback_direction = self.pending_direction
      feedback_delta = current_display - self.pending_display_speed
      feedback_received = feedback_delta * feedback_direction > 0
      if not feedback_received and now_nanos - self.pending_since_nanos < FEEDBACK_TIMEOUT_NS:
        self._set_status("waiting_feedback", current=current_display, target=target_display, unit=units)
        return []
      self._clear_pending()
      log_speed_sync(self.log, "feedback", monotonic_nanos=now_nanos, received=feedback_received,
                     delta=feedback_delta, direction=feedback_direction,
                     current=current_display, target=target_display, unit=units)
      if not feedback_received:
        self.feedback_blocked_signature = signature
      elif self.batch_sent >= BATCH_SIZE and target_display != current_display:
        self.batch_sent = 0
        self.batch_cooldown_until_nanos = now_nanos + BATCH_COOLDOWN_NS
        remaining = target_display - current_display
        self._set_status("batch_cooldown", current=current_display, target=target_display, unit=units,
                         remaining=remaining, cooldown_ms=BATCH_COOLDOWN_NS / 1e6)
        log_speed_sync(self.log, "batch_pause", monotonic_nanos=now_nanos, current=current_display,
                       target=target_display, unit=units, remaining=remaining,
                       cooldown_ms=BATCH_COOLDOWN_NS / 1e6)
        return []

    if self.feedback_blocked_signature is not None:
      if signature == self.feedback_blocked_signature:
        self._set_status("blocked", reason="feedback_timeout", current=current_display, target=target_display, unit=units)
        return []
      self.feedback_blocked_signature = None

    remaining = target_display - current_display
    if remaining == 0:
      self._set_status("synced", current=current_display, target=target_display, unit=units)
      return []
    if self.batch_cooldown_until_nanos:
      if now_nanos < self.batch_cooldown_until_nanos:
        cooldown_remaining_ns = self.batch_cooldown_until_nanos - now_nanos
        self._set_status("batch_cooldown", current=current_display, target=target_display, unit=units,
                         remaining=remaining,
                         cooldown_s=(cooldown_remaining_ns + 999_999_999) // 1_000_000_000)
        return []
      log_speed_sync(self.log, "batch_resume", monotonic_nanos=now_nanos, current=current_display,
                     target=target_display, unit=units, remaining=remaining)
      self.batch_cooldown_until_nanos = 0
    if self.last_tx_nanos and now_nanos - self.last_tx_nanos < MIN_TX_INTERVAL_NS:
      self._set_status("rate_limited", current=current_display, target=target_display, unit=units, remaining=remaining)
      return []
    if self.template is None or now_nanos - self.template_nanos > TEMPLATE_TIMEOUT_NS:
      self._set_status("blocked", reason="template_stale", current=current_display, target=target_display, unit=units)
      return []

    direction = 1 if remaining > 0 else -1
    if direction != self.batch_direction:
      self.batch_direction = direction
      self.batch_sent = 0
    data = build_speed_tick(self.template, direction)
    self.last_tx_nanos = now_nanos
    self._last_tx_data = data
    self.pending_direction = direction
    self.pending_display_speed = current_display
    self.pending_since_nanos = now_nanos
    self.batch_sent += 1
    self.session_tick_count += 1
    self._set_status("tick_sent", current=current_display, target=target_display, unit=units,
                     direction=direction, remaining=remaining, batch_sent=self.batch_sent, batch_size=BATCH_SIZE)
    log_speed_sync(self.log, "tick_sent", monotonic_nanos=now_nanos, current=current_display,
                   target=target_display, unit=units, direction=direction, remaining=remaining,
                   data=data.hex(), template_age_ms=(now_nanos - self.template_nanos) / 1e6,
                   batch_sent=self.batch_sent, batch_size=BATCH_SIZE,
                   session_tick_count=self.session_tick_count)
    return [CanData(SPEED_BUTTON_ADDRESS, data, VEHICLE_BUS)]

  def status(self) -> dict:
    return dict(self._status)
