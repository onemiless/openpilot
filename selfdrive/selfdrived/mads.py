from cereal import custom
from opendbc.car import DT_CTRL, structs

from openpilot.common.swaglog import cloudlog
from openpilot.selfdrive.selfdrived.events import ET, EVENTS, EventName


MadsState = custom.MadsState.State
GearShifter = structs.CarState.GearShifter
ButtonType = structs.CarState.ButtonEvent.Type
PARAM_REFRESH_INTERVAL = 5  # 20 Hz at the 100 Hz selfdrived update rate
# Resume once the driver is back inside the cooperative blending envelope. The
# steering-rate and dwell checks below still prevent a sudden hand-back while
# the wheel is moving quickly.
DRIVER_OVERRIDE_RELEASE_HANDS_ON_LEVEL = 2
DRIVER_OVERRIDE_RELEASE_TORQUE = 2.5  # Nm
DRIVER_OVERRIDE_RELEASE_STEERING_RATE = 10.0  # deg/s
DRIVER_OVERRIDE_RELEASE_FRAMES = round(0.25 / DT_CTRL)
EPS_TEMP_FAULT_RECOVERY_FRAMES = round(0.25 / DT_CTRL)
EAC_STATUS_INHIBITED = 0
EAC_STATUS_AVAILABLE = 1
EAC_STATUS_ACTIVE = 2
RADAR_SOFT_DISABLE_EVENTS = frozenset((
  EventName.radarFault,
  EventName.radarWrongConfig,
  EventName.radarTempUnavailable,
))

