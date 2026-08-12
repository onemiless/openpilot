from cereal import log

from openpilot.selfdrive.controls.lib.desire_helper import (
  BLINKER_LEFT,
  BLINKER_NONE,
  BLINKER_RIGHT,
  update_automatic_blinker_intent,
)


LaneChangeState = log.LaneChangeState
LaneChangeDirection = log.LaneChangeDirection


def test_automatic_overtake_blinker_is_latched_through_lane_change():
  intent = update_automatic_blinker_intent(
    BLINKER_NONE, LaneChangeState.preLaneChange, LaneChangeDirection.left, BLINKER_LEFT, BLINKER_NONE,
  )
  assert intent == BLINKER_LEFT

  for state in (LaneChangeState.laneChangeStarting, LaneChangeState.laneChangeFinishing):
    intent = update_automatic_blinker_intent(
      intent, state, LaneChangeDirection.left, BLINKER_NONE, BLINKER_NONE,
    )
    assert intent == BLINKER_LEFT

  assert update_automatic_blinker_intent(
    intent, LaneChangeState.off, LaneChangeDirection.none, BLINKER_NONE, BLINKER_NONE,
  ) == BLINKER_NONE


def test_driver_blinker_cancels_automatic_blinker_intent():
  assert update_automatic_blinker_intent(
    BLINKER_RIGHT, LaneChangeState.preLaneChange, LaneChangeDirection.right, BLINKER_RIGHT, BLINKER_LEFT,
  ) == BLINKER_NONE


def test_automatic_blinker_must_match_lane_change_direction():
  assert update_automatic_blinker_intent(
    BLINKER_NONE, LaneChangeState.preLaneChange, LaneChangeDirection.left, BLINKER_RIGHT, BLINKER_NONE,
  ) == BLINKER_NONE


def test_latched_intent_clears_if_lane_change_direction_changes():
  assert update_automatic_blinker_intent(
    BLINKER_LEFT, LaneChangeState.laneChangeStarting, LaneChangeDirection.right, BLINKER_NONE, BLINKER_NONE,
  ) == BLINKER_NONE
