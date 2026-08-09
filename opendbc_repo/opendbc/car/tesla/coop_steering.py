import math
from collections import namedtuple
from dataclasses import replace

import numpy as np

from opendbc.car import DT_CTRL, apply_steer_angle_limits_vm, rate_limit
from opendbc.car.tesla.values import CarControllerParams
from opendbc.car.vehicle_model import VehicleModel


DT_LAT_CTRL = DT_CTRL * CarControllerParams.STEER_STEP
STEER_RESUME_RATE_LIMIT_RAMP_RATE = 300  # deg/s^2


class CoopSteeringCarControllerParams(CarControllerParams):
  ANGLE_LIMITS = replace(CarControllerParams.ANGLE_LIMITS, MAX_ANGLE_RATE=5)


STEER_OVERRIDE_MIN_TORQUE = 0.5
STEER_OVERRIDE_MAX_TORQUE = 2.5
STEER_OVERRIDE_TORQUE_RANGE = STEER_OVERRIDE_MAX_TORQUE - STEER_OVERRIDE_MIN_TORQUE
STEER_OVERRIDE_STANDSTILL_VEGO = 0.1
STEER_OVERRIDE_MAX_LAT_ACCEL = 2.0
STEER_OVERRIDE_TARGET_ANGLE_MAX = CarControllerParams.ANGLE_LIMITS.STEER_ANGLE_MAX
STEER_OVERRIDE_DELTA_GAIN_LIMIT = 125
STEER_OVERRIDE_DELTA_GAIN_LIMIT_CENTERING = CoopSteeringCarControllerParams.ANGLE_LIMITS.MAX_ANGLE_RATE / DT_LAT_CTRL / STEER_OVERRIDE_TORQUE_RANGE


CoopSteeringData = namedtuple("CoopSteeringData", ["steeringAngleDeg", "lat_active"])


def get_steer_from_lat_accel(lat_accel: float, v_ego: float, VM: VehicleModel) -> float:
  curvature = lat_accel / (max(1.0, v_ego) ** 2)
  return math.degrees(VM.get_steer_from_curvature(curvature, v_ego, 0))


def apply_bounds(signal: float, limit: float) -> float:
  return float(np.clip(signal, -limit, limit))


def apply_deadzone(signal: float, deadzone: float) -> float:
  return signal - apply_bounds(signal, deadzone)


def get_override_torque_to_angle(v_ego: float, VM: VehicleModel, lat_accel: float) -> float:
  steer_from_lat_accel = apply_bounds(get_steer_from_lat_accel(lat_accel, v_ego, VM), STEER_OVERRIDE_TARGET_ANGLE_MAX)
  return steer_from_lat_accel / STEER_OVERRIDE_TORQUE_RANGE


def calc_override_angle_delta_limit(torque: float, gain_limit: float) -> float:
  max_gain = CoopSteeringCarControllerParams.ANGLE_LIMITS.MAX_ANGLE_RATE / DT_LAT_CTRL / STEER_OVERRIDE_TORQUE_RANGE
  return torque * min(gain_limit, max_gain) * DT_LAT_CTRL


class SteerRateLimiter:
  def __init__(self):
    self._last = 0.0

  def reset(self, angle: float) -> None:
    self._last = angle

  def update(self, angle: float, angle_delta_lim: float) -> float:
    limited = rate_limit(angle, self._last, -angle_delta_lim, angle_delta_lim)
    self._last = limited
    return limited


