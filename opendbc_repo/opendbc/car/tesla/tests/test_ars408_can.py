from opendbc.car.tesla.ars408_can import ARS408_BUS, ARS408_SENSOR_ID, ARS408CAN


def test_startup_configuration_is_safe_for_shared_tesla_can():
  address, data, bus = ARS408CAN().create_radar_configuration()

  assert address == 0x200
  assert bus == ARS408_BUS == 1
  assert len(data) == 8


def test_decoder_and_configuration_share_sensor_id():
  assert ARS408_SENSOR_ID == 5
