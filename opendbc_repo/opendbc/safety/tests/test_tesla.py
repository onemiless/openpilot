#!/usr/bin/env python3
import unittest

from opendbc.car.tesla.values import TeslaSafetyFlags
from opendbc.car.structs import CarParams
from opendbc.can import CANDefine
from opendbc.safety import ALTERNATIVE_EXPERIENCE
from opendbc.safety.tests.libsafety import libsafety_py
import opendbc.safety.tests.common as common
from opendbc.safety.tests.common import CANPackerPanda

MSG_DAS_steeringControl = 0x488
MSG_APS_eacMonitor = 0x27d
MSG_DAS_Control = 0x2b9
MSG_ARS408_CONFIG = 0x200
MSG_ARS408_FILTER_CONFIG = 0x202
MSG_ARS408_SPEED = 0x300
MSG_ARS408_YAW_RATE = 0x301


class TestTeslaSafetyBase(common.PandaCarSafetyTest, common.AngleSteeringSafetyTest, common.LongitudinalAccelSafetyTest):
  RELAY_MALFUNCTION_ADDRS = {0: (MSG_DAS_steeringControl, MSG_APS_eacMonitor)}
  FWD_BLACKLISTED_ADDRS = {2: [MSG_DAS_steeringControl, MSG_APS_eacMonitor]}
  TX_MSGS = [[MSG_DAS_steeringControl, 0], [MSG_APS_eacMonitor, 0], [MSG_DAS_Control, 0],
             [MSG_ARS408_CONFIG, 1], [MSG_ARS408_FILTER_CONFIG, 1],
             [MSG_ARS408_SPEED, 1], [MSG_ARS408_YAW_RATE, 1]]

  STANDSTILL_THRESHOLD = 0.1
  GAS_PRESSED_THRESHOLD = 3

  # Angle control limits
  STEER_ANGLE_MAX = 360  # deg
  DEG_TO_CAN = 10

  ANGLE_RATE_BP = [0., 5., 25.]
  ANGLE_RATE_UP = [2.5, 1.5, 0.2]  # windup limit
  ANGLE_RATE_DOWN = [5., 2.0, 0.3]  # unwind limit

  # Long control limits
  MAX_ACCEL = 2.0
  MIN_ACCEL = -3.48
  INACTIVE_ACCEL = 0.0

  packer: CANPackerPanda

  @classmethod
  def setUpClass(cls):
    if cls.__name__ == "TestTeslaSafetyBase":
      raise unittest.SkipTest

  def setUp(self):
    self.packer = CANPackerPanda("tesla_model3_party")
    self.define = CANDefine("tesla_model3_party")
    self.acc_states = {d: v for v, d in self.define.dv["DAS_control"]["DAS_accState"].items()}

  def _angle_cmd_msg(self, angle: float, enabled: bool):
    values = {"DAS_steeringAngleRequest": angle, "DAS_steeringControlType": 1 if enabled else 0}
    return self.packer.make_can_msg_panda("DAS_steeringControl", 0, values)

  def _angle_meas_msg(self, angle: float):
    return self._steering_status_msg(angle=angle)

  def _steering_status_msg(self, angle=0.0, torque=0.0, hands_on_level=0, eac_status=2, eac_error_code=0):
    values = {
      "EPAS3S_internalSAS": angle,
      "EPAS3S_torsionBarTorque": torque,
      "EPAS3S_handsOnLevel": hands_on_level,
      "EPAS3S_eacStatus": eac_status,
      "EPAS3S_eacErrorCode": eac_error_code,
    }
    return self.packer.make_can_msg_panda("EPAS3S_sysStatus", 0, values)

  def _user_brake_msg(self, brake):
    values = {"IBST_driverBrakeApply": 2 if brake else 1}
    return self.packer.make_can_msg_panda("IBST_status", 0, values)

  def _speed_msg(self, speed):
    values = {"DI_vehicleSpeed": speed * 3.6}
    return self.packer.make_can_msg_panda("DI_speed", 0, values)

  def _vehicle_moving_msg(self, speed: float):
    values = {"DI_cruiseState": 3 if speed <= self.STANDSTILL_THRESHOLD else 2}
    return self.packer.make_can_msg_panda("DI_state", 0, values)

  def _user_gas_msg(self, gas):
    values = {"DI_accelPedalPos": gas}
    return self.packer.make_can_msg_panda("DI_systemStatus", 0, values)

  def _pcm_status_msg(self, enable):
    values = {"DI_cruiseState": 2 if enable else 0}
    return self.packer.make_can_msg_panda("DI_state", 0, values)

  def _pcm_standby_msg(self):
    return self.packer.make_can_msg_panda("DI_state", 0, {"DI_cruiseState": 1})

  def _long_control_msg(self, set_speed, acc_state=0, jerk_limits=(0, 0), accel_limits=(0, 0), aeb_event=0, bus=0):
    values = {
      "DAS_setSpeed": set_speed,
      "DAS_accState": acc_state,
      "DAS_aebEvent": aeb_event,
      "DAS_jerkMin": jerk_limits[0],
      "DAS_jerkMax": jerk_limits[1],
      "DAS_accelMin": accel_limits[0],
      "DAS_accelMax": accel_limits[1],
    }
    return self.packer.make_can_msg_panda("DAS_control", bus, values)

  def _accel_msg(self, accel: float):
    # For common.LongitudinalAccelSafetyTest
    return self._long_control_msg(10, accel_limits=(accel, max(accel, 0)))

  def test_vehicle_speed_measurements(self):
    # OVERRIDDEN: 79.1667 is the max speed in m/s
    self._common_measurement_test(self._speed_msg, 0, 285 / 3.6, 1,
                                  self.safety.get_vehicle_speed_min, self.safety.get_vehicle_speed_max)

  def test_ars408_config_is_limited_to_vehicle_bus_and_eight_bytes(self):
    self.assertTrue(self._tx(common.make_msg(1, MSG_ARS408_CONFIG, 8)))
    self.assertFalse(self._tx(common.make_msg(0, MSG_ARS408_CONFIG, 8)))
    self.assertFalse(self._tx(common.make_msg(1, MSG_ARS408_CONFIG, 7)))

  def test_ars408_filter_config_is_limited_to_vehicle_bus_and_five_bytes(self):
    self.assertTrue(self._tx(common.make_msg(1, MSG_ARS408_FILTER_CONFIG, 5)))
    self.assertFalse(self._tx(common.make_msg(0, MSG_ARS408_FILTER_CONFIG, 5)))
    self.assertFalse(self._tx(common.make_msg(1, MSG_ARS408_FILTER_CONFIG, 8)))

  def test_ars408_motion_inputs_are_limited_to_dedicated_radar_bus_and_two_bytes(self):
    for address in (MSG_ARS408_SPEED, MSG_ARS408_YAW_RATE):
      self.assertTrue(self._tx(common.make_msg(1, address, 2)))
      self.assertFalse(self._tx(common.make_msg(0, address, 2)))
      self.assertFalse(self._tx(common.make_msg(2, address, 2)))
      self.assertFalse(self._tx(common.make_msg(1, address, 8)))

  def _engage_mads(self, brake_mode=0, cooperative_steering=False):
    alternative_experience = ALTERNATIVE_EXPERIENCE.ENABLE_MADS | brake_mode
    if cooperative_steering:
      alternative_experience |= ALTERNATIVE_EXPERIENCE.MADS_COOPERATIVE_STEERING
    self.safety.set_alternative_experience(alternative_experience)
    self.safety.set_controls_allowed(True)
    self.assertTrue(self._rx(self._speed_msg(10)))
    self.assertTrue(self.safety.get_controls_allowed_lateral())

  def test_mads_retains_lateral_after_longitudinal_disengages(self):
    self._engage_mads()
    self.safety.set_controls_allowed(False)
    self.assertTrue(self._rx(self._speed_msg(10)))
    self.assertFalse(self.safety.get_controls_allowed())
    self.assertTrue(self.safety.get_controls_allowed_lateral())
    self.assertTrue(self._tx(self._angle_cmd_msg(0, True)))

  def test_mads_retains_lateral_in_standby_but_exits_when_cruise_main_is_off(self):
    self._engage_mads()
    self.assertTrue(self._rx(self._pcm_standby_msg()))
    self.assertFalse(self.safety.get_controls_allowed())
    self.assertTrue(self.safety.get_controls_allowed_lateral())
    self.assertTrue(self._rx(self._pcm_status_msg(False)))
    self.assertFalse(self.safety.get_controls_allowed_lateral())

  def test_mads_brake_modes(self):
    safety_param = self.safety.get_current_safety_param()
    for mode, resumes in ((ALTERNATIVE_EXPERIENCE.MADS_DISENGAGE_LATERAL_ON_BRAKE, False),
                          (ALTERNATIVE_EXPERIENCE.MADS_PAUSE_LATERAL_ON_BRAKE, True)):
      self.safety.set_safety_hooks(CarParams.SafetyModel.tesla, safety_param)
      self.safety.init_tests()
      self._engage_mads(mode)
      self.assertTrue(self._rx(self._user_brake_msg(True)))
      self.assertFalse(self.safety.get_controls_allowed_lateral())
      self.assertTrue(self._rx(self._user_brake_msg(False)))
      self.assertEqual(resumes, self.safety.get_controls_allowed_lateral())

  def test_mads_strong_driver_steering_disengages(self):
    safety_param = self.safety.get_current_safety_param()
    for msg in (self._steering_status_msg(torque=5.01),
                self._steering_status_msg(hands_on_level=3),
                self._steering_status_msg(eac_status=0, eac_error_code=9)):
      self.safety.set_safety_hooks(CarParams.SafetyModel.tesla, safety_param)
      self.safety.init_tests()
      self._engage_mads()
      self.assertTrue(self._rx(msg))
      self.assertFalse(self.safety.get_controls_allowed())
      self.assertFalse(self.safety.get_controls_allowed_lateral())
      self.assertFalse(self._tx(self._angle_cmd_msg(0, True)))

  def test_mads_cooperative_driver_override_pauses_and_recovers(self):
    safety_param = self.safety.get_current_safety_param()
    for msg in (self._steering_status_msg(torque=5.01),
                self._steering_status_msg(hands_on_level=3)):
      self.safety.set_safety_hooks(CarParams.SafetyModel.tesla, safety_param)
      self.safety.init_tests()
      self._engage_mads(cooperative_steering=True)

      self.assertTrue(self._rx(msg))
      self.assertTrue(self.safety.get_controls_allowed())
      self.assertTrue(self.safety.get_controls_allowed_lateral())
      self.assertFalse(self._tx(self._angle_cmd_msg(0, True)))
      self.assertTrue(self._tx(self._angle_cmd_msg(0, False)))

      for _ in range(24):
        self.assertTrue(self._rx(self._steering_status_msg()))
        self.assertFalse(self._tx(self._angle_cmd_msg(0, True)))

      self.assertTrue(self._rx(self._steering_status_msg()))
      self.assertTrue(self._tx(self._angle_cmd_msg(0, True)))

  def test_mads_cooperative_high_angle_rate_fault_still_disengages(self):
    self._engage_mads(cooperative_steering=True)
    self.assertTrue(self._rx(self._steering_status_msg(eac_status=0, eac_error_code=9)))
    self.assertFalse(self.safety.get_controls_allowed())
    self.assertFalse(self.safety.get_controls_allowed_lateral())
    self.assertFalse(self._tx(self._angle_cmd_msg(0, True)))

  def test_mads_heartbeat_mismatch_disengages(self):
    self._engage_mads()
    self.safety.set_heartbeat_engaged_mads(False)
    for _ in range(2):
      self.safety.run_mads_heartbeat_check()
      self.assertTrue(self.safety.get_controls_allowed_lateral())
    self.safety.run_mads_heartbeat_check()
    self.assertFalse(self.safety.get_controls_allowed_lateral())


