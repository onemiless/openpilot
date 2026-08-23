from openpilot.sunnypilot.navassist.config import NavAssistParams
from openpilot.sunnypilot.navassist.nav_state import NavStateMachine
from openpilot.sunnypilot.navassist.types import InvalidReason, Maneuver, ProtocolSnapshot, StreamRecord


PARAMS = NavAssistParams(True, False, True, True, False, False, True, 1.2, 30 / 3.6)
NOW = 2_000_000_000


def record(value, received=NOW):
  return StreamRecord(True, 1, received, value)


def snapshot(records):
  return ProtocolSnapshot(True, "session123", 1, records)


def test_guidance_freshness_is_not_refreshed_by_vehicle():
  records = {
    "navigation_status": record({"guidance_active": True}),
    "guidance_current": record({"turn_type": 12, "distance_m": 50}, NOW - 2_000_000_000),
    "vehicle": record({"lat": 1, "lon": 1}),
  }
  state = NavStateMachine().update(snapshot(records), PARAMS, NOW)
  assert not state.guidance_valid
  assert state.maneuver == Maneuver.NONE


def test_off_route_clears_all_executable_intent():
  state = NavStateMachine().update(snapshot({
    "navigation_status": record({"guidance_active": True, "off_route": True}),
    "guidance_current": record({"turn_type": 12, "distance_m": 50}),
  }), PARAMS, NOW)
  assert state.invalid_reason == InvalidReason.OFF_ROUTE
  assert state.desired_speed_mps == 0
  assert state.maneuver == Maneuver.NONE


def test_same_maneuver_distance_updates_keep_id():
  machine = NavStateMachine()
  base = {"navigation_status": record({"guidance_active": True})}
  first = machine.update(snapshot(base | {"guidance_current": record({"turn_type": 12, "distance_m": 70, "main_text": "A"})}), PARAMS, NOW)
  second = machine.update(snapshot(base | {"guidance_current": record({"turn_type": 12, "distance_m": 30, "main_text": "A"})}), PARAMS, NOW)
  assert first.maneuver_id == second.maneuver_id != 0


def test_adjacent_same_direction_maneuver_gets_new_id_after_distance_reset():
  machine = NavStateMachine()
  base = {"navigation_status": record({"guidance_active": True})}
  first = machine.update(snapshot(base | {"guidance_current": record({"turn_type": 12, "distance_m": 5, "main_text": "A"})}), PARAMS, NOW)
  second = machine.update(snapshot(base | {"guidance_current": record({"turn_type": 12, "distance_m": 70, "main_text": "A"})}), PARAMS, NOW)
  assert first.maneuver_id != second.maneuver_id
