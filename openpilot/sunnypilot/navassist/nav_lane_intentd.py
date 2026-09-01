#!/usr/bin/env python3
from __future__ import annotations

import math
import time

from openpilot.cereal import messaging
from openpilot.common.realtime import Ratekeeper
from openpilot.sunnypilot.navassist.lane_intent import (
  LaneIntentDirection,
  LaneTopologyInput,
  LaneVehicleInput,
  NavLaneIntentCoordinator,
  NavLanePlan,
  NavTurnPlan,
  NavTurnSignalCoordinator,
  ObservedLaneChangeState,
)


PUBLISH_HZ = 20
BASE_SERVICES = ("navAssistStateSP", "carState", "carControl")
LANE_SERVICES = ("laneTopologyStateSP", "modelV2")
SERVICES = BASE_SERVICES + LANE_SERVICES
TURN_LANE_LOOKAHEAD_M = 1_000.0
EXIT_LANE_LOOKAHEAD_M = 2_000.0
LEFT_TURN_LANE_MANEUVERS = frozenset(("turnLeft", "sharpLeft", "uTurnLeft"))
RIGHT_TURN_LANE_MANEUVERS = frozenset(("turnRight", "sharpRight", "uTurnRight"))
LEFT_EXIT_LANE_MANEUVERS = frozenset(("exitLeft", "rampLeft", "mergeLeft"))
RIGHT_EXIT_LANE_MANEUVERS = frozenset(("exitRight", "rampRight", "mergeRight"))


def selected_services_healthy(sm, services: tuple[str, ...]) -> bool:
  return all(sm.seen[service] and sm.alive[service] and sm.valid[service] for service in services)


def navigation_linked(nav, *, base_healthy: bool) -> bool:
  return bool(
    base_healthy and not nav.stale and nav.routeActive and nav.routeMatched
    and str(nav.mode) == "realtime" and int(nav.maneuverEventId) != 0
  )


def build_lane_plan(nav, topology, *, healthy: bool) -> NavLanePlan:
  nav_valid = bool(healthy and nav.valid and not nav.stale)
  lanes = tuple(nav.lanes)
  recommended = tuple(int(lane.index) for lane in lanes if lane.recommended)
  if lanes:
    return NavLanePlan(
      nav_valid, str(nav.sessionId), int(nav.routeRevision), int(nav.maneuverEventId), len(lanes), recommended,
    )

  maneuver = str(nav.maneuver)
  distance_m = float(nav.maneuverDistanceM)
  lane_count = int(topology.visibleLaneCount)
  fallback_side = None
  lookahead_m = 0.0
  if maneuver in LEFT_TURN_LANE_MANEUVERS:
    fallback_side, lookahead_m = "left", TURN_LANE_LOOKAHEAD_M
  elif maneuver in RIGHT_TURN_LANE_MANEUVERS:
    fallback_side, lookahead_m = "right", TURN_LANE_LOOKAHEAD_M
  elif maneuver in LEFT_EXIT_LANE_MANEUVERS:
    fallback_side, lookahead_m = "left", EXIT_LANE_LOOKAHEAD_M
  elif maneuver in RIGHT_EXIT_LANE_MANEUVERS:
    fallback_side, lookahead_m = "right", EXIT_LANE_LOOKAHEAD_M

  heuristic_valid = bool(
    nav_valid and int(nav.maneuverEventId) != 0 and lane_count > 0 and fallback_side is not None
    and math.isfinite(distance_m) and 0.0 < distance_m <= lookahead_m
  )
  if heuristic_valid:
    target = 0 if fallback_side == "left" else lane_count - 1
    return NavLanePlan(
      True, str(nav.sessionId), int(nav.routeRevision), int(nav.maneuverEventId), lane_count, (target,), heuristic=True,
    )

  return NavLanePlan(
    nav_valid, str(nav.sessionId), int(nav.routeRevision), int(nav.maneuverEventId), len(lanes), recommended,
  )


def main() -> None:
  coordinator = NavLaneIntentCoordinator()
  turn_signal_coordinator = NavTurnSignalCoordinator()
  sm = messaging.SubMaster(list(SERVICES), poll="navAssistStateSP")
  pm = messaging.PubMaster(["navLaneIntentSP"])
  ratekeeper = Ratekeeper(PUBLISH_HZ)
  while True:
    sm.update(50)
    base_healthy = selected_services_healthy(sm, BASE_SERVICES)
    lane_services_healthy = selected_services_healthy(sm, LANE_SERVICES)
    healthy = base_healthy and lane_services_healthy
    nav = sm["navAssistStateSP"]
    topology = sm["laneTopologyStateSP"]
    car_state = sm["carState"]
    car_control = sm["carControl"]
    model_meta = sm["modelV2"].meta
    plan = build_lane_plan(nav, topology, healthy=healthy)
    topology_input = LaneTopologyInput(
      valid_for_control=bool(healthy and topology.validForControl),
      visible_lane_count=int(topology.visibleLaneCount),
      ego_lane_index=int(topology.egoLaneIndexFromLeft),
      left_neighbor_exists=bool(topology.leftNeighborExists),
      right_neighbor_exists=bool(topology.rightNeighborExists),
      left_crossing_allowed=bool(topology.leftCrossingAllowed),
      right_crossing_allowed=bool(topology.rightCrossingAllowed),
    )
    vehicle = LaneVehicleInput(
      lateral_active=bool(healthy and car_control.latActive),
      speed_mps=float(car_state.vEgo),
      left_blindspot=bool(car_state.leftBlindspot),
      right_blindspot=bool(car_state.rightBlindspot),
      left_blinker=bool(car_state.leftBlinker),
      right_blinker=bool(car_state.rightBlinker),
      brake_pressed=bool(car_state.brakePressed),
      gas_pressed=bool(car_state.gasPressed),
      lane_change_state=ObservedLaneChangeState(int(model_meta.laneChangeState.raw)),
      lane_change_direction=LaneIntentDirection(int(model_meta.laneChangeDirection.raw)),
    )
    now_ns = time.monotonic_ns()
    lane_intent = coordinator.update(plan, topology_input, vehicle, now_ns=now_ns)
    turn_plan = NavTurnPlan(
      valid=navigation_linked(nav, base_healthy=base_healthy),
      session_id=str(nav.sessionId),
      route_revision=int(nav.routeRevision),
      maneuver_event_id=int(nav.maneuverEventId),
      maneuver=str(nav.maneuver),
      distance_m=float(nav.maneuverDistanceM),
    )
    turn_intent = turn_signal_coordinator.update(turn_plan, speed_mps=float(car_state.vEgo), now_ns=now_ns)
    intent = lane_intent if lane_intent.signal_requested else turn_intent

    message = messaging.new_message("navLaneIntentSP")
    message.valid = base_healthy
    state = message.navLaneIntentSP
    state.publishMonoTime = now_ns
    state.valid = base_healthy
    state.signalRequested = intent.signal_requested
    state.laneChangeAuthorized = intent.lane_change_authorized
    state.direction = {LaneIntentDirection.none: "none", LaneIntentDirection.left: "left",
                       LaneIntentDirection.right: "right"}[intent.direction]
    state.requestId = intent.request_id
    state.targetLaneIndex = intent.target_lane_index
    state.routeRevision = plan.route_revision
    state.maneuverEventId = plan.maneuver_event_id
    state.reason = intent.reason
    state.sessionId = plan.session_id
    pm.send("navLaneIntentSP", message)
    ratekeeper.keep_time()


if __name__ == "__main__":
  main()
