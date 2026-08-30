#!/usr/bin/env python3
from __future__ import annotations

import time

from openpilot.cereal import messaging
from openpilot.common.realtime import Ratekeeper
from openpilot.sunnypilot.navassist.lane_intent import (
  LaneIntentDirection,
  LaneTopologyInput,
  LaneVehicleInput,
  NavLaneIntentCoordinator,
  NavLanePlan,
  ObservedLaneChangeState,
)


PUBLISH_HZ = 20
SERVICES = ("navAssistStateSP", "laneTopologyStateSP", "carState", "carControl", "modelV2")


def services_healthy(sm) -> bool:
  return all(sm.seen[service] and sm.alive[service] and sm.valid[service] for service in SERVICES)


def main() -> None:
  coordinator = NavLaneIntentCoordinator()
  sm = messaging.SubMaster(list(SERVICES), poll="navAssistStateSP")
  pm = messaging.PubMaster(["navLaneIntentSP"])
  ratekeeper = Ratekeeper(PUBLISH_HZ)
  while True:
    sm.update(50)
    healthy = services_healthy(sm)
    nav = sm["navAssistStateSP"]
    topology = sm["laneTopologyStateSP"]
    car_state = sm["carState"]
    car_control = sm["carControl"]
    model_meta = sm["modelV2"].meta
    plan = NavLanePlan(
      valid=bool(healthy and nav.valid and not nav.stale),
      session_id=str(nav.sessionId),
      route_revision=int(nav.routeRevision),
      maneuver_event_id=int(nav.maneuverEventId),
      lane_count=len(nav.lanes),
      recommended_indices=tuple(int(lane.index) for lane in nav.lanes if lane.recommended),
    )
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
    intent = coordinator.update(plan, topology_input, vehicle, now_ns=now_ns)

    message = messaging.new_message("navLaneIntentSP")
    message.valid = healthy
    state = message.navLaneIntentSP
    state.publishMonoTime = now_ns
    state.valid = healthy
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
