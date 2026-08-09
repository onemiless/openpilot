import math

from opendbc.can import CANParser
from opendbc.car.tesla.ars408_can import (
  ARS408_BUS, ARS408_MAX_DISTANCE, ARS408_MAX_OBJECTS, ARS408_SENSOR_ID,
  ARS408CAN, should_configure_radar,
)


def test_startup_configuration_is_safe_for_shared_tesla_can():
  address, data, bus = ARS408CAN().create_radar_configuration()

  assert address == 0x200
  assert bus == ARS408_BUS == 1
  assert len(data) == 8


def test_decoder_and_configuration_share_sensor_id():
  assert ARS408_SENSOR_ID == 0


def test_configuration_matches_persisted_sensor_zero_extended_output():
  address, data, bus = ARS408CAN().create_radar_configuration()
  parser = CANParser("ARS408", [("RadarConfiguration", math.nan)], bus)
  parser.update([(1_000_000_000, [(address, data, bus)])])

  assert ARS408_MAX_DISTANCE == 250
  assert parser.vl["RadarConfiguration"]["RadarCfg_MaxDistance"] == 250
  assert parser.vl["RadarConfiguration"]["RadarCfg_SensorID"] == 0
  assert parser.vl["RadarConfiguration"]["RadarCfg_SendExtInfo"] == 1
  assert parser.vl["RadarConfiguration"]["RadarCfg_SendQuality"] == 1
  assert parser.vl["RadarConfiguration"]["RadarCfg_StoreInNVM_valid"] == 1
  assert parser.vl["RadarConfiguration"]["RadarCfg_StoreInNVM"] == 1


def test_object_count_filter_limits_shared_bus_load():
  address, data, bus = ARS408CAN().create_object_count_filter()
  parser = CANParser("ARS408", [("FilterCfg", math.nan)], bus)
  parser.update([(1_000_000_000, [(address, data, bus)])])

  assert address == 0x202
  assert parser.vl["FilterCfg"]["FilterCfg_Type"] == 1
  assert parser.vl["FilterCfg"]["FilterCfg_Index"] == 0
  assert parser.vl["FilterCfg"]["FilterCfg_Active"] == 1
  assert parser.vl["FilterCfg"]["FilterCfg_Max_NofObj"] == ARS408_MAX_OBJECTS == 32


def test_configuration_is_only_sent_after_explicit_manual_request():
  assert not should_configure_radar(10)
  assert not should_configure_radar(500)
  assert not should_configure_radar(501)
  assert not should_configure_radar(1000)
  assert not should_configure_radar(3000)
  assert should_configure_radar(3000, reinitialize=True)


def test_motion_input_frames_are_encoded_but_not_implicitly_enabled():
  packer = ARS408CAN()
  speed_address, speed_data, speed_bus = packer.create_speed_information(27.5, 1)
  yaw_address, yaw_data, yaw_bus = packer.create_yaw_rate_information(-12.5)

  assert (speed_address, len(speed_data), speed_bus) == (0x300, 2, ARS408_BUS)
  assert (yaw_address, len(yaw_data), yaw_bus) == (0x301, 2, ARS408_BUS)
