from __future__ import annotations

import math

from openpilot.cereal import custom
from opendbc.sunnypilot.car.tesla.values import TeslaFlagsSP
from openpilot.common.realtime import DT_MDL
from openpilot.selfdrive.car.cruise import V_CRUISE_UNSET
from openpilot.sunnypilot.selfdrive.car.tesla.control_runtime import TeslaControlState, TeslaLongitudinalOwner


NavManeuver = custom.NavAssistStateSP.Maneuver

COMFORT_BRAKE = 1.2
ACTUATION_DELAY_S = 1.0
ADMISSION_MARGIN_M = 5.0
ACTIVATION_MARGIN_M = 25.0
MAX_MANEUVER_DISTANCE_M = 2_000.0
MAX_TRACK_SPEED_MPS = 60.0 / 3.6
MIN_TARGET_SPEED_MPS = 2.0
RELEASE_ACCEL_MPS2 = 1.0

TARGET_SPEEDS = {
  NavManeuver.slightLeft: 8.0,
  NavManeuver.slightRight: 8.0,
  NavManeuver.turnLeft: 5.0,
  NavManeuver.turnRight: 5.0,
  NavManeuver.sharpLeft: 3.5,
  NavManeuver.sharpRight: 3.5,
  NavManeuver.uTurnLeft: 2.5,
  NavManeuver.uTurnRight: 2.5,
  NavManeuver.exitLeft: 10.0,
  NavManeuver.exitRight: 10.0,
  NavManeuver.rampLeft: 10.0,
  NavManeuver.rampRight: 10.0,
  NavManeuver.roundabout: 6.0,
}


class NavigationSpeedController:
  """Closed-course navigation speed ceiling; never requests acceleration or a stop."""

  def __init__(self, *, enabled: bool | None = None, require_sp_longitudinal_owner: bool = False):
    self.enabled = True if enabled is None else enabled
    self.require_sp_longitudinal_owner = require_sp_longitudinal_owner
    self.output_v_target = V_CRUISE_UNSET
    self.output_a_target = 0.0
    self.is_active = False
    self.is_releasing = False
    self.event_admitted = False
    self.event_rejected = False
    self.event_key: tuple[str, int, int] | None = None
    self.target_speed = 0.0
    self.required_distance = 0.0

  @staticmethod
  def _healthy(sm) -> bool:
    service = "navAssistStateSP"
    return bool(sm.seen[service] and sm.alive[service] and sm.valid[service] and sm[service].valid and not sm[service].stale)

  def _sp_owns_longitudinal(self, sm) -> bool:
    if not self.require_sp_longitudinal_owner:
      return True
    service = "carStateSP"
    if not (sm.seen[service] and sm.alive[service] and sm.valid[service]):
      return False
    owner = TeslaControlState(TeslaFlagsSP(int(sm[service].flags))).longitudinal_owner
    return owner in (TeslaLongitudinalOwner.sp, TeslaLongitudinalOwner.ap_hybrid_sp)

  def _reject_visible_event(self, sm) -> None:
    if not self._healthy(sm):
      if self.event_key is not None:
        self.event_rejected = True
      return
    nav = sm["navAssistStateSP"]
    event_key = (str(nav.sessionId), int(nav.routeRevision), int(nav.maneuverEventId))
    if event_key[2] != 0:
      self.event_key = event_key
      self.event_admitted = False
      self.event_rejected = True

  @staticmethod
  def _required_distance(v_ego: float, target_speed: float) -> float:
    braking = max(0.0, v_ego ** 2 - target_speed ** 2) / (2.0 * COMFORT_BRAKE)
    return braking + v_ego * ACTUATION_DELAY_S

  @staticmethod
  def _target_for(nav) -> float | None:
    default = TARGET_SPEEDS.get(nav.maneuver)
    if default is None:
      return None
    if nav.advisorySpeedValid:
      return max(MIN_TARGET_SPEED_MPS, min(default, float(nav.advisorySpeedMps)))
    return default

  def _release(self, v_cruise: float, a_ego: float) -> None:
    self.is_active = False
    self.output_a_target = a_ego
    if self.output_v_target == V_CRUISE_UNSET:
      self.is_releasing = False
      return
    self.output_v_target = min(v_cruise, self.output_v_target + RELEASE_ACCEL_MPS2 * DT_MDL)
    self.is_releasing = self.output_v_target < v_cruise - 1e-3
    if not self.is_releasing:
      self.output_v_target = V_CRUISE_UNSET

  def update(self, sm, *, long_enabled: bool, long_override: bool, v_ego: float, a_ego: float, v_cruise: float,
             planner_verified: bool = True, lane_change_active: bool = False) -> None:
    if not self.enabled:
      self.output_v_target = V_CRUISE_UNSET
      self.output_a_target = a_ego
      self.is_active = self.is_releasing = False
      return

    driver_override = bool(long_override or sm["carState"].gasPressed or sm["carState"].brakePressed)
    if driver_override:
      self._reject_visible_event(sm)
      self._release(v_cruise, a_ego)
      return

    temporarily_unavailable = (not long_enabled or not planner_verified or v_ego > MAX_TRACK_SPEED_MPS
                               or not self._sp_owns_longitudinal(sm))
    if temporarily_unavailable:
      # Allow the documented workflow: plan the phone route first, then engage
      # SP/select the official backend. Once an event was admitted, however,
      # losing authority latches it out so it cannot resume mid-maneuver.
      if self.event_key is not None:
        self.event_rejected = True
      self._release(v_cruise, a_ego)
      return

    if not self._healthy(sm):
      self._reject_visible_event(sm)
      self._release(v_cruise, a_ego)
      return

    nav = sm["navAssistStateSP"]
    target_speed = self._target_for(nav)
    distance = float(nav.maneuverDistanceM)
    event_key = (str(nav.sessionId), int(nav.routeRevision), int(nav.maneuverEventId))
    if target_speed is None or event_key[2] == 0 or not math.isfinite(distance) or not 0.0 < distance <= MAX_MANEUVER_DISTANCE_M:
      if self.event_key is not None:
        self.event_rejected = True
      self._release(v_cruise, a_ego)
      return

    required_distance = self._required_distance(v_ego, target_speed)
    if event_key != self.event_key:
      self.event_key = event_key
      self.target_speed = target_speed
      self.required_distance = required_distance
      self.event_admitted = distance >= required_distance + ADMISSION_MARGIN_M
      self.event_rejected = not self.event_admitted

    if self.event_rejected or not self.event_admitted:
      self._release(v_cruise, a_ego)
      return

    self.required_distance = max(self.required_distance, required_distance)
    if distance < required_distance:
      # Do not turn a late/accelerated approach into progressively harsher
      # braking. Miss the maneuver and let the driver or route replan handle it.
      self.event_rejected = True
      self._release(v_cruise, a_ego)
      return
    if distance > self.required_distance + ACTIVATION_MARGIN_M:
      self._release(v_cruise, a_ego)
      return

    self.is_active = True
    self.is_releasing = False
    self.output_v_target = min(v_cruise, self.target_speed)
    # The selected planner/MPC produces the deceleration trajectory. Preserve
    # its current acceleration seed instead of injecting an actuator command.
    self.output_a_target = a_ego
