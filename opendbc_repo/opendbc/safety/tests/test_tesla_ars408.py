import unittest

from opendbc.car.structs import CarParams
from opendbc.car.tesla.ars408_can import ARS408CAN
from opendbc.car.tesla.values import TeslaSafetyFlags
import opendbc.safety.tests.common as common
from opendbc.safety.tests.libsafety import libsafety_py


MSG_ARS408_CONFIG = 0x200
MSG_ARS408_FILTER_CONFIG = 0x202
MSG_ARS408_SPEED = 0x300
MSG_ARS408_YAW_RATE = 0x301


class TestTeslaARS408Safety(unittest.TestCase):
  def setUp(self):
    self.safety = libsafety_py.libsafety

  def set_mode(self, flags=TeslaSafetyFlags.ARS408):
    self.safety.set_safety_hooks(CarParams.SafetyModel.tesla, int(flags))
    self.safety.init_tests()

  def tx(self, address, data, bus=1):
    return self.safety.safety_tx_hook(common.make_msg(bus, address, len(data), data))

  def tx_encoded(self, message):
    address, data, bus = message
    return self.tx(address, data, bus)

  def test_ars408_ids_require_dedicated_safety_flag(self):
    speed = ARS408CAN().create_speed_information(10.0, 1)
    for flags, allowed in ((0, False), (TeslaSafetyFlags.LONG_CONTROL, False),
                           (TeslaSafetyFlags.ARS408, True),
                           (TeslaSafetyFlags.ARS408 | TeslaSafetyFlags.LONG_CONTROL, True)):
      self.set_mode(flags)
      self.assertEqual(allowed, self.tx_encoded(speed), flags)

  def test_ars408_bus_dlc_and_field_scoped_configuration(self):
    self.set_mode()
    can = ARS408CAN()
    for field, value in (("max_distance", 250), ("send_extended", 0), ("send_extended", 1),
                         ("output_type", 0), ("output_type", 1), ("store_nvm", 1)):
      self.assertTrue(self.tx_encoded(can.create_radar_configuration(field, value)), (field, value))

    self.assertFalse(self.tx(MSG_ARS408_CONFIG, b"\x01\x1f\x40\x00\x00\x00\x00\x00", bus=0))
    self.assertFalse(self.tx(MSG_ARS408_CONFIG, b"\xff\x00\x00\x00\x00\x00\x00\x00"))
    self.assertFalse(self.safety.safety_tx_hook(common.make_msg(1, MSG_ARS408_CONFIG, 5)))

  def test_filter_query_write_and_payload_limits(self):
    self.set_mode()
    can = ARS408CAN()
    self.assertTrue(self.tx_encoded(can.create_filter_query(0)))
    self.assertTrue(self.tx_encoded(can.create_filter_configuration(0, 1, 0, 48)))
    self.assertFalse(self.tx(MSG_ARS408_FILTER_CONFIG, b"\xf8\x00\x00\x00\x00"))
    # Valid object-filter header with an out-of-range object limit payload.
    self.assertFalse(self.tx(MSG_ARS408_FILTER_CONFIG, bytes.fromhex("82ffffffff")))

  def test_speed_direction_and_reserved_bits_are_checked(self):
    self.set_mode()
    can = ARS408CAN()
    for direction in (0, 1, 2):
      self.assertTrue(self.tx_encoded(can.create_speed_information(10.0, direction)))
    self.assertFalse(self.tx(MSG_ARS408_SPEED, bytes.fromhex("c000")))
    self.assertTrue(self.tx_encoded(can.create_yaw_rate_information(-12.5)))

  def test_configuration_writes_are_blocked_while_controls_allowed(self):
    self.set_mode()
    self.safety.set_controls_allowed(True)
    can = ARS408CAN()
    self.assertFalse(self.tx_encoded(can.create_radar_configuration("max_distance", 250)))
    self.assertFalse(self.tx_encoded(can.create_filter_configuration(0, 1, 0, 48)))
    # Read-only query and ego-motion input remain available while engaged.
    self.assertTrue(self.tx_encoded(can.create_filter_query(0)))
    self.assertTrue(self.tx_encoded(can.create_speed_information(10.0, 1)))
    self.assertTrue(self.tx_encoded(can.create_yaw_rate_information(1.0)))