EAC_STATUS_NAMES = {
  EAC_STATUS_INHIBITED: "EAC_INHIBITED",
  EAC_STATUS_AVAILABLE: "EAC_AVAILABLE",
  EAC_STATUS_ACTIVE: "EAC_ACTIVE",
  3: "EAC_FAULT",
}


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
    # Tesla's exact three-finger center-display gesture is the independent
    # lateral request. Full selfdrive engagement remains a second valid path.
    steering_mode = params.get_int("MadsSteeringMode")
    self.steering_mode = steering_mode if steering_mode in (0, 1, 2) else MadsSteeringMode.DISENGAGE

    self.state = MadsState.disabled
    self.enabled = False
    self.active = False
    self.controls_mismatch = False
    self.lateral_mismatch_counter = 0

    self._requested = False
    self._cp_scoped_request = False
    self._selfdrive_enabled_prev = False
    self._brake_pressed_prev = False
    self._param_refresh_counter = 0
    self._pending_exit_reason = ""
    self._driver_override_latched = False
    self._driver_override_release_counter = 0
    self._eps_temp_fault_latched = False
    self._eps_temp_fault_frames = 0
    self._eps_temp_fault_recovery_counter = 0
    self._eps_fault_consecutive_frames = 0
    self._eac_status = EAC_STATUS_AVAILABLE
    self._eac_error_code = 0
    self.last_transition_reason = ""
    self._radar_temp_degraded = False

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
        self._cp_scoped_request = False
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
        self._cp_scoped_request = False
        self._pending_exit_reason = "manual_disarm"
      elif self._cp_scoped_request:
        # A driver re-arming independent MADS while full CP is active converts
        # the temporary CP request into a persistent independent session.
        self._cp_scoped_request = False
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

  def _update_driver_override(self, CS) -> bool:
    driver_override = bool(getattr(CS, "steeringOverride", False))
    if driver_override:
      if not self._driver_override_latched:
        cloudlog.event("mads.driver_override", active=True, hands_on_level=int(getattr(CS, "handsOnLevel", 0)),
                       steering_torque=float(CS.steeringTorque), steering_rate=float(CS.steeringRateDeg))
      self._driver_override_latched = True
      self._driver_override_release_counter = 0
      return False

    if not self._driver_override_latched:
      return False

    release_ready = (int(getattr(CS, "handsOnLevel", 0)) <= DRIVER_OVERRIDE_RELEASE_HANDS_ON_LEVEL and
                     abs(float(CS.steeringTorque)) <= DRIVER_OVERRIDE_RELEASE_TORQUE and
                     abs(float(CS.steeringRateDeg)) <= DRIVER_OVERRIDE_RELEASE_STEERING_RATE)
    self._driver_override_release_counter = self._driver_override_release_counter + 1 if release_ready else 0
    if self._driver_override_release_counter < DRIVER_OVERRIDE_RELEASE_FRAMES:
      return False

    self._driver_override_latched = False
    self._driver_override_release_counter = 0
    cloudlog.event("mads.driver_override", active=False, hands_on_level=int(getattr(CS, "handsOnLevel", 0)),
                   steering_torque=float(CS.steeringTorque), steering_rate=float(CS.steeringRateDeg),
                   stable_release_ms=round(DRIVER_OVERRIDE_RELEASE_FRAMES * DT_CTRL * 1000))
    return True

  def _update_eps_temporary_fault(self, CS) -> bool:
    self._eac_status = int(getattr(CS, "eacStatus", EAC_STATUS_AVAILABLE))
    self._eac_error_code = int(getattr(CS, "eacErrorCode", 0))
    self._eps_fault_consecutive_frames = (self._eps_fault_consecutive_frames + 1
                                          if CS.steerFaultTemporary or CS.steerFaultPermanent else 0)
    # Match SP's state ownership: any non-disengaging EPS inhibit pauses
    # steering output without destroying the MADS session. Error 9 and strong
    # driver input arrive as steeringDisengage and remain hard exits.
    temporary_fault = (bool(CS.steerFaultTemporary) and
                       self._eac_status == EAC_STATUS_INHIBITED and
                       not bool(getattr(CS, "steeringDisengage", False)))
    eps_available = (not CS.steerFaultTemporary and not CS.steerFaultPermanent and
                     self._eac_status in (EAC_STATUS_AVAILABLE, EAC_STATUS_ACTIVE))

    if temporary_fault:
      if not self._eps_temp_fault_latched:
        cloudlog.event("mads.eps_temporary_fault", active=True,
                       eac_status=EAC_STATUS_NAMES.get(self._eac_status, "EAC_UNKNOWN"),
                       eac_status_raw=self._eac_status, eac_error_code=self._eac_error_code,
                       steering_torque=float(CS.steeringTorque), steering_rate=float(CS.steeringRateDeg))
      self._eps_temp_fault_latched = True
      self._eps_temp_fault_frames += 1
      self._eps_temp_fault_recovery_counter = 0
    elif self._eps_temp_fault_latched:
      self._eps_temp_fault_recovery_counter = self._eps_temp_fault_recovery_counter + 1 if eps_available else 0
      if self._eps_temp_fault_recovery_counter >= EPS_TEMP_FAULT_RECOVERY_FRAMES:
        cloudlog.event("mads.eps_temporary_fault", active=False,
                       eac_status=EAC_STATUS_NAMES.get(self._eac_status, "EAC_UNKNOWN"),
                       eac_status_raw=self._eac_status, eac_error_code=self._eac_error_code,
                       fault_frames=self._eps_temp_fault_frames,
                       stable_recovery_frames=self._eps_temp_fault_recovery_counter,
                       stable_recovery_ms=round(EPS_TEMP_FAULT_RECOVERY_FRAMES * DT_CTRL * 1000))
        self._eps_temp_fault_latched = False
        self._eps_temp_fault_frames = 0
        self._eps_temp_fault_recovery_counter = 0

    return self._eps_temp_fault_latched

  def update(self, CS, selfdrive_enabled: bool, selfdrive_active: bool, events) -> None:
    self._refresh_params()
    screen_toggle = any(be.type == ButtonType.lkas and be.pressed for be in CS.buttonEvents)

    if not self.available:
      self._requested = False
      self._cp_scoped_request = False
      self._driver_override_latched = False
      self._driver_override_release_counter = 0
      self._set_state(MadsState.disabled, self._pending_exit_reason or "not_available")
      self._pending_exit_reason = ""
      self._selfdrive_enabled_prev = selfdrive_enabled
      self._brake_pressed_prev = CS.brakePressed
      return

    selfdrive_rising = selfdrive_enabled and not self._selfdrive_enabled_prev
    selfdrive_falling = not selfdrive_enabled and self._selfdrive_enabled_prev
    brake_rising = CS.brakePressed and not self._brake_pressed_prev
    both_pedals = CS.brakePressed and CS.gasPressed
    driver_override_released = self._update_driver_override(CS)
    eps_temp_fault_paused = self._update_eps_temporary_fault(CS)

    if selfdrive_rising:
      self._requested = True
      self._cp_scoped_request = not self.user_enabled
      cloudlog.event("mads.full_cp_request", independent_mads_armed=self.user_enabled,
                     cp_scoped=self._cp_scoped_request)
    elif selfdrive_falling and self._cp_scoped_request:
      self._requested = False
      self._cp_scoped_request = False
      self._pending_exit_reason = "full_cp_disengaged"

    steering_disengage = bool(getattr(CS, "steeringDisengage", False))
    wrong_gear = CS.gearShifter in (GearShifter.park, GearShifter.reverse, GearShifter.neutral, GearShifter.unknown)
    # Match SP: keep the MADS session armed, but pause active lateral output in
    # reverse at any speed and in other wrong gears below 2.5 m/s.
    gear_pause = CS.gearShifter == GearShifter.reverse or (wrong_gear and CS.vEgo < 2.5)
    pause_for_brake = self.steering_mode == MadsSteeringMode.PAUSE and CS.brakePressed
    immediate_steering_fault = CS.steerFaultPermanent
    soft_disable_events = [event for event in events.names if ET.SOFT_DISABLE in EVENTS.get(event, {})]
    radar_only_soft_disable = (bool(soft_disable_events) and
                               all(event in RADAR_SOFT_DISABLE_EVENTS for event in soft_disable_events))

    if radar_only_soft_disable != self._radar_temp_degraded:
      self._radar_temp_degraded = radar_only_soft_disable
      cloudlog.event("mads.radar_degraded", active=radar_only_soft_disable,
                     action="keep_lateral_active", error=radar_only_soft_disable)

    exit_reasons = []
    if steering_disengage:
      exit_reasons.append("steering_disengage")
    if both_pedals:
      exit_reasons.append("both_pedals")
    if self.controls_mismatch:
      exit_reasons.append("panda_lateral_mismatch")
    if CS.invalidLkasSetting:
      exit_reasons.append("invalid_lkas_setting")
    if immediate_steering_fault:
      exit_reasons.append("steering_fault")
    if events.contains(ET.IMMEDIATE_DISABLE):
      exit_reasons.append("immediate_disable_event")
    if events.contains(ET.SOFT_DISABLE) and not radar_only_soft_disable:
      exit_reasons.append("soft_disable_event")

    safety_exit = bool(exit_reasons)
    if safety_exit or (brake_rising and self.steering_mode == MadsSteeringMode.DISENGAGE):
      self._requested = False
      self._cp_scoped_request = False
      self._driver_override_latched = False
      self._driver_override_release_counter = 0
      if not safety_exit:
        exit_reasons.append("brake_disengage")

    screen_enabled = False
    if screen_toggle:
      if self._requested:
        self._requested = False
        self._cp_scoped_request = False
        self.user_enabled = False
        self.params.put_bool("MadsUserEnabled", False)
        self._pending_exit_reason = "screen_toggle_off"
        cloudlog.event("mads.screen_toggle", enabled=False, active=self.active)
      elif not exit_reasons and not CS.brakePressed:
        self._requested = True
        self._cp_scoped_request = False
        self.user_enabled = True
        self.params.put_bool("MadsUserEnabled", True)
        screen_enabled = True
        cloudlog.event("mads.screen_toggle", enabled=True, active=self.active)
      else:
        reasons = [*exit_reasons, *(["brake_pressed"] if CS.brakePressed else [])]
        cloudlog.event("mads.screen_toggle_blocked", reasons=",".join(reasons))

    if not self._requested:
      reason = ",".join(exit_reasons) if exit_reasons else self._pending_exit_reason or "not_requested"
      self._set_state(MadsState.disabled, reason)
    elif eps_temp_fault_paused:
      self._set_state(MadsState.paused, "eps_temporary_fault")
    elif self._driver_override_latched:
      self._set_state(MadsState.paused, "driver_override")
    elif gear_pause:
      self._set_state(MadsState.paused, "gear_pause")
    elif pause_for_brake:
      self._set_state(MadsState.paused, "brake_pause")
    elif events.contains(ET.OVERRIDE_LATERAL):
      self._set_state(MadsState.overriding, "driver_override")
    else:
      reason = ("selfdrive_engaged" if selfdrive_rising else
                "screen_toggle" if screen_enabled else
                "driver_override_released" if driver_override_released else
                "gear_resumed" if self.state == MadsState.paused and self.last_transition_reason == "gear_pause" else
                "brake_released" if self.state == MadsState.paused else "requested")
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
      self.last_transition_reason = reason
      cloudlog.event("mads.transition", previous_state=str(previous_state), state=str(state), reason=reason,
                     enabled=self.enabled, active=self.active, steering_mode=self.steering_mode,
                     eac_status=EAC_STATUS_NAMES.get(self._eac_status, "EAC_UNKNOWN"),
                     eac_status_raw=self._eac_status, eac_error_code=self._eac_error_code,
                     eps_fault_frames=self._eps_fault_consecutive_frames,
                     eps_temp_fault_frames=self._eps_temp_fault_frames,
                     error=state == MadsState.disabled and reason not in ("", "not_requested"))
