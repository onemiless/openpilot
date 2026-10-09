import pytest
from openpilot.cereal import log
from openpilot.sunnypilot.selfdrive.controls.lib.tests.test_nav_lane_intent_desire import car_state, helper, intent


@pytest.mark.parametrize('side', ['left', 'right'])
@pytest.mark.parametrize('delay_ticks', [0, 1, 5, 25])
def test_withdrawal_before_observed_lamp_cannot_start_a_manual_change(side, delay_ticks):
  dh = helper()
  waiting = intent(direction=side, ready=False)
  dh.update(car_state(), True, 1.0, nav_lane_intent=waiting)
  dh.update(car_state(), True, 1.0, nav_lane_intent=waiting)
  assert dh.lane_change_state == log.LaneChangeState.preLaneChange
  stopped = intent(direction='none', signal=False, ready=False)
  for _ in range(delay_ticks):
    dh.update(car_state(), True, 1.0, nav_lane_intent=stopped)
  for _ in range(10):
    dh.update(car_state(**{side + 'Blinker': True}), True, 1.0, nav_lane_intent=stopped)
    assert dh.lane_change_state == log.LaneChangeState.off
    assert dh.desire == log.Desire.none


@pytest.mark.parametrize('side', ['left', 'right'])
def test_after_late_lamp_off_a_new_driver_signal_uses_original_behavior(side):
  dh = helper()
  waiting = intent(direction=side, ready=False)
  dh.update(car_state(), True, 1.0, nav_lane_intent=waiting)
  dh.update(car_state(), True, 1.0, nav_lane_intent=waiting)
  dh.update(car_state(), True, 1.0)
  for _ in range(5):
    dh.update(car_state(**{side + 'Blinker': True}), True, 1.0)
  assert dh.lane_change_state == log.LaneChangeState.off
  dh.update(car_state(), True, 1.0)
  for _ in range(5):
    dh.update(car_state(**{side + 'Blinker': True}), True, 1.0)
  assert dh.lane_change_state == log.LaneChangeState.laneChangeStarting


@pytest.mark.parametrize('side', ['left', 'right'])
def test_no_lamp_feedback_expires_instead_of_permanently_blocking_driver(side):
  dh = helper()
  dh.update(car_state(), True, 1.0, nav_lane_intent=intent(direction=side, ready=False))
  for _ in range(60):
    dh.update(car_state(), True, 1.0)
  for _ in range(5):
    dh.update(car_state(**{side + 'Blinker': True}), True, 1.0)
  assert dh.lane_change_state == log.LaneChangeState.laneChangeStarting


@pytest.mark.parametrize('side', ['left', 'right'])
def test_new_qualified_request_takes_over_but_still_requires_ready(side):
  dh = helper()
  crossing = {side + '_crossing_allowed': True}
  waiting = intent(direction=side, ready=False)
  dh.update(car_state(), True, 1.0, nav_lane_intent=waiting, **crossing)
  dh.update(car_state(), True, 1.0)
  for _ in range(5):
    dh.update(car_state(**{side + 'Blinker': True}), True, 1.0, nav_lane_intent=waiting, **crossing)
  assert dh.lane_change_state == log.LaneChangeState.preLaneChange
  ready = intent(direction=side, ready=True)
  dh.update(car_state(**{side + 'Blinker': True}), True, 1.0, nav_lane_intent=ready, **crossing)
  assert dh.lane_change_state == log.LaneChangeState.laneChangeStarting


@pytest.mark.parametrize('side', ['left', 'right'])
def test_late_lane_lamp_cannot_become_a_low_speed_turn(side):
  dh = helper()
  dh.lane_turn_controller.enabled = True
  dh.lane_turn_controller.lane_turn_value = 20.0
  dh.update(car_state(vEgo=5.0), True, 1.0, nav_lane_intent=intent(direction=side, ready=False))
  dh.update(car_state(vEgo=5.0), True, 1.0)
  for _ in range(10):
    dh.update(car_state(vEgo=5.0, **{side + 'Blinker': True}), True, 1.0)
    assert dh.desire == log.Desire.none


@pytest.mark.parametrize('side', ['left', 'right'])
def test_pending_lamp_does_not_suppress_opposite_driver_signal(side):
  dh = helper()
  other = 'right' if side == 'left' else 'left'
  dh.update(car_state(), True, 1.0, nav_lane_intent=intent(direction=side, ready=False))
  dh.update(car_state(), True, 1.0)
  for _ in range(5):
    dh.update(car_state(**{other + 'Blinker': True}), True, 1.0)
  assert dh.lane_change_state == log.LaneChangeState.laneChangeStarting
  assert dh.lane_change_direction == getattr(log.LaneChangeDirection, other)
