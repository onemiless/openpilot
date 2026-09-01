from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class LaneIntentDirection(IntEnum):
  none = 0
  left = 1
  right = 2


class ObservedLaneChangeState(IntEnum):
  off = 0
  pre = 1
  starting = 2
  finishing = 3


@dataclass(frozen=True)
class NavLanePlan:
  valid: bool
  session_id: str
  route_revision: int
  maneuver_event_id: int
  lane_count: int
  recommended_indices: tuple[int, ...]


@dataclass(frozen=True)
class LaneTopologyInput:
  valid_for_control: bool
  visible_lane_count: int
  ego_lane_index: int
  left_neighbor_exists: bool
  right_neighbor_exists: bool
  left_crossing_allowed: bool
  right_crossing_allowed: bool


@dataclass(frozen=True)
class LaneVehicleInput:
  lateral_active: bool
  speed_mps: float
  left_blindspot: bool = False
  right_blindspot: bool = False
  left_blinker: bool = False
  right_blinker: bool = False
  brake_pressed: bool = False
  gas_pressed: bool = False
  lane_change_state: ObservedLaneChangeState = ObservedLaneChangeState.off
  lane_change_direction: LaneIntentDirection = LaneIntentDirection.none


@dataclass(frozen=True)
class NavTurnPlan:
  valid: bool
  session_id: str
  route_revision: int
  maneuver_event_id: int
  maneuver: str
  distance_m: float


@dataclass(frozen=True)
class NavLaneIntent:
  signal_requested: bool = False
  lane_change_authorized: bool = False
  direction: LaneIntentDirection = LaneIntentDirection.none
  request_id: int = 0
  target_lane_index: int = -1
  reason: str = "idle"


class NavTurnSignalCoordinator:
  """Requests a physical lamp for a route turn without authorizing a lane change."""

  SIGNAL_TIMEOUT_NS = 30_000_000_000
  LOOKAHEAD_TIME_S = 8.0
  MIN_LOOKAHEAD_M = 40.0
  MAX_LOOKAHEAD_M = 250.0
  LOOKAHEAD_MARGIN_M = 20.0
  MANEUVER_DIRECTIONS = {
    "slightLeft": LaneIntentDirection.left,
    "turnLeft": LaneIntentDirection.left,
    "sharpLeft": LaneIntentDirection.left,
    "uTurnLeft": LaneIntentDirection.left,
    "exitLeft": LaneIntentDirection.left,
    "rampLeft": LaneIntentDirection.left,
    "mergeLeft": LaneIntentDirection.left,
    "slightRight": LaneIntentDirection.right,
    "turnRight": LaneIntentDirection.right,
    "sharpRight": LaneIntentDirection.right,
    "uTurnRight": LaneIntentDirection.right,
    "exitRight": LaneIntentDirection.right,
    "rampRight": LaneIntentDirection.right,
    "mergeRight": LaneIntentDirection.right,
  }

  def __init__(self) -> None:
    self._active_key: tuple[str, int, int] | None = None
    self._active_direction = LaneIntentDirection.none
    self._active_since_ns = 0

  def _reset(self, reason: str = "idle") -> NavLaneIntent:
    self._active_key = None
    self._active_direction = LaneIntentDirection.none
    self._active_since_ns = 0
    return NavLaneIntent(reason=reason)

  def update(self, plan: NavTurnPlan, *, speed_mps: float, now_ns: int) -> NavLaneIntent:
    direction = self.MANEUVER_DIRECTIONS.get(plan.maneuver, LaneIntentDirection.none)
    event_key = (plan.session_id, plan.route_revision, plan.maneuver_event_id)
    if not plan.valid or direction == LaneIntentDirection.none or plan.maneuver_event_id == 0:
      return self._reset("turnUnavailable")

    if self._active_key is not None:
      if event_key != self._active_key or direction != self._active_direction:
        self._reset("turnChanged")
      elif now_ns - self._active_since_ns > self.SIGNAL_TIMEOUT_NS:
        return self._reset("turnSignalTimeout")
      else:
        return NavLaneIntent(
          signal_requested=True,
          direction=self._active_direction,
          request_id=plan.maneuver_event_id,
          target_lane_index=-1,
          reason="turnApproach",
        )

    lookahead_m = max(self.MIN_LOOKAHEAD_M, min(
      self.MAX_LOOKAHEAD_M, max(0.0, speed_mps) * self.LOOKAHEAD_TIME_S + self.LOOKAHEAD_MARGIN_M,
    ))
    if not 0.0 < plan.distance_m <= lookahead_m:
      return self._reset("turnOutsideWindow")

    self._active_key = event_key
    self._active_direction = direction
    self._active_since_ns = now_ns
    return NavLaneIntent(
      signal_requested=True,
      direction=direction,
      request_id=plan.maneuver_event_id,
      target_lane_index=-1,
      reason="turnApproach",
    )


