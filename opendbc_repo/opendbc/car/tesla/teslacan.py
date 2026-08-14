from opendbc.car import DT_CTRL
from opendbc.car.common.conversions import Conversions as CV
from opendbc.car.tesla.values import CANBUS, CarControllerParams

TESLA_LONGITUDINAL_HANDOFF_AEB_EVENT = 3


class TeslaCAN:
  def __init__(self, packer):
    self.packer = packer
    self.jerk = 0.0

  def reset_longitudinal_jerk(self):
    self.jerk = 0.0

  @staticmethod
  def checksum(msg_id, dat):
    ret = (msg_id & 0xFF) + ((msg_id >> 8) & 0xFF)
    ret += sum(dat)
    return ret & 0xFF

  def create_steering_control(self, angle, enabled, counter):
    values = {
      "DAS_steeringAngleRequest": -angle,
      "DAS_steeringHapticRequest": 0,
      "DAS_steeringControlType": 1 if enabled else 0,
      "DAS_steeringControlCounter": counter,
    }

    data = self.packer.make_can_msg("DAS_steeringControl", CANBUS.party, values)[1]
    values["DAS_steeringControlChecksum"] = self.checksum(0x488, data[:3])
    return self.packer.make_can_msg("DAS_steeringControl", CANBUS.party, values)

  def create_longitudinal_command(self, acc_state, accel, cntr, v_ego, active):
    # Report a continuous, physically plausible speed instead of switching
    # between 0 and the global cruise maximum whenever accel changes sign.
    set_speed = min(max(v_ego + accel, 0) * CV.MS_TO_KPH, 400)
    if active:
      # DAS_control is emitted at 25 Hz. Ramp the positive jerk envelope at the
      # same 1 m/s^3/s rate as the known-good SP Tesla controller.
      self.jerk = min(self.jerk + CarControllerParams.JERK_RATE_UP * DT_CTRL * 4,
                      CarControllerParams.JERK_LIMIT_MAX)

    values = {
      "DAS_setSpeed": set_speed,
      "DAS_accState": acc_state,
      "DAS_aebEvent": 0,
      "DAS_jerkMin": CarControllerParams.JERK_LIMIT_MIN,
      "DAS_jerkMax": self.jerk,
      "DAS_accelMin": accel,
      "DAS_accelMax": max(accel, 0),
      "DAS_controlCounter": cntr,
      "DAS_controlChecksum": 0,
    }
    data = self.packer.make_can_msg("DAS_control", CANBUS.party, values)[1]
    values["DAS_controlChecksum"] = self.checksum(0x2b9, data[:7])
    return self.packer.make_can_msg("DAS_control", CANBUS.party, values)

  def create_stock_longitudinal_handoff(self, das_control, counter):
    """Build a Panda-consumed ownership marker that never reaches the vehicle."""
    values = {
      "DAS_setSpeed": das_control["DAS_setSpeed"],
      "DAS_accState": das_control["DAS_accState"],
      "DAS_aebEvent": TESLA_LONGITUDINAL_HANDOFF_AEB_EVENT,
      "DAS_jerkMin": das_control["DAS_jerkMin"],
      "DAS_jerkMax": das_control["DAS_jerkMax"],
      "DAS_accelMin": das_control["DAS_accelMin"],
      "DAS_accelMax": das_control["DAS_accelMax"],
      "DAS_controlCounter": counter,
      "DAS_controlChecksum": 0,
    }
    data = self.packer.make_can_msg("DAS_control", CANBUS.party, values)[1]
    values["DAS_controlChecksum"] = self.checksum(0x2b9, data[:7])
    return self.packer.make_can_msg("DAS_control", CANBUS.party, values)

  def create_steering_allowed(self, counter):
    values = {
      "APS_eacAllow": 1,
      "APS_eacMonitorCounter": counter,
    }

    data = self.packer.make_can_msg("APS_eacMonitor", CANBUS.party, values)[1]
    values["APS_eacMonitorChecksum"] = self.checksum(0x27d, data[:2])
    return self.packer.make_can_msg("APS_eacMonitor", CANBUS.party, values)


def tesla_checksum(address: int, sig, d: bytearray) -> int:
  checksum = (address & 0xFF) + ((address >> 8) & 0xFF)
  checksum_byte = sig.start_bit // 8
  for i in range(len(d)):
    if i != checksum_byte:
      checksum += d[i]
  return checksum & 0xFF
