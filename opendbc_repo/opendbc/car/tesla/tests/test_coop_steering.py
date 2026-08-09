import pytest

from opendbc.car.tesla.coop_steering import (
  STEER_OVERRIDE_DELTA_GAIN_LIMIT,
  STEER_OVERRIDE_MIN_TORQUE,
  CoopSteeringCarController,
  apply_deadzone,
  calc_override_angle_delta_limit,
)


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
