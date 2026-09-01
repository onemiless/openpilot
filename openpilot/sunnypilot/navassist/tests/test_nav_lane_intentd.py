from types import SimpleNamespace

from openpilot.sunnypilot.navassist.nav_lane_intentd import navigation_linked


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
