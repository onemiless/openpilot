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
MSG_SPEED_SYNC = 0x3C2
MSG_TURN_SIGNAL = 0x3E9
MSG_UI_STATUS_2 = 0x3DF


class TestTeslaSafetyBase(common.PandaCarSafetyTest, common.AngleSteeringSafetyTest, common.LongitudinalAccelSafetyTest):
  RELAY_MALFUNCTION_ADDRS = {0: (MSG_DAS_steeringControl, MSG_APS_eacMonitor)}
  FWD_BLACKLISTED_ADDRS = {2: [MSG_DAS_steeringControl, MSG_APS_eacMonitor]}
  TX_MSGS = [[MSG_DAS_steeringControl, 0], [MSG_APS_eacMonitor, 0], [MSG_DAS_Control, 0],
             [MSG_ARS408_CONFIG, 1], [MSG_ARS408_FILTER_CONFIG, 1],
             [MSG_ARS408_SPEED, 1], [MSG_ARS408_YAW_RATE, 1],
             [MSG_SPEED_SYNC, 1], [MSG_TURN_SIGNAL, 1]]

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
    self.radar_packer = CANPackerPanda("ARS408")
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

  def _speed_sync_msg(self, tick, bus=1, template=None):
    msg = common.make_msg(bus, MSG_SPEED_SYNC, 8)
    if template is not None:
      for i in range(8):
        msg[0].data[i] = template[0].data[i]
    msg[0].data[0] = (msg[0].data[0] & 0xFC) | 1
    msg[0].data[3] = (msg[0].data[3] & 0xC0) | (tick & 0x3F)
    return msg

  def _turn_signal_msg(self, request, reason, counter, bus=1, template=None):
    msg = common.make_msg(bus, MSG_TURN_SIGNAL, 8)
    if template is not None:
      for i in range(8):
        msg[0].data[i] = template[0].data[i]
    msg[0].data[1] = (msg[0].data[1] & 0xFC) | request
    msg[0].data[2] = (msg[0].data[2] & 0xE1) | ((reason & 0xF) << 1)
    msg[0].data[6] = (msg[0].data[6] & 0x0F) | ((counter & 0xF) << 4)
    msg[0].data[7] = (0xE9 + 0x03 + sum(msg[0].data[i] for i in range(7))) & 0xFF
    return msg

  def _mads_touch_msg(self, points, bus=1, length=8):
    msg = common.make_msg(bus, MSG_UI_STATUS_2, length)
    if length > 3:
      msg[0].data[3] = points
    return msg

  def test_turn_signal_requires_flag_and_fresh_idle_template(self):
    template = self._turn_signal_msg(0, 0, 3)
    action = self._turn_signal_msg(1, 8, 4, template=template)
    self.assertTrue(self._rx(template))
    self.assertFalse(self._tx(action))

    self.safety.set_safety_hooks(CarParams.SafetyModel.tesla, TeslaSafetyFlags.TURN_SIGNAL_TEST)
    self.safety.init_tests()
    self.assertFalse(self._tx(action))
    self.assertTrue(self._rx(template))
    self.assertTrue(self._tx(action))
    self.assertFalse(self._tx(action))

  def test_turn_signal_rejects_direction_change_mutation_and_stale_template(self):
    self.safety.set_safety_hooks(CarParams.SafetyModel.tesla, TeslaSafetyFlags.TURN_SIGNAL_TEST)
    self.safety.init_tests()
    template = self._turn_signal_msg(0, 0, 7)
    self.assertTrue(self._rx(template))
    self.assertTrue(self._tx(self._turn_signal_msg(1, 8, 8, template=template)))

    next_template = self._turn_signal_msg(0, 0, 8)
    self.assertTrue(self._rx(next_template))
    self.assertFalse(self._tx(self._turn_signal_msg(2, 8, 9, template=next_template)))

    mutated = self._turn_signal_msg(1, 8, 9, template=next_template)
    mutated[0].data[4] ^= 1
    mutated[0].data[7] = (0xE9 + 0x03 + sum(mutated[0].data[i] for i in range(7))) & 0xFF
    self.assertFalse(self._tx(mutated))

    self.safety.set_timer(1_500_001)
    self.assertFalse(self._tx(self._turn_signal_msg(1, 8, 9, template=next_template)))

  def test_turn_signal_cancel_and_controls_allowed_are_supported(self):
    self.safety.set_safety_hooks(CarParams.SafetyModel.tesla, TeslaSafetyFlags.TURN_SIGNAL_TEST)
    self.safety.init_tests()
    template = self._turn_signal_msg(0, 0, 1)
    self.assertTrue(self._rx(template))
    self.safety.set_controls_allowed(True)
    self.assertTrue(self._tx(self._turn_signal_msg(2, 8, 2, template=template)))
    cancel_template = self._turn_signal_msg(0, 0, 2)
    self.assertTrue(self._rx(cancel_template))
    self.assertTrue(self._tx(self._turn_signal_msg(3, 4, 3, template=cancel_template)))

  def test_speed_sync_requires_flag_controls_and_valid_ticks(self):
    template = self._speed_sync_msg(0)
    self.assertTrue(self._rx(template))
    self.assertFalse(self._tx(self._speed_sync_msg(1, template=template)))

    self.safety.set_safety_hooks(CarParams.SafetyModel.tesla, TeslaSafetyFlags.SPEED_SYNC)
    self.safety.init_tests()
    self.assertTrue(self._rx(template))
    self.assertFalse(self._tx(self._speed_sync_msg(1, template=template)))
    self.safety.set_controls_allowed(True)
    self.assertTrue(self._tx(self._speed_sync_msg(1, template=template)))

    self.safety.set_timer(250_001)
    self.assertTrue(self._tx(self._speed_sync_msg(-1, template=template)))
    for index, invalid_tick in enumerate((0, 2, -2, 3, 31, -32), start=2):
      self.safety.set_timer(index * 250_001)
      self.assertFalse(self._tx(self._speed_sync_msg(invalid_tick, template=template)))

  def test_speed_sync_rejects_rate_mutation_and_stale_template(self):
    self.safety.set_safety_hooks(CarParams.SafetyModel.tesla, TeslaSafetyFlags.SPEED_SYNC)
    self.safety.init_tests()
    self.safety.set_controls_allowed(True)
    template = self._speed_sync_msg(0)
    template[0].data[4] = 0x55
    self.assertTrue(self._rx(template))
    self.assertTrue(self._tx(self._speed_sync_msg(1, template=template)))
    self.assertFalse(self._tx(self._speed_sync_msg(-1, template=template)))

    self.safety.set_timer(250_001)
    mutated = self._speed_sync_msg(-1, template=template)
    mutated[0].data[4] ^= 1
    self.assertFalse(self._tx(mutated))

    self.safety.set_timer(1_500_001)
    self.assertFalse(self._tx(self._speed_sync_msg(-1, template=template)))

  def _accel_msg(self, accel: float):
    # For common.LongitudinalAccelSafetyTest
    return self._long_control_msg(10, accel_limits=(accel, max(accel, 0)))

  def test_vehicle_speed_measurements(self):
    # OVERRIDDEN: 79.1667 is the max speed in m/s
    self._common_measurement_test(self._speed_msg, 0, 285 / 3.6, 1,
                                  self.safety.get_vehicle_speed_min, self.safety.get_vehicle_speed_max)

  def test_ars408_config_is_limited_to_vehicle_bus_and_eight_bytes(self):
    valid = self.radar_packer.make_can_msg_panda("RadarConfiguration", 1, {
      "RadarCfg_MaxDistance_valid": 1, "RadarCfg_MaxDistance": 250,
    })
    self.assertTrue(self._tx(valid))
    self.assertFalse(self._tx(common.make_msg(0, MSG_ARS408_CONFIG, 8, b"\x01\x1f\x40\x00\x00\x00\x00\x00")))
    self.assertFalse(self._tx(common.make_msg(1, MSG_ARS408_CONFIG, 7)))

  def test_ars408_filter_config_is_limited_to_vehicle_bus_and_five_bytes(self):
    valid = self.radar_packer.make_can_msg_panda("FilterCfg", 1, {
      "FilterCfg_Type": 1, "FilterCfg_Index": 1, "FilterCfg_Active": 1, "FilterCfg_Valid": 1,
      "FilterCfg_Min_Distance": 0, "FilterCfg_Max_Distance": 250,
    })
    self.assertTrue(self._tx(valid))
    self.assertFalse(self._tx(common.make_msg(0, MSG_ARS408_FILTER_CONFIG, 5, b"\x8e\x00\x00\x09\xc4")))
    self.assertFalse(self._tx(common.make_msg(1, MSG_ARS408_FILTER_CONFIG, 8)))

  def test_ars408_filter_query_is_read_only(self):
    query = self.radar_packer.make_can_msg_panda("FilterCfg", 1, {
      "FilterCfg_Type": 1, "FilterCfg_Index": 0, "FilterCfg_Active": 0, "FilterCfg_Valid": 0,
    })
    self.assertTrue(self._tx(query))

    query_with_payload = self.radar_packer.make_can_msg_panda("FilterCfg", 1, {
      "FilterCfg_Type": 1, "FilterCfg_Index": 0, "FilterCfg_Active": 0, "FilterCfg_Valid": 0,
      "FilterCfg_Max_NofObj": 48,
    })
    self.assertFalse(self._tx(query_with_payload))

  def test_ars408_config_rejects_unreviewed_fields_and_cluster_output(self):
    for values in (
      {"RadarCfg_SensorID_valid": 1, "RadarCfg_SensorID": 0},
      {"RadarCfg_SendQuality_valid": 1, "RadarCfg_SendQuality": 1},
      {"RadarCfg_OutputType_valid": 1, "RadarCfg_OutputType": 2},
      {"RadarCfg_MaxDistance_valid": 1, "RadarCfg_MaxDistance": 198},
    ):
      with self.subTest(values=values):
        msg = self.radar_packer.make_can_msg_panda("RadarConfiguration", 1, values)
        self.assertFalse(self._tx(msg))

  def test_ars408_filter_rejects_cluster_and_reserved_index(self):
    for filter_type, index in ((0, 1), (1, 15)):
      with self.subTest(filter_type=filter_type, index=index):
        msg = self.radar_packer.make_can_msg_panda("FilterCfg", 1, {
          "FilterCfg_Type": filter_type, "FilterCfg_Index": index,
          "FilterCfg_Active": 1, "FilterCfg_Valid": 1,
        })
        self.assertFalse(self._tx(msg))

  def test_ars408_motion_inputs_are_limited_to_gateway_bus_and_two_bytes(self):
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

  def test_mads_retains_lateral_when_cruise_main_is_standby_or_unavailable(self):
    self._engage_mads()
    self.assertTrue(self._rx(self._pcm_standby_msg()))
    self.assertFalse(self.safety.get_controls_allowed())
    self.assertTrue(self.safety.get_controls_allowed_lateral())
    self.assertTrue(self._rx(self._pcm_status_msg(False)))
    self.assertTrue(self.safety.get_controls_allowed_lateral())

  def test_three_finger_touch_requests_mads_without_acc_main_or_full_cp(self):
    self.safety.set_alternative_experience(ALTERNATIVE_EXPERIENCE.ENABLE_MADS)
    self.safety.set_heartbeat_engaged_mads(True)
    self.assertTrue(self._rx(self._pcm_status_msg(False)))
    self.assertFalse(self.safety.get_controls_allowed())
    self.assertFalse(self.safety.get_controls_allowed_lateral())

    self.assertTrue(self._rx(self._mads_touch_msg(3)))
    self.assertTrue(self.safety.get_controls_allowed_lateral())

    # Holding three fingers cannot create another request after a safety exit.
    self.assertTrue(self._rx(self._steering_status_msg(eac_status=3)))
    self.assertFalse(self.safety.get_controls_allowed_lateral())
    self.assertTrue(self._rx(self._mads_touch_msg(3)))
    self.assertFalse(self.safety.get_controls_allowed_lateral())

    self.assertTrue(self._rx(self._mads_touch_msg(0)))
    self.assertTrue(self._rx(self._steering_status_msg(eac_status=1)))
    self.assertTrue(self._rx(self._mads_touch_msg(3)))
    self.assertTrue(self.safety.get_controls_allowed_lateral())

  def test_three_finger_touch_cannot_reauthorize_during_persistent_steering_fault(self):
    self.safety.set_alternative_experience(ALTERNATIVE_EXPERIENCE.ENABLE_MADS)
    self.safety.set_heartbeat_engaged_mads(True)
    self.assertTrue(self._rx(self._pcm_status_msg(False)))
    self.assertTrue(self._rx(self._steering_status_msg(eac_status=3)))
    self.assertTrue(self._rx(self._mads_touch_msg(3)))
    self.assertFalse(self.safety.get_controls_allowed_lateral())
    self.assertFalse(self._tx(self._angle_cmd_msg(0, True)))

  def test_mads_touch_requires_exact_count_bus_and_length(self):
    safety_param = self.safety.get_current_safety_param()
    invalid_messages = [*(self._mads_touch_msg(points) for points in (1, 2, 4, 5)),
                        self._mads_touch_msg(3, bus=0), self._mads_touch_msg(3, length=7)]
    for msg in invalid_messages:
      self.safety.set_safety_hooks(CarParams.SafetyModel.tesla, safety_param)
      self.safety.init_tests()
      self.safety.set_alternative_experience(ALTERNATIVE_EXPERIENCE.ENABLE_MADS)
      self.assertTrue(self._rx(self._pcm_status_msg(False)))
      self.assertTrue(self._rx(msg))
      self.assertFalse(self.safety.get_controls_allowed_lateral())

  def test_touch_mads_heartbeat_is_liveness_not_start_authority(self):
    self.safety.set_alternative_experience(ALTERNATIVE_EXPERIENCE.ENABLE_MADS)
    self.safety.set_heartbeat_engaged_mads(False)
    self.assertTrue(self._rx(self._pcm_status_msg(False)))
    self.assertTrue(self._rx(self._mads_touch_msg(3)))
    self.assertTrue(self.safety.get_controls_allowed_lateral())

    for _ in range(2):
      self.safety.run_mads_heartbeat_check()
      self.assertTrue(self.safety.get_controls_allowed_lateral())
    self.safety.run_mads_heartbeat_check()
    self.assertFalse(self.safety.get_controls_allowed_lateral())

  def test_touch_mads_brake_modes_remain_authoritative(self):
    safety_param = self.safety.get_current_safety_param()
    for mode, resumes in ((ALTERNATIVE_EXPERIENCE.MADS_DISENGAGE_LATERAL_ON_BRAKE, False),
                          (ALTERNATIVE_EXPERIENCE.MADS_PAUSE_LATERAL_ON_BRAKE, True)):
      self.safety.set_safety_hooks(CarParams.SafetyModel.tesla, safety_param)
      self.safety.init_tests()
      self.safety.set_alternative_experience(ALTERNATIVE_EXPERIENCE.ENABLE_MADS | mode)
      self.safety.set_heartbeat_engaged_mads(True)
      self.assertTrue(self._rx(self._pcm_status_msg(False)))
      self.assertTrue(self._rx(self._mads_touch_msg(3)))
      self.assertTrue(self.safety.get_controls_allowed_lateral())
      self.assertTrue(self._rx(self._user_brake_msg(True)))
      self.assertFalse(self.safety.get_controls_allowed_lateral())
      self.assertTrue(self._rx(self._user_brake_msg(False)))
      self.assertEqual(resumes, self.safety.get_controls_allowed_lateral())

  def test_touch_mads_does_not_grant_unconfigured_longitudinal_or_speed_sync_tx(self):
    safety_param = self.safety.get_current_safety_param() | TeslaSafetyFlags.SPEED_SYNC
    self.safety.set_safety_hooks(CarParams.SafetyModel.tesla, safety_param)
    self.safety.init_tests()
    self.safety.set_alternative_experience(ALTERNATIVE_EXPERIENCE.ENABLE_MADS)
    self.safety.set_heartbeat_engaged_mads(True)
    self.assertTrue(self._rx(self._pcm_status_msg(False)))
    self.assertTrue(self._rx(self._mads_touch_msg(3)))
    self.assertTrue(self.safety.get_controls_allowed_lateral())
    self.assertFalse(self.safety.get_controls_allowed())

    # MADS cannot turn a stock-longitudinal safety configuration into active
    # longitudinal authority. A LONG_CONTROL configuration is intentionally a
    # separate authority selected before this gesture is received.
    if not self.LONGITUDINAL:
      active_long = self._long_control_msg(30, acc_state=self.acc_states["ACC_ON"])
      self.assertFalse(self._tx(active_long))
    template = self._speed_sync_msg(0)
    self.assertTrue(self._rx(template))
    self.assertFalse(self._tx(self._speed_sync_msg(1, template=template)))

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
                self._steering_status_msg(eac_status=3),
                self._steering_status_msg(eac_status=0, eac_error_code=9)):
      self.safety.set_safety_hooks(CarParams.SafetyModel.tesla, safety_param)
      self.safety.init_tests()
      self._engage_mads()
      self.assertTrue(self._rx(msg))
      self.assertFalse(self.safety.get_controls_allowed())
      self.assertFalse(self.safety.get_controls_allowed_lateral())
      self.assertFalse(self._tx(self._angle_cmd_msg(0, True)))

  def test_mads_cooperative_driver_override_still_disengages(self):
    safety_param = self.safety.get_current_safety_param()
    for msg in (self._steering_status_msg(torque=5.01),
                self._steering_status_msg(hands_on_level=3)):
      self.safety.set_safety_hooks(CarParams.SafetyModel.tesla, safety_param)
      self.safety.init_tests()
      self._engage_mads(cooperative_steering=True)

      self.assertTrue(self._rx(msg))
      self.assertFalse(self.safety.get_controls_allowed())
      self.assertFalse(self.safety.get_controls_allowed_lateral())
      self.assertFalse(self._tx(self._angle_cmd_msg(0, True)))

  def test_mads_cooperative_high_angle_rate_fault_still_disengages(self):
    self._engage_mads(cooperative_steering=True)
    self.assertTrue(self._rx(self._steering_status_msg(eac_status=0, eac_error_code=9)))
    self.assertFalse(self.safety.get_controls_allowed())
    self.assertFalse(self.safety.get_controls_allowed_lateral())
    self.assertFalse(self._tx(self._angle_cmd_msg(0, True)))

  def test_mads_eps_error_4_pauses_output_then_recovers_after_stable_available(self):
    self._engage_mads(cooperative_steering=True)
    self.assertTrue(self._rx(self._steering_status_msg(torque=4.12, eac_status=0, eac_error_code=4)))
    self.assertTrue(self.safety.get_controls_allowed_lateral())
    self.assertFalse(self._tx(self._angle_cmd_msg(0, True)))
    self.assertTrue(self._tx(self._angle_cmd_msg(0, False)))

    for _ in range(24):
      self.assertTrue(self._rx(self._steering_status_msg(eac_status=1)))
      self.assertFalse(self._tx(self._angle_cmd_msg(0, True)))

    self.assertTrue(self._rx(self._steering_status_msg(eac_status=1)))
    self.assertTrue(self._tx(self._angle_cmd_msg(0, True)))

  def test_mads_persistent_eps_inhibit_pauses_without_revoking_lateral_authority(self):
    self._engage_mads(cooperative_steering=True)
    for error_code in (0, 4, 8):
      inhibited = self._steering_status_msg(eac_status=0, eac_error_code=error_code)
      for _ in range(150):
        self.assertTrue(self._rx(inhibited))
        self.assertTrue(self.safety.get_controls_allowed_lateral())
        self.assertFalse(self._tx(self._angle_cmd_msg(0, True)))

    for _ in range(24):
      self.assertTrue(self._rx(self._steering_status_msg(eac_status=1)))
      self.assertFalse(self._tx(self._angle_cmd_msg(0, True)))

    self.assertTrue(self._rx(self._steering_status_msg(eac_status=1)))
    self.assertTrue(self.safety.get_controls_allowed_lateral())
    self.assertTrue(self._tx(self._angle_cmd_msg(0, True)))

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
