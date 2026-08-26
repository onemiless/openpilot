from openpilot.sunnypilot.navassist.config import NavAssistParams
from openpilot.sunnypilot.navassist.nav_state import NavStateMachine
from openpilot.sunnypilot.navassist.types import InvalidReason, Maneuver, ProtocolSnapshot, StreamRecord


PARAMS = NavAssistParams(True, False, True, True, False, 1.2)
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


def test_next_maneuver_contributes_cumulative_speed_target():
  state = NavStateMachine().update(snapshot({
    "navigation_status": record({"guidance_active": True}),
    "guidance_current": record({"turn_type": 51, "distance_m": 100}),
    "guidance_next": record({"turn_type": 12, "distance_m": 200}),
  }), PARAMS, NOW)
  assert state.speed_source.name == "NEXT_MANEUVER"
  assert state.distance_to_next_maneuver_m == 300
  assert state.speed_control_distance_m == 300


def test_route_change_reidentifies_same_direction_maneuver():
  machine = NavStateMachine()
  base = {
    "navigation_status": record({"guidance_active": True}),
    "guidance_current": record({"turn_type": 12, "distance_m": 70, "main_text": "A"}),
  }
  first = machine.update(snapshot(base | {"route": record({"polyline": [{"lat": 37.0, "lon": 127.0}, {"lat": 37.1, "lon": 127.1}]})}), PARAMS, NOW)
  second = machine.update(snapshot(base | {"route": record({"polyline": [{"lat": 37.0, "lon": 127.0}, {"lat": 37.2, "lon": 127.2}]})}), PARAMS, NOW)
  assert first.maneuver_id != second.maneuver_id


def test_all_control_streams_stale_reports_stale():
  state = NavStateMachine().update(snapshot({
    "navigation_status": record({"guidance_active": True}),
  }), PARAMS, NOW)
  assert not state.data_valid
  assert state.stale
  assert state.invalid_reason == InvalidReason.STALE_MESSAGE


def test_section_local_off_route_is_not_a_candidate():
  state = NavStateMachine().update(snapshot({
    "navigation_status": record({"guidance_active": True}),
    "speed": record({"section": {"active": True, "off_route": True, "speed_limit_kph": 40,
                                    "remaining_distance_m": 500}}),
  }), PARAMS, NOW)
  assert state.section_speed_mps == 0


def test_secondary_sdi_can_supply_stricter_camera_target():
  state = NavStateMachine().update(snapshot({
    "navigation_status": record({"guidance_active": True}),
    "speed": record({
      "sdi": {"speed_limit_kph": 80, "distance_m": 300},
      "sdi_secondary": {"speed_limit_kph": 50, "distance_m": 500},
    }),
  }), PARAMS, NOW)
  assert round(state.speed_camera_mps * 3.6) == 50
  assert state.speed_camera_distance_m == 500