class CoopSteeringCarController:
  def __init__(self):
    self.apply_angle_last = 0.0
    self.coop_apply_angle_sat_last = 0.0
    self.angle_override = 0.0
    self.resume_rate_limiter_delta = SteerRateLimiter()
    self.resume_rate_limiter = SteerRateLimiter()

  def reset_override_state(self, apply_angle: float) -> None:
    self.apply_angle_last = apply_angle
    self.angle_override = 0.0
    self.coop_apply_angle_sat_last = apply_angle

  def compute_override_targets(self, v_ego: float, steering_torque: float, VM: VehicleModel) -> tuple[float, float]:
    torque_to_angle = get_override_torque_to_angle(v_ego, VM, STEER_OVERRIDE_MAX_LAT_ACCEL)
    torque_with_deadzone = apply_deadzone(steering_torque, STEER_OVERRIDE_MIN_TORQUE)
    neutral_torque = 0.0 if abs(v_ego) <= STEER_OVERRIDE_STANDSTILL_VEGO else self.angle_override / torque_to_angle
    return torque_with_deadzone * torque_to_angle, torque_with_deadzone - neutral_torque

  def override_slew_step(self, angle_override_target: float, override_torque: float) -> float:
    target_error = angle_override_target - self.angle_override
    slew_away = calc_override_angle_delta_limit(abs(override_torque), STEER_OVERRIDE_DELTA_GAIN_LIMIT)
    slew_center = calc_override_angle_delta_limit(abs(override_torque), STEER_OVERRIDE_DELTA_GAIN_LIMIT_CENTERING)
    down_step = slew_center if self.angle_override > 0 else slew_away
    up_step = slew_center if self.angle_override < 0 else slew_away
    return float(np.clip(target_error, -down_step, up_step))

  @staticmethod
  def adjust_slew_for_planner(slew_step: float, apply_angle_step: float, override_torque: float) -> float:
    direction = slew_step * apply_angle_step
    if direction > 0:
      return slew_step - apply_bounds(apply_angle_step, abs(slew_step))
    if direction < 0:
      driver_effort = abs(override_torque) / STEER_OVERRIDE_TORQUE_RANGE
      return slew_step - driver_effort * apply_angle_step
    return slew_step

  @staticmethod
  def unwind_on_saturation(angle_override: float, sat_error: float) -> float:
    if angle_override * sat_error <= 0:
      return angle_override
    return angle_override - apply_bounds(sat_error, abs(angle_override))

  def resume_steer_desired_rate_limit(self, lat_active: bool, apply_angle: float) -> float:
    if not lat_active:
      self.resume_rate_limiter_delta.reset(0.0)
      self.resume_rate_limiter.reset(apply_angle)
      return apply_angle

    angle_rate_delta_lim = self.resume_rate_limiter_delta.update(
      CarControllerParams.ANGLE_LIMITS.MAX_ANGLE_RATE,
      STEER_RESUME_RATE_LIMIT_RAMP_RATE * DT_LAT_CTRL ** 2,
    )
    return self.resume_rate_limiter.update(apply_angle, angle_rate_delta_lim)

  def update(self, apply_angle: float, lat_active: bool, enabled: bool, CS, VM: VehicleModel) -> CoopSteeringData:
    apply_angle = self.resume_steer_desired_rate_limit(lat_active, apply_angle)

    if not lat_active or not enabled:
      self.reset_override_state(apply_angle)
      return CoopSteeringData(apply_angle, lat_active)

    apply_angle_step = apply_angle - self.apply_angle_last
    self.apply_angle_last = apply_angle

    angle_override_target, override_torque = self.compute_override_targets(CS.out.vEgo, CS.out.steeringTorque, VM)
    slew_step = self.override_slew_step(angle_override_target, override_torque)
    self.angle_override += self.adjust_slew_for_planner(slew_step, apply_angle_step, override_torque)
    apply_angle += self.angle_override

    self.coop_apply_angle_sat_last = apply_steer_angle_limits_vm(
      apply_angle, self.coop_apply_angle_sat_last, CS.out.vEgoRaw,
      CS.out.steeringAngleDeg, lat_active, CoopSteeringCarControllerParams, VM,
    )
    sat_error = apply_angle - self.coop_apply_angle_sat_last
    self.angle_override = self.unwind_on_saturation(self.angle_override, sat_error)
    return CoopSteeringData(self.coop_apply_angle_sat_last, lat_active)
