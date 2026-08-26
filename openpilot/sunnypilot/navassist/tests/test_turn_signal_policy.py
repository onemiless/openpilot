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


def control(**kwargs):
  values = {"latActive": True}
  values.update(kwargs)
  return ns(**values)


def test_navigation_requests_signal_without_bypassing_existing_blindspot_logic():
  decision = NavigationTurnSignalPolicy().update(
    nav(), True, PARAMS, car(leftBlindspot=True), control(), None,
  )
  assert decision.action == TurnSignalAction.REQUEST
  assert decision.direction == "left"


def test_forks_map_to_matching_signal_direction():
  left = NavigationTurnSignalPolicy().update(nav(maneuver=3), True, PARAMS, car(), control(), None)
  right = NavigationTurnSignalPolicy().update(nav(maneuver=4), True, PARAMS, car(), control(), None)
  assert left.direction == "left" and right.direction == "right"


def test_shadow_and_inactive_lateral_never_request_signal():
  shadow = NavAssistParams(True, True, True, True, False, 1.2)
  assert NavigationTurnSignalPolicy().update(nav(), True, shadow, car(), control(), None).action == TurnSignalAction.NONE
  assert NavigationTurnSignalPolicy().update(nav(), True, PARAMS, car(), control(latActive=False), None).action == TurnSignalAction.NONE


def test_driver_blinker_owns_request_and_consumes_maneuver():
  policy = NavigationTurnSignalPolicy()
  assert policy.update(nav(), True, PARAMS, car(leftBlinker=True), control(), None).reason == "driver_blinker"
  assert policy.update(nav(), True, PARAMS, car(), control(), None).reason == "consumed"


def test_trigger_window_scales_with_speed():
  policy = NavigationTurnSignalPolicy()
  assert policy.update(nav(distance=130), True, PARAMS, car(vEgo=20), control(), None).reason == "window"
  assert policy.update(nav(distance=130), True, PARAMS, car(vEgo=25), control(), None).action == TurnSignalAction.REQUEST


def test_active_navigation_request_cancels_when_guidance_changes():
  status = {"origin": "navigation", "test_id": "nav:session:7", "direction": "left"}
  decision = NavigationTurnSignalPolicy().update(nav(stale=True), True, PARAMS, car(), control(), status)
  assert decision.action == TurnSignalAction.CANCEL
  assert decision.request_id == "nav:session:7"


def test_submitted_maneuver_is_one_shot():
  policy = NavigationTurnSignalPolicy()
  current = nav()
  decision = policy.update(current, True, PARAMS, car(), control(), None)
  assert decision.action == TurnSignalAction.REQUEST
  policy.mark_submitted(current)
  assert policy.update(current, True, PARAMS, car(), control(), None).reason == "consumed"
