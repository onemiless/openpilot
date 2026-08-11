from types import SimpleNamespace

import pytest

from opendbc.car.tesla.carcontroller import CarController
from opendbc.car.tesla.carstate import classify_steering_input
from opendbc.car.tesla.coop_steering import (
  STEER_OVERRIDE_DELTA_GAIN_LIMIT,
  STEER_OVERRIDE_MIN_TORQUE,
  CoopSteeringCarController,
  apply_deadzone,
  calc_override_angle_delta_limit,
)
from opendbc.car.tesla.interface import CarInterface
from opendbc.car.tesla.values import STEER_THRESHOLD
from opendbc.car.vehicle_model import VehicleModel


def test_strong_driver_input_always_disengages():
  assert classify_steering_input(3, 2.5, "EAC_ACTIVE", 0, False) == (False, True)
  assert classify_steering_input(3, 2.5, "EAC_ACTIVE", 0, True) == (False, True)
  assert classify_steering_input(0, 5.01, "EAC_ACTIVE", 0, True) == (False, True)


def test_driver_steering_threshold_matches_dev_new():
  assert STEER_THRESHOLD == 1.0


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


def test_controller_keeps_planner_and_cooperative_output_angle_state_separate():
  controller = CarController.__new__(CarController)
  controller.planner_apply_angle_last = 0.0
  controller.apply_angle_last = 0.0
  controller.coop_steering = CoopSteeringCarController()
  controller.coop_steering_enabled = True
  controller.VM = VehicleModel(CarInterface.get_non_essential_params("TESLA_MODEL_Y"))
  CS = SimpleNamespace(out=SimpleNamespace(vEgo=10.0, vEgoRaw=10.0, steeringTorque=1.5, steeringAngleDeg=0.0))

  for _ in range(50):
    output_angle, lat_active = controller.update_steering_control(0.0, True, CS)
  assert lat_active
  assert abs(output_angle) < 30.0
  assert controller.planner_apply_angle_last == pytest.approx(0.0)

  CS.out.steeringTorque = 0.0
  for _ in range(50):
    output_angle, lat_active = controller.update_steering_control(0.0, True, CS)
  assert lat_active
  assert abs(output_angle) < 1.0
