from types import SimpleNamespace

from openpilot.sunnypilot.navassist.nav_lane_intentd import build_lane_plan, navigation_linked


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


def test_explicit_amap_lane_info_overrides_extreme_lane_heuristic():
  lanes = [
    SimpleNamespace(index=0, recommended=False),
    SimpleNamespace(index=1, recommended=True),
    SimpleNamespace(index=2, recommended=False),
  ]
  plan = build_lane_plan(lane_guidance_nav(maneuver="turnLeft", lanes=lanes), topology(), healthy=True)

  assert not plan.heuristic
  assert plan.lane_count == 3
  assert plan.recommended_indices == (1,)


def test_turn_fallback_is_bounded_while_exit_fallback_starts_farther_out():
  far_turn = build_lane_plan(
    lane_guidance_nav(maneuver="turnLeft", maneuverDistanceM=1_500.0), topology(), healthy=True,
  )
  far_exit = build_lane_plan(
    lane_guidance_nav(maneuver="exitRight", maneuverDistanceM=1_500.0), topology(), healthy=True,
  )

  assert not far_turn.heuristic and far_turn.recommended_indices == ()
  assert far_exit.heuristic and far_exit.recommended_indices == (2,)


def test_slight_turn_without_lane_info_does_not_force_an_extreme_lane():
  plan = build_lane_plan(lane_guidance_nav(maneuver="slightLeft"), topology(), healthy=True)

  assert not plan.heuristic
  assert plan.recommended_indices == ()
