import pytest

from opendbc.car import apply_steer_angle_limits_vm, structs
from opendbc.car.tesla.values import CarControllerParams
from opendbc.car.vehicle_model import VehicleModel


def model_y_params():
  cp = structs.CarParams()
  cp.mass = 2072.0
  cp.wheelbase = 2.89
  cp.centerToFront = cp.wheelbase * 0.5
  cp.steerRatio = 12.0
  cp.steerRatioRear = 0.0
  cp.rotationalInertia = 2500.0
  cp.tireStiffnessFront = 192150.0
  cp.tireStiffnessRear = 202500.0
  return cp


def test_model_y_uses_official_ratio_and_low_speed_angle_rate():
  cp = model_y_params()
  vm = VehicleModel(cp)

  assert cp.steerRatio == 12.0
  assert CarControllerParams.ANGLE_LIMITS.STEER_ANGLE_MAX == 360
  assert CarControllerParams.ANGLE_LIMITS.MAX_ANGLE_RATE == 5
  assert apply_steer_angle_limits_vm(100.0, 0.0, 1.0, 0.0, True, CarControllerParams, vm) == pytest.approx(5.0)


def test_model_y_angle_limit_returns_to_measured_angle_when_inactive():
  vm = VehicleModel(model_y_params())
  result = apply_steer_angle_limits_vm(100.0, 20.0, 5.0, -12.0, False, CarControllerParams, vm)
  assert result == pytest.approx(-12.0)
