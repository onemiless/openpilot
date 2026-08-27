from types import SimpleNamespace as ns

from openpilot.sunnypilot.navassist.config import NavAssistParams
from openpilot.sunnypilot.navassist.turn_signal_policy import NavigationTurnSignalPolicy, TurnSignalAction


PARAMS = NavAssistParams(True, False, True, True, False, 1.2)


def nav(maneuver=1, distance=100.0, maneuver_id=7, **kwargs):
  values = {"sessionId": "session", "maneuverId": maneuver_id, "maneuver": ns(raw=maneuver),
            "dataValid": True, "guidanceValid": True, "guidanceActive": True, "stale": False, "offRoute": False,
            "distanceToManeuverM": distance}
  values.update(kwargs)
  return ns(**values)


def car(**kwargs):
  values = {"vEgo": 20.0, "leftBlinker": False, "rightBlinker": False, "brakePressed": False,
            "leftBlindspot": False, "rightBlindspot": False}
  values.update(kwargs)
  return ns(**values)


def test_navigation_requests_signal_without_bypassing_existing_blindspot_logic():
  decision = NavigationTurnSignalPolicy().update(
    nav(), True, PARAMS, car(leftBlindspot=True), True, None, 1_000_000_000,
  )
  assert decision.action == TurnSignalAction.REQUEST
  assert decision.direction == "left"


def test_forks_map_to_matching_signal_direction():
  left = NavigationTurnSignalPolicy().update(nav(maneuver=3), True, PARAMS, car(), True, None, 1_000_000_000)
  right = NavigationTurnSignalPolicy().update(nav(maneuver=4), True, PARAMS, car(), True, None, 1_000_000_000)
  assert left.direction == "left" and right.direction == "right"


def test_shadow_and_inactive_lateral_never_request_signal():
  shadow = NavAssistParams(True, True, True, True, False, 1.2)
  assert NavigationTurnSignalPolicy().update(nav(), True, shadow, car(), True, None, 1_000_000_000).action == TurnSignalAction.NONE
  assert NavigationTurnSignalPolicy().update(nav(), True, PARAMS, car(), False, None, 1_000_000_000).action == TurnSignalAction.NONE


def test_driver_blinker_owns_request_and_consumes_maneuver():
  policy = NavigationTurnSignalPolicy()
  assert policy.update(nav(), True, PARAMS, car(leftBlinker=True), True, None, 1_000_000_000).reason == "driver_blinker"
  assert policy.update(nav(), True, PARAMS, car(), True, None, 1_000_000_001).reason == "consumed"


def test_trigger_window_provides_ten_seconds_with_50_to_250_meter_bounds():
  assert NavigationTurnSignalPolicy().update(
    nav(distance=49), True, PARAMS, car(vEgo=5), True, None, 1_000_000_000,
  ).action == TurnSignalAction.REQUEST
  assert NavigationTurnSignalPolicy().update(
    nav(distance=51), True, PARAMS, car(vEgo=5), True, None, 1_000_000_000,
  ).reason == "window"
  assert NavigationTurnSignalPolicy().update(
    nav(distance=199), True, PARAMS, car(vEgo=20), True, None, 1_000_000_000,
  ).action == TurnSignalAction.REQUEST
  assert NavigationTurnSignalPolicy().update(
    nav(distance=201), True, PARAMS, car(vEgo=20), True, None, 1_000_000_000,
  ).reason == "window"
  assert NavigationTurnSignalPolicy().update(
    nav(distance=249), True, PARAMS, car(vEgo=30), True, None, 1_000_000_000,
  ).action == TurnSignalAction.REQUEST


def test_active_navigation_request_cancels_when_guidance_changes():
  status = {"origin": "navigation", "test_id": "nav:session:7", "direction": "left"}
  decision = NavigationTurnSignalPolicy().update(nav(stale=True), True, PARAMS, car(), True, status, 1_000_000_000)
  assert decision.action == TurnSignalAction.CANCEL
  assert decision.request_id == "nav:session:7"


def test_submitted_maneuver_is_one_shot():
  policy = NavigationTurnSignalPolicy()
  current = nav()
  decision = policy.update(current, True, PARAMS, car(), True, None, 1_000_000_000)
  assert decision.action == TurnSignalAction.REQUEST
  policy.mark_submitted(current, decision.request_id, 1_000_000_000)
  assert policy.update(current, True, PARAMS, car(), True, None, 1_000_000_001).reason == "awaiting_completion"


def test_session_timeout_without_lane_change_rearms_same_maneuver():
  policy = NavigationTurnSignalPolicy()
  current = nav()
  first = policy.update(current, True, PARAMS, car(), True, None, 1_000_000_000)
  policy.mark_submitted(current, first.request_id, 1_000_000_000)
  policy.complete({"test_id": first.request_id, "result": "PASS", "lane_change_started": False,
                   "cancel_reason": "session_timeout"}, 2_000_000_000)

  assert policy.update(current, True, PARAMS, car(), True, None, 2_500_000_000).reason == "retry_wait"
  second = policy.update(current, True, PARAMS, car(), True, None, 3_100_000_000)
  assert second.action == TurnSignalAction.REQUEST
  assert second.request_id != first.request_id


def test_completed_lane_change_consumes_maneuver_without_retry():
  policy = NavigationTurnSignalPolicy()
  current = nav()
  first = policy.update(current, True, PARAMS, car(), True, None, 1_000_000_000)
  policy.mark_submitted(current, first.request_id, 1_000_000_000)
  policy.complete({"test_id": first.request_id, "result": "PASS", "lane_change_started": True,
                   "cancel_reason": "lane_change_finishing"}, 2_000_000_000)
  assert policy.update(current, True, PARAMS, car(), True, None, 4_000_000_000).reason == "consumed"


def test_same_maneuver_has_at_most_three_bounded_attempts():
  policy = NavigationTurnSignalPolicy()
  current = nav()
  now = 1_000_000_000
  request_ids = []
  for _ in range(3):
    decision = policy.update(current, True, PARAMS, car(), True, None, now)
    assert decision.action == TurnSignalAction.REQUEST
    request_ids.append(decision.request_id)
    policy.mark_submitted(current, decision.request_id, now)
    now += 1_000_000_000
    policy.complete({"test_id": decision.request_id, "result": "PASS", "lane_change_started": False,
                     "cancel_reason": "session_timeout"}, now)
    now += 1_100_000_000
  assert len(set(request_ids)) == 3
  assert policy.update(current, True, PARAMS, car(), True, None, now).reason == "consumed"
