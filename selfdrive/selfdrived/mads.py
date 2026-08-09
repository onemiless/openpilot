from cereal import custom
from opendbc.car import structs

from openpilot.common.swaglog import cloudlog
from openpilot.selfdrive.selfdrived.events import ET


MadsState = custom.MadsState.State
GearShifter = structs.CarState.GearShifter


class MadsSteeringMode:
  REMAIN_ACTIVE = 0
  PAUSE = 1
  DISENGAGE = 2


class ModularAssistiveDrivingSystem:
  """Target-native owner for an independent lateral-control session."""

  def __init__(self, CP, params):
    self.CP = CP
    self.available = CP.brand == "tesla" and params.get_bool("Mads") and not CP.passive
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

    cloudlog.event("mads.config", available=self.available, steering_mode=self.steering_mode,
                   car_brand=CP.brand, passive=CP.passive)

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
    if not self.available:
      self._set_state(MadsState.disabled)
      return

    selfdrive_rising = selfdrive_enabled and not self._selfdrive_enabled_prev
    brake_rising = CS.brakePressed and not self._brake_pressed_prev
    both_pedals = CS.brakePressed and CS.gasPressed

    if selfdrive_rising:
      self._requested = True

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
      reason = ",".join(exit_reasons) if exit_reasons else "not_requested"
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

  def _set_state(self, state, reason: str = "") -> None:
    previous_state = self.state
    self.state = state
    self.enabled = state != MadsState.disabled
    self.active = state in (MadsState.enabled, MadsState.softDisabling, MadsState.overriding)
    if state != previous_state:
      cloudlog.event("mads.transition", previous_state=str(previous_state), state=str(state), reason=reason,
                     enabled=self.enabled, active=self.active, steering_mode=self.steering_mode,
                     error=state == MadsState.disabled and reason not in ("", "not_requested"))
