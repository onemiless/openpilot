from types import SimpleNamespace

from openpilot.selfdrive.controls.lib.desire_helper import DesireHelper, LaneChangeDirection, LaneChangeState
from openpilot.sunnypilot.selfdrive.controls.lib.auto_lane_change import AutoLaneChangeMode


def car_state(**updates):
  values = {
    "vEgo": 15.0,
    "leftBlinker": False,
    "rightBlinker": False,
    "leftBlindspot": False,
    "rightBlindspot": False,
    "brakePressed": False,
    "steeringPressed": False,
    "steeringTorque": 0.0,
  }
  values.update(updates)
  return SimpleNamespace(**values)


def intent(*, direction="left", authorized=False, signal=True, target=0):
  return SimpleNamespace(valid=True, signalRequested=signal, laneChangeAuthorized=authorized,
                         direction=direction, targetLaneIndex=target)


def helper():
  desire = DesireHelper()
  desire.alc.update_params = lambda: None
  desire.alc.lane_change_set_timer = AutoLaneChangeMode.NUDGELESS
  desire.lane_turn_controller.update_params = lambda: None
  return desire


def test_navigation_signal_enters_pre_lane_change_but_waits_for_authority():
  desire = helper()
  desire.update(car_state(), True, 1.0, nav_lane_intent=intent(authorized=False))
  assert desire.lane_change_state == LaneChangeState.preLaneChange

  for _ in range(10):
    desire.update(car_state(leftBlinker=True), True, 1.0, nav_lane_intent=intent(authorized=False))
  assert desire.lane_change_state == LaneChangeState.preLaneChange

  desire.update(car_state(leftBlinker=True), True, 1.0, nav_lane_intent=intent(authorized=True))
  assert desire.lane_change_state == LaneChangeState.laneChangeStarting


def test_navigation_authority_never_overrides_blindspot_or_conflicting_driver_signal():
  blocked = helper()
  blocked.update(car_state(leftBlindspot=True), True, 1.0, nav_lane_intent=intent(authorized=True))
  blocked.update(car_state(leftBlinker=True, leftBlindspot=True), True, 1.0, nav_lane_intent=intent(authorized=True))
  assert blocked.lane_change_state == LaneChangeState.preLaneChange

  conflict = helper()
  conflict.update(car_state(rightBlinker=True), True, 1.0, nav_lane_intent=intent(direction="left", authorized=True))
  assert conflict.lane_change_state == LaneChangeState.preLaneChange
  assert conflict.lane_change_direction == LaneChangeDirection.right


def test_navigation_authority_never_overrides_solid_line_or_road_edge():
  for blockers in (
    {"left_line_blocked": True},
    {"left_edge_detected": True},
  ):
    desire = helper()
    desire.update(car_state(), True, 1.0, nav_lane_intent=intent(authorized=True), **blockers)
    desire.update(car_state(leftBlinker=True), True, 1.0, nav_lane_intent=intent(authorized=True), **blockers)

    assert desire.lane_change_state == LaneChangeState.preLaneChange


def test_navigation_turn_signal_does_not_enter_lane_change_state_machine():
  desire = helper()

  desire.update(car_state(), True, 1.0, nav_lane_intent=intent(target=-1))

  assert desire.lane_change_state == LaneChangeState.off
  assert desire.lane_change_direction == LaneChangeDirection.none