class NavLaneIntentCoordinator:
  MISMATCH_STABLE_NS = 500_000_000
  CROSSING_STABLE_NS = 300_000_000
  LANE_INDEX_STABLE_NS = 500_000_000
  TOPOLOGY_TRANSITION_GRACE_NS = 1_000_000_000
  SIGNAL_WAIT_TIMEOUT_NS = 60_000_000_000
  LANE_CHANGE_TIMEOUT_NS = 10_000_000_000
  COOLDOWN_NS = 750_000_000
  MIN_SPEED_MPS = 20 * 0.44704
  MAX_SPEED_MPS = 33.33

  def __init__(self) -> None:
    self._phase = "idle"
    self._candidate = None
    self._candidate_since_ns = 0
    self._crossing_since_ns = 0
    self._phase_since_ns = 0
    self._signal_since_ns = 0
    self._blocked_key = None
    self._request_id = 0
    self._expected_lane_index = -1
    self._completion_since_ns = 0
    self._topology_invalid_since_ns = 0

  def _idle(self, reason: str = "idle") -> NavLaneIntent:
    return NavLaneIntent(reason=reason)

  @staticmethod
  def _target(plan: NavLanePlan, ego_index: int) -> int | None:
    valid = tuple(index for index in plan.recommended_indices if 0 <= index < plan.lane_count)
    return min(valid, key=lambda index: (abs(index - ego_index), index)) if valid else None

  @staticmethod
  def _direction(ego_index: int, target_index: int) -> LaneIntentDirection:
    if target_index < ego_index:
      return LaneIntentDirection.left
    if target_index > ego_index:
      return LaneIntentDirection.right
    return LaneIntentDirection.none

  @staticmethod
  def _event_key(plan: NavLanePlan, target_index: int) -> tuple[str, int, int, tuple[int, ...], int]:
    return plan.session_id, plan.route_revision, plan.maneuver_event_id, plan.recommended_indices, target_index

  def _reset(self) -> None:
    self._phase = "idle"
    self._candidate = None
    self._candidate_since_ns = 0
    self._crossing_since_ns = 0
    self._phase_since_ns = 0
    self._signal_since_ns = 0
    self._expected_lane_index = -1
    self._completion_since_ns = 0
    self._topology_invalid_since_ns = 0

  def _abort(self, event_key, reason: str) -> NavLaneIntent:
    self._blocked_key = event_key
    self._reset()
    return self._idle(reason)

  def update(self, plan: NavLanePlan, topology: LaneTopologyInput, vehicle: LaneVehicleInput,
             *, now_ns: int) -> NavLaneIntent:
    base_healthy = bool(
      plan.valid and vehicle.lateral_active and not vehicle.brake_pressed and not vehicle.gas_pressed
      and self.MIN_SPEED_MPS <= vehicle.speed_mps <= self.MAX_SPEED_MPS
    )
    topology_healthy = bool(
      topology.valid_for_control and plan.lane_count == topology.visible_lane_count
      and 0 <= topology.ego_lane_index < topology.visible_lane_count
    )
    if not base_healthy:
      if self._phase not in ("idle", "cooldown") and self._candidate is not None:
        return self._abort(self._candidate[0], "health")
      self._reset()
      return self._idle("health")

    if not topology_healthy:
      if self._phase == "changing" and self._candidate is not None:
        event_key, _start_ego, direction, target_index = self._candidate
        if self._event_key(plan, target_index) != event_key:
          return self._abort(event_key, "routeChanged")
        physical_signal_on = ((vehicle.left_blinker and not vehicle.right_blinker)
                              if direction == LaneIntentDirection.left else
                              (vehicle.right_blinker and not vehicle.left_blinker))
        if not physical_signal_on:
          return self._abort(event_key, "physicalSignalLost")
        if self._topology_invalid_since_ns == 0:
          self._topology_invalid_since_ns = now_ns
        elif now_ns - self._topology_invalid_since_ns > self.TOPOLOGY_TRANSITION_GRACE_NS:
          return self._abort(event_key, "topologyTransitionTimeout")
        return NavLaneIntent(True, True, direction, self._request_id, self._expected_lane_index, "topologyTransition")
      self._reset()
      return self._idle("health")
    self._topology_invalid_since_ns = 0

    if self._phase == "cooldown":
      if now_ns - self._phase_since_ns < self.COOLDOWN_NS:
        return self._idle("cooldown")
      if topology.ego_lane_index != self._expected_lane_index:
        return self._abort(self._candidate[0] if self._candidate is not None else None, "laneChangeNotObserved")
      self._reset()
      return self._idle("laneChangeComplete")

    if self._phase == "changing" and self._candidate is not None:
      event_key, _start_ego, direction, target_index = self._candidate
      if self._event_key(plan, target_index) != event_key:
        return self._abort(event_key, "routeChanged")
      if (vehicle.lane_change_state in (ObservedLaneChangeState.pre, ObservedLaneChangeState.starting,
                                        ObservedLaneChangeState.finishing) and
          vehicle.lane_change_direction != direction):
        return self._abort(event_key, "directionMismatch")
      if now_ns - self._phase_since_ns > self.LANE_CHANGE_TIMEOUT_NS:
        return self._abort(event_key, "laneChangeTimeout")
      physical_signal_on = ((vehicle.left_blinker and not vehicle.right_blinker)
                            if direction == LaneIntentDirection.left else
                            (vehicle.right_blinker and not vehicle.left_blinker))
      if not physical_signal_on:
        return self._abort(event_key, "physicalSignalLost")
      model_cycle_complete = vehicle.lane_change_state in (
        ObservedLaneChangeState.off, ObservedLaneChangeState.pre, ObservedLaneChangeState.finishing,
      )
      if topology.ego_lane_index == self._expected_lane_index and model_cycle_complete:
        if self._completion_since_ns == 0:
          self._completion_since_ns = now_ns
        elif now_ns - self._completion_since_ns >= self.LANE_INDEX_STABLE_NS:
          self._phase = "cooldown"
          self._phase_since_ns = now_ns
          return self._idle("laneChangeObserved")
      else:
        self._completion_since_ns = 0
      return NavLaneIntent(
        signal_requested=True,
        lane_change_authorized=True,
        direction=direction,
        request_id=self._request_id,
        target_lane_index=self._expected_lane_index,
        reason=self._phase,
      )

    target_index = self._target(plan, topology.ego_lane_index)
    if target_index is None:
      self._reset()
      return self._idle("noRecommendedLane")
    direction = self._direction(topology.ego_lane_index, target_index)
    if direction == LaneIntentDirection.none:
      self._blocked_key = None
      self._reset()
      return self._idle("alreadyInRecommendedLane")

    event_key = self._event_key(plan, target_index)
    if self._blocked_key == event_key:
      return self._idle("blockedEvent")

    neighbor_exists = topology.left_neighbor_exists if direction == LaneIntentDirection.left else topology.right_neighbor_exists
    if not neighbor_exists:
      return self._abort(event_key, "noNeighbor")

    candidate = (event_key, topology.ego_lane_index, direction, target_index)
    if self._phase == "idle":
      if candidate != self._candidate:
        self._candidate = candidate
        self._candidate_since_ns = now_ns
        self._signal_since_ns = now_ns
        self._request_id += 1
        return NavLaneIntent(
          signal_requested=True,
          direction=direction,
          request_id=self._request_id,
          target_lane_index=(topology.ego_lane_index - 1 if direction == LaneIntentDirection.left
                             else topology.ego_lane_index + 1),
          reason="stabilizingLaneAlignment",
        )
      if now_ns - self._candidate_since_ns < self.MISMATCH_STABLE_NS:
        return NavLaneIntent(
          signal_requested=True,
          direction=direction,
          request_id=self._request_id,
          target_lane_index=(topology.ego_lane_index - 1 if direction == LaneIntentDirection.left
                             else topology.ego_lane_index + 1),
          reason="stabilizingLaneAlignment",
        )
      self._phase = "signaling"
      self._phase_since_ns = now_ns
      self._crossing_since_ns = 0

    if self._candidate != candidate and self._phase != "cooldown":
      self._reset()
      self._candidate = candidate
      self._candidate_since_ns = now_ns
      return self._idle("routeChanged")

    if self._phase in ("authorized", "changing") and now_ns - self._phase_since_ns > self.LANE_CHANGE_TIMEOUT_NS:
      return self._abort(event_key, "laneChangeTimeout")

    if vehicle.lane_change_state in (ObservedLaneChangeState.starting, ObservedLaneChangeState.finishing):
      if vehicle.lane_change_direction != direction:
        return self._abort(event_key, "directionMismatch")
      if vehicle.lane_change_state == ObservedLaneChangeState.starting:
        self._phase = "changing"
        self._phase_since_ns = now_ns
        self._expected_lane_index = topology.ego_lane_index - 1 if direction == LaneIntentDirection.left else topology.ego_lane_index + 1
        self._completion_since_ns = 0
      else:
        # DesireHelper implementations differ on whether finishing is emitted.
        # Completion is confirmed only by a stable one-lane ego-index change.
        self._phase = "changing"

    crossing_allowed = topology.left_crossing_allowed if direction == LaneIntentDirection.left else topology.right_crossing_allowed
    blindspot = vehicle.left_blindspot if direction == LaneIntentDirection.left else vehicle.right_blindspot
    physical_signal_on = ((vehicle.left_blinker and not vehicle.right_blinker)
                          if direction == LaneIntentDirection.left else
                          (vehicle.right_blinker and not vehicle.left_blinker))
    if self._phase == "signaling":
      if now_ns - self._signal_since_ns > self.SIGNAL_WAIT_TIMEOUT_NS:
        return self._abort(event_key, "crossingWaitTimeout")
      if crossing_allowed and not blindspot and physical_signal_on:
        if self._crossing_since_ns == 0:
          self._crossing_since_ns = now_ns
        if now_ns - self._crossing_since_ns >= self.CROSSING_STABLE_NS:
          self._phase = "authorized"
          self._phase_since_ns = now_ns
      else:
        self._crossing_since_ns = 0
    elif self._phase == "authorized" and (not crossing_allowed or blindspot or not physical_signal_on):
      self._phase = "signaling"
      self._crossing_since_ns = 0

    authorized = self._phase in ("authorized", "changing")
    return NavLaneIntent(
      signal_requested=True,
      lane_change_authorized=authorized,
      direction=direction,
      request_id=self._request_id,
      target_lane_index=topology.ego_lane_index - 1 if direction == LaneIntentDirection.left else topology.ego_lane_index + 1,
      reason=self._phase,
    )
