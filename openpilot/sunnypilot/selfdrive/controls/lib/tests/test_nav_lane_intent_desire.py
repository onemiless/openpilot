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


def intent(*, direction="left", signal=True, target=0):
  return SimpleNamespace(valid=True, signalRequested=signal, direction=direction, targetLaneIndex=target)


def helper():
  desire = DesireHelper()
  desire.alc.update_params = lambda: None
  desire.alc.lane_change_set_timer = AutoLaneChangeMode.NUDGELESS
  desire.lane_turn_controller.update_params = lambda: None
  return desire


def test_navigation_signal_enters_pre_lane_change_but_waits_for_sp_crossing_gate():
  desire = helper()
  desire.update(car_state(), True, 1.0, nav_lane_intent=intent())
  assert desire.lane_change_state == LaneChangeState.preLaneChange

  for _ in range(10):
    desire.update(car_state(leftBlinker=True), True, 1.0, nav_lane_intent=intent())
  assert desire.lane_change_state == LaneChangeState.preLaneChange

  desire.update(car_state(leftBlinker=True), True, 1.0, nav_lane_intent=intent(),
                left_crossing_allowed=True)
  assert desire.lane_change_state == LaneChangeState.laneChangeStarting


def test_navigation_target_never_overrides_blindspot_or_conflicting_driver_signal():
  blocked = helper()
  blocked.update(car_state(leftBlindspot=True), True, 1.0, nav_lane_intent=intent(), left_crossing_allowed=True)
  blocked.update(car_state(leftBlinker=True, leftBlindspot=True), True, 1.0,
                 nav_lane_intent=intent(), left_crossing_allowed=True)
  assert blocked.lane_change_state == LaneChangeState.preLaneChange

  conflict = helper()
  conflict.update(car_state(rightBlinker=True), True, 1.0, nav_lane_intent=intent(direction="left"))
  assert conflict.lane_change_state == LaneChangeState.preLaneChange
  assert conflict.lane_change_direction == LaneChangeDirection.right


def test_navigation_target_never_overrides_solid_line_or_road_edge():
  for blockers in (
    {"left_line_blocked": True},
    {"left_edge_detected": True},
  ):
    desire = helper()
    desire.update(car_state(), True, 1.0, nav_lane_intent=intent(), left_crossing_allowed=True, **blockers)
    desire.update(car_state(leftBlinker=True), True, 1.0, nav_lane_intent=intent(),
                  left_crossing_allowed=True, **blockers)

    assert desire.lane_change_state == LaneChangeState.preLaneChange


def test_navigation_turn_signal_does_not_enter_lane_change_state_machine():
  desire = helper()
  turn_only = intent(target=-1)

  desire.update(car_state(), True, 1.0, nav_lane_intent=turn_only)

  # The Tesla turn-signal controller makes the requested lamp physical. Its
  # feedback returns through carState and must retain the turn-only intent
  # instead of looking like a new driver lane-change request.
  for _ in range(10):
    desire.update(car_state(leftBlinker=True), True, 1.0, nav_lane_intent=turn_only)

  assert desire.lane_change_state == LaneChangeState.off
  assert desire.lane_change_direction == LaneChangeDirection.none


def test_navigation_lane_change_lamp_does_not_trigger_lane_turn_desire():
  desire = helper()
  desire.lane_turn_controller.enabled = True
  desire.lane_turn_controller.update_params = lambda: None
  desire.lane_turn_controller.lane_turn_value = 20.0
  lane_target = intent(target=0)

  desire.update(car_state(vEgo=5.0), True, 1.0, nav_lane_intent=lane_target)
  desire.update(car_state(vEgo=5.0, leftBlinker=True), True, 1.0, nav_lane_intent=lane_target,
                left_crossing_allowed=True)

  assert desire.lane_turn_direction == 0
  assert desire.desire == 0


def test_navigation_turn_only_lamp_retains_lane_turn_desire():
  desire = helper()
  desire.lane_turn_controller.enabled = True
  desire.lane_turn_controller.update_params = lambda: None
  desire.lane_turn_controller.lane_turn_value = 20.0
  turn_only = intent(target=-1)

  desire.update(car_state(vEgo=5.0), True, 1.0, nav_lane_intent=turn_only)
  desire.update(car_state(vEgo=5.0, leftBlinker=True), True, 1.0, nav_lane_intent=turn_only)

  assert int(desire.lane_turn_direction) != 0


def test_navigation_lane_target_respects_sp_alc_off():
  desire = helper()
  desire.alc.lane_change_set_timer = AutoLaneChangeMode.OFF
  lane_target = intent(target=0)

  desire.update(car_state(), True, 1.0, nav_lane_intent=lane_target,
                left_crossing_allowed=True)
  for _ in range(10):
    desire.alc.lane_change_set_timer = AutoLaneChangeMode.OFF
    desire.update(car_state(leftBlinker=True), True, 1.0, nav_lane_intent=lane_target,
                  left_crossing_allowed=True)

  assert desire.lane_change_state == LaneChangeState.off
  assert desire.desire == 0


def test_navigation_lane_target_uses_sp_alc_after_physical_lamp_and_dashed_boundary():
  desire = helper()
  lane_target = intent(target=0)

  desire.update(car_state(), True, 1.0, nav_lane_intent=lane_target,
                left_crossing_allowed=True)
  for _ in range(10):
    desire.update(car_state(leftBlinker=True), True, 1.0, nav_lane_intent=lane_target,
                  left_crossing_allowed=True)

  assert desire.lane_change_state == LaneChangeState.laneChangeStarting


def test_navigation_physical_lamp_tail_cannot_start_an_extra_lane_change():
  desire = helper()
  lane_target = intent(target=0)

  desire.update(car_state(), True, 1.0, nav_lane_intent=lane_target)
  for _ in range(10):
    desire.update(car_state(leftBlinker=True), True, 1.0, nav_lane_intent=lane_target)
  assert desire.lane_change_state == LaneChangeState.preLaneChange

  stopped = intent(signal=False, target=0)
  for _ in range(5):
    desire.update(car_state(leftBlinker=True), True, 1.0, nav_lane_intent=stopped)

  assert desire.lane_change_state == LaneChangeState.off
  assert desire.desire == 0
