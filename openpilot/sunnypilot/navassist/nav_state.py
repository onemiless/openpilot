from __future__ import annotations

import hashlib
import math

from openpilot.common.constants import CV
from openpilot.sunnypilot.navassist.config import NavAssistParams
from openpilot.sunnypilot.navassist.speed_planner import select_speed_candidate
from openpilot.sunnypilot.navassist.turn_mapper import map_turn_type
from openpilot.sunnypilot.navassist.types import (
  InvalidReason, Maneuver, NavAssistState, ProtocolSnapshot, SpeedCandidate, SpeedSource, StreamRecord,
)


TURN_SPEED_MPS = 25.0 * CV.KPH_TO_MS
FORK_SPEED_MPS = 50.0 * CV.KPH_TO_MS
ROUNDABOUT_SPEED_MPS = 20.0 * CV.KPH_TO_MS
UTURN_SPEED_MPS = 10.0 * CV.KPH_TO_MS


def _dict(value: object | None) -> dict:
  return value if isinstance(value, dict) else {}


def _finite(value: object, default: float = 0.0) -> float:
  try:
    result = float(value)
  except (TypeError, ValueError, OverflowError):
    return default
  return result if math.isfinite(result) else default


def _integer(value: object, default: int = -1) -> int:
  if isinstance(value, bool):
    return default
  try:
    return int(value)
  except (TypeError, ValueError, OverflowError):
    return default


def _fresh(record: StreamRecord, now_ns: int, timeout_ns: int) -> bool:
  age = now_ns - record.received_mono_ns
  return record.present and record.received_mono_ns > 0 and 0 <= age <= timeout_ns


def _maneuver_speed(maneuver: Maneuver, road_limit_mps: float) -> float:
  if maneuver in (Maneuver.TURN_LEFT, Maneuver.TURN_RIGHT):
    return TURN_SPEED_MPS
  if maneuver in (Maneuver.FORK_LEFT, Maneuver.FORK_RIGHT):
    return min(road_limit_mps, FORK_SPEED_MPS) if road_limit_mps > 0 else FORK_SPEED_MPS
  if maneuver == Maneuver.ROUNDABOUT:
    return ROUNDABOUT_SPEED_MPS
  if maneuver == Maneuver.UTURN:
    return UTURN_SPEED_MPS
  return 0.0


class ManeuverIdentity:
  def __init__(self) -> None:
    self._session_id = ""
    self._signature = ""
    self._distance_m = 0.0
    self._id = 0
    self._generation = -1

  def update(self, session_id: str, maneuver: Maneuver, guidance: dict, generation: int) -> int:
    if maneuver == Maneuver.NONE:
      self._signature = ""
      self._distance_m = 0.0
      return 0
    point = _dict(guidance.get("point"))
    stable_text = str(guidance.get("road_name") or guidance.get("main_text") or "")[:96]
    signature = f"{int(maneuver)}|{stable_text}|{_finite(point.get('lat'), 999):.5f}|{_finite(point.get('lon'), 999):.5f}"
    distance_m = max(0.0, _finite(guidance.get("distance_m")))
    new_action = (
      session_id != self._session_id or generation != self._generation or signature != self._signature
      or (self._distance_m <= 30.0 and distance_m > self._distance_m + 30.0)
    )
    if new_action:
      raw = f"{session_id}|{generation}|{signature}|{self._id + 1}".encode()
      self._id = int.from_bytes(hashlib.blake2s(raw, digest_size=8).digest(), "big") or 1
    self._session_id = session_id
    self._signature = signature
    self._distance_m = distance_m
    self._generation = generation
    return self._id


