from cereal import custom
from opendbc.car import structs

from openpilot.common.swaglog import cloudlog
from openpilot.selfdrive.selfdrived.events import ET


MadsState = custom.MadsState.State
GearShifter = structs.CarState.GearShifter
PARAM_REFRESH_INTERVAL = 5  # 20 Hz at the 100 Hz selfdrived update rate


class MadsSteeringMode:
  REMAIN_ACTIVE = 0
  PAUSE = 1
  DISENGAGE = 2


class ModularAssistiveDrivingSystem:
  """Target-native owner for an independent lateral-control session."""

  def __init__(self, CP, params):
    self.CP = CP
    self.params = params
    self.feature_enabled_at_start = params.get_bool("Mads")
    self.feature_enabled = self.feature_enabled_at_start
    self.feature_disabled_latched = False
    self.user_enabled = params.get_bool("MadsUserEnabled")
    self.available = CP.brand == "tesla" and self.feature_enabled_at_start and not CP.passive
    # This Tesla target has no verified independent steering-enable input.
    # Start MADS through the normal engage path and separate only disengagement.
    steering_mode = params.get_int("MadsSteeringMode")
    self.steering_mode = steering_mode if steering_mode in (0, 1, 2) else MadsSteeringMode.DISENGAGE

    self.state = MadsState.disabled
    self.enabled = False
    self.active = False
    self.controls_mismatch = False
    self.lateral_mismatch_counter = 0

    self._requested = False
    self._selfdrive_enabled_prev = False
    self._brake_pressed_prev = False
    self._param_refresh_counter = 0
    self._pending_exit_reason = ""

    cloudlog.event("mads.config", available=self.available, steering_mode=self.steering_mode,
                   feature_enabled=self.feature_enabled, user_enabled=self.user_enabled,
                   car_brand=CP.brand, passive=CP.passive)

  def _refresh_params(self) -> None:
    refresh_now = self._param_refresh_counter % PARAM_REFRESH_INTERVAL == 0
    self._param_refresh_counter += 1
    if not refresh_now:
      return

    feature_enabled = self.params.get_bool("Mads")
    user_enabled = self.params.get_bool("MadsUserEnabled")

    if feature_enabled != self.feature_enabled:
      previous_feature_enabled = self.feature_enabled
      self.feature_enabled = feature_enabled
      if not feature_enabled:
        # Do not return to legacy control in the middle of a drive. Latch MADS
        # unavailable until all control processes restart with matching config.
        self.feature_disabled_latched = True
        self.available = False
        self._requested = False
        self._pending_exit_reason = "config_disabled"
      cloudlog.event("mads.config_changed", previous_enabled=previous_feature_enabled,
                     enabled=feature_enabled, available=self.available,
                     restart_required=feature_enabled or self.feature_disabled_latched)

    if feature_enabled and (not self.feature_enabled_at_start or self.feature_disabled_latched):
      self.available = False

    if user_enabled != self.user_enabled:
      previous_user_enabled = self.user_enabled
      self.user_enabled = user_enabled
      if not user_enabled:
        self._requested = False
        self._pending_exit_reason = "manual_disarm"
      cloudlog.event("mads.user_request", previous_enabled=previous_user_enabled,
                     enabled=user_enabled, active=self.active,
                     requires_normal_engagement=user_enabled)

  def data_sample(self, panda_states, selfdrive_enabled: bool) -> None:
    if not self.available or not self.active or selfdrive_enabled:
      self.lateral_mismatch_counter = 0
      self.controls_mismatch = False
      return

    mismatch = any(not ps.controlsAllowedLateral for ps in panda_states
                   if ps.safetyModel not in (structs.CarParams.SafetyModel.silent,
                                             structs.CarParams.SafetyModel.noOutput))
    self.lateral_mismatch_counter = self.lateral_mismatch_counter + 1 if mismatch else 0
    controls_mismatch = self.lateral_mismatch_counter >= 200
    if controls_mismatch and not self.controls_mismatch:
      cloudlog.event("mads.panda_lateral_mismatch", mismatch_cycles=self.lateral_mismatch_counter, error=True)
    self.controls_mismatch = controls_mismatch

  def update(self, CS, selfdrive_enabled: bool, selfdrive_active: bool, events) -> None:
    self._refresh_params()

    if not self.available:
      self._requested = False
      self._set_state(MadsState.disabled, self._pending_exit_reason or "not_available")
      self._pending_exit_reason = ""
      self._selfdrive_enabled_prev = selfdrive_enabled
      self._brake_pressed_prev = CS.brakePressed
      return

    selfdrive_rising = selfdrive_enabled and not self._selfdrive_enabled_prev
    brake_rising = CS.brakePressed and not self._brake_pressed_prev
    both_pedals = CS.brakePressed and CS.gasPressed

    if selfdrive_rising and self.user_enabled:
      self._requested = True
    elif selfdrive_rising:
      cloudlog.event("mads.engagement_blocked", reason="user_disarmed")

    steering_disengage = bool(getattr(CS, "steeringDisengage", False))
    unsafe_gear = CS.gearShifter in (GearShifter.park, GearShifter.reverse, GearShifter.neutral, GearShifter.unknown)
    pause_for_brake = self.steering_mode == MadsSteeringMode.PAUSE and CS.brakePressed
    steering_fault = CS.steerFaultTemporary or CS.steerFaultPermanent

    exit_reasons = []
    if steering_disengage:
      exit_reasons.append("steering_disengage")
    if both_pedals:
      exit_reasons.append("both_pedals")
    if self.controls_mismatch:
      exit_reasons.append("panda_lateral_mismatch")
    if CS.invalidLkasSetting:
      exit_reasons.append("invalid_lkas_setting")
    if not CS.cruiseState.available:
      exit_reasons.append("cruise_main_unavailable")
    if unsafe_gear:
      exit_reasons.append("unsafe_gear")
    if steering_fault:
      exit_reasons.append("steering_fault")
    if events.contains(ET.IMMEDIATE_DISABLE):
      exit_reasons.append("immediate_disable_event")
    if events.contains(ET.SOFT_DISABLE):
      exit_reasons.append("soft_disable_event")

    safety_exit = bool(exit_reasons)
    if safety_exit or (brake_rising and self.steering_mode == MadsSteeringMode.DISENGAGE):
      self._requested = False
      if not safety_exit:
        exit_reasons.append("brake_disengage")

    if not self._requested:
      reason = ",".join(exit_reasons) if exit_reasons else self._pending_exit_reason or "not_requested"
      self._set_state(MadsState.disabled, reason)
    elif pause_for_brake:
      self._set_state(MadsState.paused, "brake_pause")
    elif events.contains(ET.OVERRIDE_LATERAL):
      self._set_state(MadsState.overriding, "driver_override")
    else:
      reason = "selfdrive_engaged" if selfdrive_rising else "brake_released" if self.state == MadsState.paused else "requested"
      self._set_state(MadsState.enabled, reason)

    self._selfdrive_enabled_prev = selfdrive_enabled
    self._brake_pressed_prev = CS.brakePressed
    self._pending_exit_reason = ""

  def _set_state(self, state, reason: str = "") -> None:
    previous_state = self.state
    self.state = state
    self.enabled = state != MadsState.disabled
    self.active = state in (MadsState.enabled, MadsState.softDisabling, MadsState.overriding)
    if state != previous_state:
      cloudlog.event("mads.transition", previous_state=str(previous_state), state=str(state), reason=reason,
                     enabled=self.enabled, active=self.active, steering_mode=self.steering_mode,
                     error=state == MadsState.disabled and reason not in ("", "not_requested"))
