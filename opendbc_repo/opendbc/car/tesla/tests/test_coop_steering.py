import pytest

from opendbc.car.tesla.carstate import classify_steering_input
from opendbc.car.tesla.coop_steering import (
  STEER_OVERRIDE_DELTA_GAIN_LIMIT,
  STEER_OVERRIDE_MIN_TORQUE,
  CoopSteeringCarController,
  apply_deadzone,
  calc_override_angle_delta_limit,
)


def test_strong_driver_input_is_recoverable_only_in_cooperative_mode():
  assert classify_steering_input(3, 2.5, "EAC_ACTIVE", 0, False) == (False, True)
  assert classify_steering_input(3, 2.5, "EAC_ACTIVE", 0, True) == (True, False)
  assert classify_steering_input(0, 5.01, "EAC_ACTIVE", 0, True) == (True, False)


def test_high_angle_rate_fault_is_never_recoverable():
  assert classify_steering_input(3, 5.01, "EAC_INHIBITED", 9, True) == (False, True)


def test_driver_torque_deadzone_is_symmetric():
  assert apply_deadzone(0.4, STEER_OVERRIDE_MIN_TORQUE) == 0
  assert apply_deadzone(-0.4, STEER_OVERRIDE_MIN_TORQUE) == 0
  assert apply_deadzone(1.0, STEER_OVERRIDE_MIN_TORQUE) == pytest.approx(0.5)
  assert apply_deadzone(-1.0, STEER_OVERRIDE_MIN_TORQUE) == pytest.approx(-0.5)


def test_override_slew_is_bounded_and_tracks_driver_direction():
  controller = CoopSteeringCarController()
  positive_step = controller.override_slew_step(50, 1.0)
  negative_step = controller.override_slew_step(-50, -1.0)
  bound = calc_override_angle_delta_limit(1.0, STEER_OVERRIDE_DELTA_GAIN_LIMIT)
  assert positive_step == pytest.approx(bound)
  assert negative_step == pytest.approx(-bound)


def test_planner_motion_does_not_double_count_driver_override():
  slew = 1.0
  assert CoopSteeringCarController.adjust_slew_for_planner(slew, 0.4, 1.0) == pytest.approx(0.6)
  assert CoopSteeringCarController.adjust_slew_for_planner(slew, -0.4, 1.0) > slew


def test_saturation_unwinds_only_in_saturated_direction():
  assert CoopSteeringCarController.unwind_on_saturation(5.0, 2.0) == pytest.approx(3.0)
  assert CoopSteeringCarController.unwind_on_saturation(-5.0, -2.0) == pytest.approx(-3.0)
  assert CoopSteeringCarController.unwind_on_saturation(5.0, -2.0) == pytest.approx(5.0)


def test_diagnostic_state_resets_when_cooperative_steering_is_inactive():
  controller = CoopSteeringCarController()
  controller.driver_override_active = True
  controller.angle_saturated = True
  controller.update(12.0, False, True, None, None)
  assert not controller.driver_override_active
  assert not controller.angle_saturated
