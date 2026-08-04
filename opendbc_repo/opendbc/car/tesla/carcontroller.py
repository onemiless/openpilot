import math

import numpy as np
from opendbc.can import CANPacker
from opendbc.car import Bus, apply_std_steer_angle_limits, structs
from opendbc.car.interfaces import CarControllerBase
from opendbc.car.tesla.teslacan import TeslaCAN
from opendbc.car.tesla.values import CANBUS, CarControllerParams


ARS408_BUS = CANBUS.vehicle
ARS408_SENSOR_OFFSET = 5 << 4
ARS408_MOTION_STEP = 5  # card runs at 100 Hz; radar motion inputs run at 20 Hz


def create_ars408_motion_messages(packer, CP, CS):
  speed = float(np.clip(abs(CS.out.vEgo), 0.0, 163.8))
  reverse = CS.out.gearShifter == structs.CarState.GearShifter.reverse
  direction = 0 if speed < 0.05 else (2 if reverse else 1)
  signed_speed = -speed if reverse else speed

  road_wheel_angle_deg = CS.out.steeringAngleDeg / CP.steerRatio
  yaw_rate = math.degrees(signed_speed * math.tan(math.radians(road_wheel_angle_deg)) / CP.wheelbase)
  yaw_rate = float(np.clip(yaw_rate, -327.68, 327.66))

  speed_msg = packer.make_can_msg("SpeedInformation", ARS408_BUS, {
    "RadarDevice_Speed": speed,
    "RadarDevice_SpeedDirection": direction,
  })
  yaw_msg = packer.make_can_msg("YawRateInformation", ARS408_BUS, {
    "RadarDevice_YawRate": yaw_rate,
  })
  return [(address + ARS408_SENSOR_OFFSET, data, bus) for address, data, bus in (speed_msg, yaw_msg)]


class CarController(CarControllerBase):
  def __init__(self, dbc_names, CP):
    super().__init__(dbc_names, CP)
    self.apply_angle_last = 0
    self.packer = CANPacker(dbc_names[Bus.party])
    self.radar_packer = CANPacker("ARS408")
    self.tesla_can = TeslaCAN(self.packer)

  def update(self, CC, CS, now_nanos):
    actuators = CC.actuators
    can_sends = []

    # Disengage and allow for user override on high torque inputs
    # TODO: move this to a generic disengageRequested carState field and set CC.cruiseControl.cancel based on it
    hands_on_fault = CS.hands_on_level >= 3
    cruise_cancel = CC.cruiseControl.cancel or hands_on_fault
    lat_active = CC.latActive and not hands_on_fault

    if self.frame % 2 == 0:
      # Angular rate limit based on speed
      self.apply_angle_last = apply_std_steer_angle_limits(actuators.steeringAngleDeg, self.apply_angle_last, CS.out.vEgo,
                                                           CS.out.steeringAngleDeg, CC.latActive, CarControllerParams.ANGLE_LIMITS)

      can_sends.append(self.tesla_can.create_steering_control(self.apply_angle_last, lat_active, (self.frame // 2) % 16))

    if self.frame % 10 == 0:
      can_sends.append(self.tesla_can.create_steering_allowed((self.frame // 10) % 16))

    if not self.CP.radarUnavailable and self.frame % ARS408_MOTION_STEP == 0:
      can_sends.extend(create_ars408_motion_messages(self.radar_packer, self.CP, CS))

    # Longitudinal control
    if self.CP.openpilotLongitudinalControl:
      if self.frame % 4 == 0:
        state = 13 if cruise_cancel else 4  # 4=ACC_ON, 13=ACC_CANCEL_GENERIC_SILENT
        accel = float(np.clip(actuators.accel, CarControllerParams.ACCEL_MIN, CarControllerParams.ACCEL_MAX))
        cntr = (self.frame // 4) % 8
        can_sends.append(self.tesla_can.create_longitudinal_command(state, accel, cntr, CS.out.vEgo, CC.longActive))

    else:
      # Increment counter so cancel is prioritized even without openpilot longitudinal
      if cruise_cancel:
        cntr = (CS.das_control["DAS_controlCounter"] + 1) % 8
        can_sends.append(self.tesla_can.create_longitudinal_command(13, 0, cntr, CS.out.vEgo, False))

    # TODO: HUD control
    new_actuators = actuators.as_builder()
    new_actuators.steeringAngleDeg = self.apply_angle_last

    self.frame += 1
    return new_actuators, can_sends
