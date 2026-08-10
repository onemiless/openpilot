import logging
import math

import numpy as np
from opendbc.can import CANPacker
from opendbc.car import Bus, apply_steer_angle_limits_vm, structs
from opendbc.car.interfaces import CarControllerBase
from opendbc.car.tesla.ars408_can import ARS408CAN, ARS408_MOTION_INPUT_ENABLED, should_configure_radar
from opendbc.car.tesla.coop_steering import CoopSteeringCarController
from opendbc.car.tesla.teslacan import TeslaCAN
from opendbc.car.tesla.values import CarControllerParams
from opendbc.car.vehicle_model import VehicleModel
from openpilot.common.params import Params


log = logging.getLogger(__name__)


class CarController(CarControllerBase):
  def __init__(self, dbc_names, CP):
    super().__init__(dbc_names, CP)
    self.apply_angle_last = 0
    self.packer = CANPacker(dbc_names[Bus.party])
    self.tesla_can = TeslaCAN(self.packer)
    self.ars408_can = None if CP.radarUnavailable else ARS408CAN()
    self.params = Params()
    self.VM = VehicleModel(CP)
    self.coop_steering = CoopSteeringCarController()
    self.coop_steering_enabled = self.params.get_bool("TeslaCoopSteering")
    self.radar_motion_enabled = self.params.get_bool("TeslaRadarMotionInput")
    self._radar_motion_valid_prev = None
    self._coop_override_prev = False
    self._coop_saturated_prev = False
    self._steering_disengage_prev = False
    log.info("Tesla cooperative steering configured enabled=%d", int(self.coop_steering_enabled))
    log.info("ARS408 motion input configured enabled=%d bus=1 rate_hz=20", int(self.radar_motion_enabled))

  def send_radar_motion(self, CS):
    """Return reviewed ARS408 motion frames when the physical CAN path is safe."""
    if self.ars408_can is None or not ARS408_MOTION_INPUT_ENABLED or not self.radar_motion_enabled:
      return []

    speed_mps = float(CS.out.vEgoRaw)
    yaw_rate_rad_s = float(CS.out.yawRate)
    motion_valid = bool(CS.out.canValid) and math.isfinite(speed_mps) and math.isfinite(yaw_rate_rad_s)
    if motion_valid != self._radar_motion_valid_prev:
      log.info("ARS408 motion source valid=%d speed=%.3f yaw_rate_rad_s=%.4f",
               int(motion_valid), speed_mps, yaw_rate_rad_s)
      self._radar_motion_valid_prev = motion_valid
    if not motion_valid:
      return []

    reverse = CS.out.gearShifter == structs.CarState.GearShifter.reverse
    standstill = CS.out.standstill or abs(speed_mps) < 0.05
    direction = 0 if standstill else (2 if reverse else 1)
    yaw_rate_deg_s = math.degrees(-yaw_rate_rad_s if reverse else yaw_rate_rad_s)
    return [
      self.ars408_can.create_speed_information(speed_mps, direction),
      self.ars408_can.create_yaw_rate_information(yaw_rate_deg_s),
    ]

  def update(self, CC, CS, now_nanos):
    actuators = CC.actuators
    can_sends = []

    # Configuration is stored in radar NVM. Never send it automatically;
    # TeslaRadarReinitialize is an explicit, one-shot request for a new setup.
    radar_reinitialize = self.params.get_bool("TeslaRadarReinitialize")
    if self.ars408_can is not None and should_configure_radar(self.frame, radar_reinitialize):
      can_sends.append(self.ars408_can.create_radar_configuration())
      can_sends.append(self.ars408_can.create_object_count_filter())
      if radar_reinitialize:
        self.params.remove("TeslaRadarReinitialize")
      log.info("ARS408 configuration sent on dedicated radar bus at frame %d reinitialize=%d",
               self.frame, int(radar_reinitialize))

    # The directly connected ARS408 has a dedicated, non-forwarded bus 1.
    if self.frame % 5 == 0:
      can_sends.extend(self.send_radar_motion(CS))

    # Disengage and allow for user override on high torque inputs
    # TODO: move this to a generic disengageRequested carState field and set CC.cruiseControl.cancel based on it
    steering_disengage = CS.out.steeringDisengage
    cruise_cancel = CC.cruiseControl.cancel or steering_disengage
    lat_active = CC.latActive and not steering_disengage
    if steering_disengage != self._steering_disengage_prev:
      log.warning("Tesla steering safety disengage=%d torque=%.2f hands_on_level=%d",
                  int(steering_disengage), CS.out.steeringTorque, CS.out.handsOnLevel)
      self._steering_disengage_prev = steering_disengage

    if self.frame % 2 == 0:
      # Angular rate limit based on speed
      self.apply_angle_last = apply_steer_angle_limits_vm(actuators.steeringAngleDeg, self.apply_angle_last, CS.out.vEgoRaw,
                                                          CS.out.steeringAngleDeg, lat_active, CarControllerParams, self.VM)

      coop_steering = self.coop_steering.update(self.apply_angle_last, lat_active, self.coop_steering_enabled, CS, self.VM)
      self.apply_angle_last = coop_steering.steeringAngleDeg
      lat_active = coop_steering.lat_active

      if self.coop_steering.driver_override_active != self._coop_override_prev:
        log.info("Tesla cooperative steering driver_override=%d torque=%.2f override_angle=%.2f output_angle=%.2f",
                 int(self.coop_steering.driver_override_active), CS.out.steeringTorque,
                 self.coop_steering.angle_override, self.apply_angle_last)
        self._coop_override_prev = self.coop_steering.driver_override_active
      if self.coop_steering.angle_saturated != self._coop_saturated_prev:
        log.info("Tesla cooperative steering saturated=%d torque=%.2f override_angle=%.2f output_angle=%.2f",
                 int(self.coop_steering.angle_saturated), CS.out.steeringTorque,
                 self.coop_steering.angle_override, self.apply_angle_last)
        self._coop_saturated_prev = self.coop_steering.angle_saturated

      can_sends.append(self.tesla_can.create_steering_control(self.apply_angle_last, lat_active, (self.frame // 2) % 16))

    if self.frame % 10 == 0:
      can_sends.append(self.tesla_can.create_steering_allowed((self.frame // 10) % 16))

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
