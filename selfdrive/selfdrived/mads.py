from cereal import custom
from opendbc.car import structs

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

  def data_sample(self, panda_states, selfdrive_enabled: bool) -> None:
    if not self.available or not self.active or selfdrive_enabled:
      self.lateral_mismatch_counter = 0
      self.controls_mismatch = False
      return

    mismatch = any(not ps.controlsAllowedLateral for ps in panda_states
                   if ps.safetyModel not in (structs.CarParams.SafetyModel.silent,
                                             structs.CarParams.SafetyModel.noOutput))
    self.lateral_mismatch_counter = self.lateral_mismatch_counter + 1 if mismatch else 0
    self.controls_mismatch = self.lateral_mismatch_counter >= 200

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

    safety_exit = (steering_disengage or both_pedals or self.controls_mismatch or CS.invalidLkasSetting or
                   not CS.cruiseState.available or unsafe_gear or steering_fault or
                   events.contains(ET.IMMEDIATE_DISABLE) or events.contains(ET.SOFT_DISABLE))
    if safety_exit or (brake_rising and self.steering_mode == MadsSteeringMode.DISENGAGE):
      self._requested = False

    if not self._requested:
      self._set_state(MadsState.disabled)
    elif pause_for_brake:
      self._set_state(MadsState.paused)
    elif events.contains(ET.OVERRIDE_LATERAL):
      self._set_state(MadsState.overriding)
    else:
      self._set_state(MadsState.enabled)

    self._selfdrive_enabled_prev = selfdrive_enabled
    self._brake_pressed_prev = CS.brakePressed

  def _set_state(self, state) -> None:
    self.state = state
    self.enabled = state != MadsState.disabled
    self.active = state in (MadsState.enabled, MadsState.softDisabling, MadsState.overriding)
