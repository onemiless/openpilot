#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import replace
import math
import time

from openpilot.cereal import messaging
from openpilot.common.params import Params
from openpilot.common.realtime import Ratekeeper
from openpilot.common.swaglog import cloudlog
from openpilot.sunnypilot.navassist.config import NavAssistParams, PUBLISH_HZ, ROUTE_CALC_HZ
from openpilot.sunnypilot.navassist.nav_state import NavStateMachine
from openpilot.sunnypilot.navassist.protocol.amap_companion_v1 import AMapCompanionReceiver, AMapCompanionServer
from openpilot.sunnypilot.navassist.protocol.carrot_v2 import CarrotV2Receiver, CarrotV2Server
from openpilot.sunnypilot.navassist.protocol.source_mux import StickySourceMux
from openpilot.sunnypilot.navassist.route_speed import RouteSpeedPlanner, RouteSpeedResult
from openpilot.sunnypilot.navassist.speed_planner import select_speed_candidate
from openpilot.sunnypilot.navassist.types import NavAssistState, SpeedCandidate, SpeedSource


MANEUVER_NAMES = ("none", "turnLeft", "turnRight", "forkLeft", "forkRight", "roundabout", "uturn", "arrive", "tollgate")
SPEED_SOURCE_NAMES = ("none", "maneuver", "nextManeuver", "speedCamera", "section", "routeCurve")
INVALID_REASON_NAMES = ("none", "disabled", "disconnected", "staleMessage", "protocolError", "sequenceError",
                        "navigationInactive", "offRoute", "locationInvalid")
SOURCE_NAMES = ("none", "carrotV2", "amapCompanionV1")


def _finite(value: float) -> float:
  return float(value) if math.isfinite(float(value)) else 0.0


def fill_nav_assist_message(message, state: NavAssistState, now_ns: int) -> None:
  nav = message.navAssistSP
  nav.schemaVersion = 1
  nav.sessionId = state.session_id[:64]
  nav.generation = state.generation
  nav.publishMonoTimeNanos = now_ns
  nav.connected = state.connected
  nav.dataValid = state.data_valid
  nav.guidanceValid = state.guidance_valid
  nav.speedValid = state.speed_valid
  nav.routeValid = state.route_valid
  nav.guidanceActive = state.guidance_active
  nav.offRoute = state.off_route
  nav.stale = state.stale
  nav.maneuver = MANEUVER_NAMES[int(state.maneuver)]
  nav.maneuverId = state.maneuver_id
  nav.rawTurnType = state.raw_turn_type
  nav.distanceToManeuverM = _finite(state.distance_to_maneuver_m)
  nav.maneuverTargetSpeedMps = _finite(state.maneuver_target_speed_mps)
  nav.nextManeuver = MANEUVER_NAMES[int(state.next_maneuver)]
  nav.nextManeuverId = state.next_maneuver_id
  nav.rawNextTurnType = state.raw_next_turn_type
  nav.distanceToNextManeuverM = _finite(state.distance_to_next_maneuver_m)
  nav.roadLimitMps = _finite(state.road_limit_mps)
  nav.routeSpeedMps = _finite(state.route_speed_mps)
  nav.speedCameraMps = _finite(state.speed_camera_mps)
  nav.speedCameraDistanceM = _finite(state.speed_camera_distance_m)
  nav.sectionSpeedMps = _finite(state.section_speed_mps)
  nav.sectionDistanceM = _finite(state.section_distance_m)
  nav.desiredSpeedMps = _finite(state.desired_speed_mps)
  nav.speedControlDistanceM = _finite(state.speed_control_distance_m)
  nav.speedSource = SPEED_SOURCE_NAMES[int(state.speed_source)]
  nav.routeDeviationM = _finite(state.route_deviation_m)
  nav.invalidReason = INVALID_REASON_NAMES[int(state.invalid_reason)]
  nav.source = SOURCE_NAMES[int(state.source)]


def add_route_constraint(state: NavAssistState, result: RouteSpeedResult) -> NavAssistState:
  if not result.valid:
    return replace(state, route_valid=False, route_speed_mps=0.0,
                   route_deviation_m=result.deviation_m)
  candidates = []
  if state.desired_speed_mps > 0:
    candidates.append(SpeedCandidate(state.speed_source, state.desired_speed_mps, state.speed_control_distance_m))
  if result.speed_mps > 0:
    candidates.append(SpeedCandidate(SpeedSource.ROUTE_CURVE, result.speed_mps, result.control_distance_m))
  selected = select_speed_candidate(candidates)
  return replace(
    state, route_valid=True, route_speed_mps=result.speed_mps, route_deviation_m=result.deviation_m,
    desired_speed_mps=selected.target_speed_mps if selected else 0.0,
    speed_control_distance_m=selected.control_distance_m if selected else 0.0,
    speed_source=selected.source if selected else SpeedSource.NONE,
  )


def main() -> None:
  params_store = Params()
  params = NavAssistParams.read(params_store)
  carrot_receiver = CarrotV2Receiver()
  carrot_server = CarrotV2Server(carrot_receiver)
  amap_receiver = AMapCompanionReceiver()
  amap_server = AMapCompanionServer(amap_receiver)
  carrot_server.start()
  amap_server.start()
  state_machine = NavStateMachine()
  pm = messaging.PubMaster(["navAssistSP"])
  rk = Ratekeeper(PUBLISH_HZ)
  last_params_read = 0.0
  last_route_calc = 0.0
  last_route_key: tuple[str, int, int] | None = None
  route_result = RouteSpeedResult()
  route_planner = RouteSpeedPlanner()
  source_mux = StickySourceMux()
  cloudlog.info("navassistd started: Carrot V2 TCP 7714, AMap Companion TCP 7715, discovery UDP 7705")

  while True:
    now = time.monotonic()
    now_ns = time.monotonic_ns()
    if now - last_params_read >= 1.0:
      params = NavAssistParams.read(params_store)
      last_params_read = now
    snapshot = source_mux.select((carrot_receiver.snapshot(), amap_receiver.snapshot()), now_ns, params.message_timeout_s)
    state = state_machine.update(snapshot, params, now_ns)

    route_key = (snapshot.session_id, snapshot.record("route").sequence, snapshot.record("vehicle").sequence)
    route_changed = route_key != last_route_key
    if state.route_valid and params.route_speed_control and (route_changed or now - last_route_calc >= 1.0 / ROUTE_CALC_HZ):
      vehicle = snapshot.record("vehicle").value
      route = snapshot.record("route").value
      if isinstance(vehicle, dict) and isinstance(route, dict):
        try:
          location = (float(vehicle["lat"]), float(vehicle["lon"]))
          points = tuple((float(p["lat"]), float(p["lon"])) for p in route.get("polyline", ()))
          route_result = route_planner.calculate(location, points)
        except (KeyError, TypeError, ValueError, OverflowError):
          route_result = RouteSpeedResult()
      last_route_calc = now
      last_route_key = route_key
    if params.route_speed_control and state.route_valid:
      state = add_route_constraint(state, route_result)

    message = messaging.new_message("navAssistSP")
    message.valid = True
    fill_nav_assist_message(message, state, now_ns)
    pm.send("navAssistSP", message)
    rk.keep_time()


if __name__ == "__main__":
  main()
