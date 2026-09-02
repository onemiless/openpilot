from types import SimpleNamespace

from openpilot.sunnypilot.navassist.lane_intent import LaneIntentDirection
from openpilot.sunnypilot.navassist.nav_lane_intentd import build_lane_plan, navigation_linked
from openpilot.sunnypilot.selfdrive.controls.lib.nav_turn_completion import sp_turn_geometry_active


def nav(**updates):
  values = {
    "stale": False,
    "routeActive": True,
    "routeMatched": True,
    "mode": "realtime",
    "maneuverEventId": 11,
  }
  values.update(updates)
  return SimpleNamespace(**values)


def test_pre_turn_signal_uses_fresh_linked_route_without_full_gps_control_validity():
  assert navigation_linked(nav(), base_healthy=True)


def test_pre_turn_signal_rejects_stale_inactive_unmatched_or_non_realtime_routes():
  assert not navigation_linked(nav(stale=True), base_healthy=True)
  assert not navigation_linked(nav(routeActive=False), base_healthy=True)
  assert not navigation_linked(nav(routeMatched=False), base_healthy=True)
  assert not navigation_linked(nav(mode="simulation"), base_healthy=True)
  assert not navigation_linked(nav(maneuverEventId=0), base_healthy=True)
  assert not navigation_linked(nav(), base_healthy=False)


def test_sp_turn_geometry_uses_existing_vision_lateral_acceleration_threshold():
  straight = SimpleNamespace(desiredCurvature=0.01)
  turning = SimpleNamespace(desiredCurvature=0.015)
  assert not sp_turn_geometry_active(straight, 10.0)
  assert sp_turn_geometry_active(turning, 10.0)


def lane_guidance_nav(**updates):
  values = {
    "valid": True,
    "stale": False,
    "sessionId": "session-a",
    "routeRevision": 3,
    "maneuverEventId": 17,
    "maneuver": "turnLeft",
    "maneuverDistanceM": 800.0,
    "lanes": [],
  }
  values.update(updates)
  return SimpleNamespace(**values)


def topology(count=3):
  return SimpleNamespace(visibleLaneCount=count)


def test_missing_lane_info_uses_visual_extreme_lane_for_ordinary_turns():
  left = build_lane_plan(lane_guidance_nav(maneuver="turnLeft"), topology(), healthy=True)
  right = build_lane_plan(lane_guidance_nav(maneuver="turnRight"), topology(), healthy=True)

  assert left.valid and left.heuristic and left.lane_count == 3 and left.recommended_indices == (0,)
  assert right.valid and right.heuristic and right.lane_count == 3 and right.recommended_indices == (2,)
  assert left.allow_unknown_crossing and right.allow_unknown_crossing
  assert not left.ignore_solid_boundary and not right.ignore_solid_boundary


def test_unanchored_middle_amap_lane_is_not_treated_as_a_visual_absolute_index():
  lanes = [
    SimpleNamespace(index=0, recommended=False),
    SimpleNamespace(index=1, recommended=True),
    SimpleNamespace(index=2, recommended=False),
  ]
  plan = build_lane_plan(lane_guidance_nav(maneuver="turnLeft", lanes=lanes), topology(), healthy=True)

  assert not plan.valid
  assert not plan.heuristic
  assert plan.recommended_indices == ()


def test_amap_edge_recommendation_qualifies_relative_extreme_on_wider_road():
  lanes = [SimpleNamespace(index=index, recommended=index == 0) for index in range(4)]

  plan = build_lane_plan(lane_guidance_nav(maneuver="turnLeft", lanes=lanes), topology(count=3), healthy=True)

  assert plan.valid and plan.heuristic
  assert plan.lane_count == 3
  assert plan.recommended_indices == (0,)


def test_turn_fallback_is_bounded_while_exit_fallback_starts_farther_out():
  far_turn = build_lane_plan(
    lane_guidance_nav(maneuver="turnLeft", maneuverDistanceM=1_500.0), topology(), healthy=True,
  )
  far_exit = build_lane_plan(
    lane_guidance_nav(maneuver="exitRight", maneuverDistanceM=1_500.0), topology(), healthy=True,
  )

  assert not far_turn.heuristic and far_turn.recommended_indices == ()
  assert far_exit.heuristic and far_exit.recommended_indices == (2,)


def test_imminent_exit_builds_a_bounded_cp_style_fork_now_policy():
  plan = build_lane_plan(
    lane_guidance_nav(maneuver="exitRight", maneuverDistanceM=50.0), topology(count=1), healthy=True,
  )

  assert plan.valid and plan.heuristic
  assert plan.edge_direction == LaneIntentDirection.right
  assert plan.force_fork
  assert plan.allow_unknown_crossing
  assert plan.ignore_solid_boundary


def test_slight_turn_without_lane_info_does_not_force_an_extreme_lane():
  plan = build_lane_plan(lane_guidance_nav(maneuver="slightLeft"), topology(), healthy=True)

  assert not plan.heuristic
  assert plan.recommended_indices == ()