class TestTeslaStockSafety(TestTeslaSafetyBase):

  LONGITUDINAL = False

  def setUp(self):
    super().setUp()
    self.safety = libsafety_py.libsafety
    self.safety.set_safety_hooks(CarParams.SafetyModel.tesla, 0)
    self.safety.init_tests()

  def test_cancel(self):
    for acc_state in range(16):
      self.safety.set_controls_allowed(True)
      should_tx = acc_state == self.acc_states["ACC_CANCEL_GENERIC_SILENT"]
      self.assertFalse(self._tx(self._long_control_msg(0, acc_state=acc_state, accel_limits=(self.MIN_ACCEL, self.MAX_ACCEL))))
      self.assertEqual(should_tx, self._tx(self._long_control_msg(0, acc_state=acc_state)))

  def test_no_aeb(self):
    for aeb_event in range(4):
      self.assertEqual(self._tx(self._long_control_msg(10, acc_state=self.acc_states["ACC_CANCEL_GENERIC_SILENT"], aeb_event=aeb_event)), aeb_event == 0)


class TestTeslaLongitudinalSafety(TestTeslaSafetyBase):
  RELAY_MALFUNCTION_ADDRS = {0: (MSG_DAS_steeringControl, MSG_APS_eacMonitor, MSG_DAS_Control)}
  FWD_BLACKLISTED_ADDRS = {2: [MSG_DAS_steeringControl, MSG_APS_eacMonitor, MSG_DAS_Control]}

  def setUp(self):
    super().setUp()
    self.safety = libsafety_py.libsafety
    self.safety.set_safety_hooks(CarParams.SafetyModel.tesla, TeslaSafetyFlags.LONG_CONTROL)
    self.safety.init_tests()

  def test_no_aeb(self):
    for aeb_event in range(4):
      self.assertEqual(self._tx(self._long_control_msg(10, aeb_event=aeb_event)), aeb_event == 0)

  def test_stock_aeb_passthrough(self):
    no_aeb_msg = self._long_control_msg(10, aeb_event=0)
    no_aeb_msg_cam = self._long_control_msg(10, aeb_event=0, bus=2)
    aeb_msg_cam = self._long_control_msg(10, aeb_event=1, bus=2)

    # stock system sends no AEB -> no forwarding, and OP is allowed to TX
    self.assertEqual(1, self._rx(no_aeb_msg_cam))
    self.assertEqual(-1, self.safety.safety_fwd_hook(2, no_aeb_msg_cam.addr))
    self.assertTrue(self._tx(no_aeb_msg))

    # stock system sends AEB -> forwarding, and OP is not allowed to TX
    self.assertEqual(1, self._rx(aeb_msg_cam))
    self.assertEqual(0, self.safety.safety_fwd_hook(2, aeb_msg_cam.addr))
    self.assertFalse(self._tx(no_aeb_msg))

  def test_prevent_reverse(self):
    # Note: Tesla can reverse while at a standstill if both accel_min and accel_max are negative.
    self.safety.set_controls_allowed(True)

    # accel_min and accel_max are positive
    self.assertTrue(self._tx(self._long_control_msg(set_speed=10, accel_limits=(1.1, 0.8))))
    self.assertTrue(self._tx(self._long_control_msg(set_speed=0, accel_limits=(1.1, 0.8))))

    # accel_min and accel_max are both zero
    self.assertTrue(self._tx(self._long_control_msg(set_speed=10, accel_limits=(0, 0))))
    self.assertTrue(self._tx(self._long_control_msg(set_speed=0, accel_limits=(0, 0))))

    # accel_min and accel_max have opposing signs
    self.assertTrue(self._tx(self._long_control_msg(set_speed=10, accel_limits=(-0.8, 1.3))))
    self.assertTrue(self._tx(self._long_control_msg(set_speed=0, accel_limits=(0.8, -1.3))))
    self.assertTrue(self._tx(self._long_control_msg(set_speed=0, accel_limits=(0, -1.3))))

    # accel_min and accel_max are negative
    self.assertFalse(self._tx(self._long_control_msg(set_speed=10, accel_limits=(-1.1, -0.6))))
    self.assertFalse(self._tx(self._long_control_msg(set_speed=0, accel_limits=(-0.6, -1.1))))
    self.assertFalse(self._tx(self._long_control_msg(set_speed=0, accel_limits=(-0.1, -0.1))))


if __name__ == "__main__":
  unittest.main()