class NavStateMachine:
  def __init__(self) -> None:
    self._current_identity = ManeuverIdentity()
    self._next_identity = ManeuverIdentity()
    self._route_signature: tuple | None = None
    self._route_generation = 0

  def _update_route_generation(self, route_record: StreamRecord) -> int:
    route = _dict(route_record.value) if route_record.present else {}
    points = route.get("polyline", ())
    signature = tuple(
      (round(_finite(_dict(point).get("lat"), 999.0), 5), round(_finite(_dict(point).get("lon"), 999.0), 5))
      for point in points if isinstance(point, dict)
    ) if isinstance(points, (list, tuple)) else ()
    if signature and self._route_signature is not None and signature != self._route_signature:
      self._route_generation += 1
    if signature:
      self._route_signature = signature
    return self._route_generation

  def update(self, snapshot: ProtocolSnapshot, params: NavAssistParams, now_ns: int) -> NavAssistState:
    if not params.enabled:
      return NavAssistState(connected=snapshot.connected, session_id=snapshot.session_id,
                            generation=snapshot.generation, invalid_reason=InvalidReason.DISABLED)
    if not snapshot.connected:
      return NavAssistState(session_id=snapshot.session_id, generation=snapshot.generation,
                            invalid_reason=InvalidReason.DISCONNECTED)
    if snapshot.protocol_error:
      return NavAssistState(connected=True, session_id=snapshot.session_id, generation=snapshot.generation,
                            invalid_reason=InvalidReason.PROTOCOL_ERROR)
    if snapshot.sequence_error:
      return NavAssistState(connected=True, session_id=snapshot.session_id, generation=snapshot.generation,
                            invalid_reason=InvalidReason.SEQUENCE_ERROR)

    timeout_ns = int(params.message_timeout_s * 1e9)
    status_record = snapshot.record("navigation_status")
    status_fresh = _fresh(status_record, now_ns, timeout_ns)
    status = _dict(status_record.value)
    if not status_fresh:
      return NavAssistState(connected=True, session_id=snapshot.session_id, generation=snapshot.generation,
                            invalid_reason=InvalidReason.STALE_MESSAGE)
    guidance_active = bool(status.get("guidance_active", False))
    off_route = bool(status.get("off_route", False)) or status.get("mode") == "off_route"
    if off_route:
      return NavAssistState(connected=True, session_id=snapshot.session_id, generation=snapshot.generation,
                            guidance_active=guidance_active, off_route=True, stale=False,
                            invalid_reason=InvalidReason.OFF_ROUTE)
    if not guidance_active:
      return NavAssistState(connected=True, session_id=snapshot.session_id, generation=snapshot.generation,
                            stale=False, invalid_reason=InvalidReason.NAVIGATION_INACTIVE)

    current_record = snapshot.record("guidance_current")
    next_record = snapshot.record("guidance_next")
    speed_record = snapshot.record("speed")
    route_record = snapshot.record("route")
    vehicle_record = snapshot.record("vehicle")
    guidance_valid = _fresh(current_record, now_ns, timeout_ns)
    next_valid = _fresh(next_record, now_ns, timeout_ns)
    speed_valid = _fresh(speed_record, now_ns, timeout_ns)
    route_valid = _fresh(route_record, now_ns, timeout_ns) and _fresh(vehicle_record, now_ns, timeout_ns)
    route_generation = self._update_route_generation(route_record)
    maneuver_generation = (snapshot.generation << 32) | route_generation

    current = _dict(current_record.value) if guidance_valid else {}
    following = _dict(next_record.value) if next_valid else {}
    speed = _dict(speed_record.value) if speed_valid else {}
    raw_turn = _integer(current.get("turn_type"))
    raw_next = _integer(following.get("turn_type"))
    maneuver = map_turn_type(raw_turn)
    next_maneuver = map_turn_type(raw_next)
    distance_m = max(0.0, _finite(current.get("distance_m")))
    next_distance_m = max(0.0, _finite(following.get("distance_m")))

    road_limit_kph = _finite(speed.get("road_limit_kph"))
    road_limit_mps = road_limit_kph * CV.KPH_TO_MS if 0 < road_limit_kph <= 200 and road_limit_kph % 10 == 0 else 0.0
    maneuver_speed = _maneuver_speed(maneuver, road_limit_mps)
    next_maneuver_speed = _maneuver_speed(next_maneuver, road_limit_mps)
    cumulative_next_distance_m = next_distance_m + (distance_m if guidance_valid else 0.0)
    candidates: list[SpeedCandidate] = []
    if guidance_valid and maneuver_speed > 0:
      candidates.append(SpeedCandidate(SpeedSource.MANEUVER, maneuver_speed, distance_m))
    if next_valid and next_maneuver_speed > 0:
      candidates.append(SpeedCandidate(SpeedSource.NEXT_MANEUVER, next_maneuver_speed, cumulative_next_distance_m))

    camera_candidates = []
    for camera_name in ("sdi", "sdi_secondary"):
      sdi = _dict(speed.get(camera_name))
      candidate_speed = _finite(sdi.get("speed_limit_kph")) * CV.KPH_TO_MS
      candidate_distance = max(0.0, _finite(sdi.get("distance_m")))
      if speed_valid and candidate_speed > 0 and candidate_distance > 0:
        camera_candidates.append(SpeedCandidate(SpeedSource.SPEED_CAMERA, candidate_speed, candidate_distance))
    selected_camera = select_speed_candidate(camera_candidates)
    camera_speed = selected_camera.target_speed_mps if selected_camera else 0.0
    camera_distance = selected_camera.control_distance_m if selected_camera else 0.0
    candidates.extend(camera_candidates)

    section = _dict(speed.get("section"))
    section_active = (bool(section.get("active", False)) and not bool(section.get("suspended", False))
                      and not bool(section.get("off_route", False)))
    section_speed = _finite(section.get("speed_limit_kph")) * CV.KPH_TO_MS
    section_distance = max(0.0, _finite(section.get("remaining_distance_m")))
    if speed_valid and section_active and section_speed > 0:
      candidates.append(SpeedCandidate(SpeedSource.SECTION, section_speed, section_distance))

    selected = select_speed_candidate(candidates)
    data_valid = guidance_valid or speed_valid or route_valid
    if not data_valid:
      return NavAssistState(
        connected=True, session_id=snapshot.session_id, generation=snapshot.generation,
        guidance_active=True, stale=True, invalid_reason=InvalidReason.STALE_MESSAGE,
      )
    return NavAssistState(
      connected=True, session_id=snapshot.session_id, generation=snapshot.generation,
      data_valid=data_valid, guidance_valid=guidance_valid, speed_valid=speed_valid, route_valid=route_valid,
      guidance_active=True, stale=False, invalid_reason=InvalidReason.NONE,
      maneuver=maneuver, maneuver_id=self._current_identity.update(snapshot.session_id, maneuver, current, maneuver_generation),
      raw_turn_type=raw_turn, distance_to_maneuver_m=distance_m, maneuver_target_speed_mps=maneuver_speed,
      next_maneuver=next_maneuver,
      next_maneuver_id=self._next_identity.update(snapshot.session_id, next_maneuver, following, maneuver_generation),
      raw_next_turn_type=raw_next, distance_to_next_maneuver_m=cumulative_next_distance_m,
      road_limit_mps=road_limit_mps,
      speed_camera_mps=camera_speed if speed_valid else 0.0,
      speed_camera_distance_m=camera_distance if speed_valid else 0.0,
      section_speed_mps=section_speed if speed_valid and section_active else 0.0,
      section_distance_m=section_distance if speed_valid and section_active else 0.0,
      desired_speed_mps=selected.target_speed_mps if selected else 0.0,
      speed_control_distance_m=selected.control_distance_m if selected else 0.0,
      speed_source=selected.source if selected else SpeedSource.NONE,
    )
