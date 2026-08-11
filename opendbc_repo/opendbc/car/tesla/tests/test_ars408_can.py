import math
import time
from types import SimpleNamespace

import pytest

from opendbc.can import CANParser
from opendbc.car import structs
from opendbc.car.tesla.ars408_can import (
  ARS408_BUS, ARS408_FILTER_SIGNALS, ARS408_MOTION_INPUT_ENABLED, ARS408_SENSOR_ID, ARS408CAN,
)
from opendbc.car.tesla.carcontroller import CarController
from opendbc.car.tesla.carstate import calculate_yaw_rate


def decode(message, name):
  address, data, bus = message
  parser = CANParser("ARS408", [(name, math.nan)], bus)
  parser.update([(1_000_000_000, [(address, data, bus)])])
  return parser.vl[name]


def test_field_scoped_configuration_targets_dedicated_radar_can():
  address, data, bus = ARS408CAN().create_radar_configuration("max_distance", 250)

  assert address == 0x200
  assert bus == ARS408_BUS == 1
  assert len(data) == 8


def test_decoder_and_configuration_share_sensor_id():
  assert ARS408_SENSOR_ID == 0


@pytest.mark.parametrize(("field", "value", "valid_signal", "value_signal"), [
  ("max_distance", 236, "RadarCfg_MaxDistance_valid", "RadarCfg_MaxDistance"),
  ("send_extended", 0, "RadarCfg_SendExtInfo_valid", "RadarCfg_SendExtInfo"),
  ("output_type", 1, "RadarCfg_OutputType_valid", "RadarCfg_OutputType"),
  ("store_nvm", 1, "RadarCfg_StoreInNVM_valid", "RadarCfg_StoreInNVM"),
])
def test_configuration_sets_only_the_requested_valid_bit(field, value, valid_signal, value_signal):
  state = decode(ARS408CAN().create_radar_configuration(field, value), "RadarConfiguration")
  valid_signals = [name for name in state if name.endswith("_valid")]

  assert state[valid_signal] == 1
  assert state[value_signal] == value
  assert all(state[name] == (1 if name == valid_signal else 0) for name in valid_signals)


@pytest.mark.parametrize(("field", "value"), [
  ("max_distance", 199), ("max_distance", 251), ("max_distance", 201), ("output_type", 2),
])
def test_unsupported_configuration_is_rejected(field, value):
  with pytest.raises(ValueError):
    ARS408CAN().create_radar_configuration(field, value)


def test_object_filter_writes_one_complete_record():
  address, data, bus = ARS408CAN().create_filter_configuration(1, True, 10.0, 200.0)
  state = decode((address, data, bus), "FilterCfg")

  assert address == 0x202
  assert state["FilterCfg_Type"] == 1
  assert state["FilterCfg_Index"] == 1
  assert state["FilterCfg_Active"] == 1
  assert state["FilterCfg_Valid"] == 1
  assert state["FilterCfg_Min_Distance"] == 10.0
  assert state["FilterCfg_Max_Distance"] == 200.0


def test_object_filter_query_cannot_modify_the_selected_record():
  address, data, bus = ARS408CAN().create_filter_query(0)
  state = decode((address, data, bus), "FilterCfg")

  assert address == 0x202
  assert state["FilterCfg_Type"] == 1
  assert state["FilterCfg_Index"] == 0
  assert state["FilterCfg_Active"] == 0
  assert state["FilterCfg_Valid"] == 0
  assert state["FilterCfg_Min_NofObj"] == 0
  assert state["FilterCfg_Max_NofObj"] == 0


def test_all_supported_object_filter_indices_pack():
  for index, (_suffix, lower, upper, _resolution) in ARS408_FILTER_SIGNALS.items():
    state = decode(ARS408CAN().create_filter_configuration(index, True, lower, upper), "FilterCfg")
    assert state["FilterCfg_Index"] == index
    assert state["FilterCfg_Type"] == 1


def test_motion_input_frames_are_encoded_for_dedicated_radar_bus():
  packer = ARS408CAN()
  speed_address, speed_data, speed_bus = packer.create_speed_information(27.5, 1)
  yaw_address, yaw_data, yaw_bus = packer.create_yaw_rate_information(-12.5)

  assert (speed_address, len(speed_data), speed_bus) == (0x300, 2, ARS408_BUS)
  assert (yaw_address, len(yaw_data), yaw_bus) == (0x301, 2, ARS408_BUS)
  assert ARS408_MOTION_INPUT_ENABLED


def test_yaw_rate_estimate_uses_vehicle_model_and_stops_at_zero_speed():
  class FakeVehicleModel:
    @staticmethod
    def calc_curvature(_steering_angle_rad, _speed_mps, _roll):
      return 0.01

  assert calculate_yaw_rate(FakeVehicleModel(), 20.0, 10.0) == -0.2
  assert calculate_yaw_rate(FakeVehicleModel(), 0.0, 10.0) == 0.0


def test_controller_sends_valid_motion_inputs_and_reverses_yaw_sign():
  controller = CarController.__new__(CarController)
  controller.ars408_can = ARS408CAN()
  controller.radar_motion_enabled = True
  controller._radar_motion_valid_prev = None
  car_state = SimpleNamespace(out=SimpleNamespace(
    vEgoRaw=20.0,
    yawRate=0.1,
    canValid=True,
    standstill=False,
    gearShifter=structs.CarState.GearShifter.reverse,
  ))

  messages = controller.send_radar_motion(car_state)
  parser = CANParser("ARS408", [("SpeedInformation", math.nan), ("YawRateInformation", math.nan)], ARS408_BUS)
  parser.update([(1_000_000_000, messages)])

  assert parser.vl["SpeedInformation"]["RadarDevice_Speed"] == 20.0
  assert parser.vl["SpeedInformation"]["RadarDevice_SpeedDirection"] == 2
  assert parser.vl["YawRateInformation"]["RadarDevice_YawRate"] == pytest.approx(-math.degrees(0.1), abs=0.02)


def test_controller_stops_motion_tx_when_car_state_is_invalid():
  controller = CarController.__new__(CarController)
  controller.ars408_can = ARS408CAN()
  controller.radar_motion_enabled = True
  controller._radar_motion_valid_prev = None
  car_state = SimpleNamespace(out=SimpleNamespace(vEgoRaw=20.0, yawRate=0.1, canValid=False))

  assert controller.send_radar_motion(car_state) == []


class FakeParams:
  def __init__(self, values=None):
    self.values = dict(values or {})

  def get(self, key, encoding=None):
    value = self.values.get(key)
    if value is None:
      return None
    return value if encoding else str(value).encode()

  def remove(self, key):
    self.values.pop(key, None)

  def put_nonblocking(self, key, value):
    self.values[key] = str(value)

  def put(self, key, value):
    self.values[key] = str(value)


def test_controller_waits_for_readback_before_nvm_store():
  request_id = str(int(time.time() * 1000))
  controller = CarController.__new__(CarController)
  controller.ars408_can = ARS408CAN()
  controller.params = FakeParams({
    "TeslaRadarConfigRequest": f"{request_id},max_distance,240,1",
    "TeslaRadarStateMaxDistance": "240",
    "TeslaRadarStateSeq": "7",
  })
  controller._radar_config_request = None
  controller._radar_filter_request = None
  controller.frame = 100
  controls = SimpleNamespace(latActive=False, longActive=False)
  car_state = SimpleNamespace(out=SimpleNamespace(canValid=True, standstill=True))

  sends = controller.update_radar_configuration(controls, car_state)
  assert len(sends) == 1
  assert decode(sends[0], "RadarConfiguration")["RadarCfg_MaxDistance_valid"] == 1
  assert controller.params.values["TeslaRadarConfigResult"].split(",")[1] == "sent"

  controller.frame += 1
  assert controller.update_radar_configuration(controls, car_state) == []
  assert controller._radar_config_request is not None
  controller.params.values["TeslaRadarStateSeq"] = "8"
  controller.frame += 1
  sends = controller.update_radar_configuration(controls, car_state)
  assert len(sends) == 1
  assert decode(sends[0], "RadarConfiguration")["RadarCfg_StoreInNVM_valid"] == 1
  assert controller._radar_config_request is None
  assert controller.params.values["TeslaRadarConfigResult"].split(",")[1] == "nvm_sent"


@pytest.mark.parametrize(("field", "value", "valid_signal"), [
  ("max_distance", 240, "RadarCfg_MaxDistance_valid"),
  ("send_extended", 0, "RadarCfg_SendExtInfo_valid"),
  ("output_type", 0, "RadarCfg_OutputType_valid"),
])
def test_controller_configures_while_moving_and_engaged(field, value, valid_signal):
  request_id = str(int(time.time() * 1000))
  controller = CarController.__new__(CarController)
  controller.ars408_can = ARS408CAN()
  controller.params = FakeParams({"TeslaRadarConfigRequest": f"{request_id},{field},{value},0"})
  controller._radar_config_request = None
  controller._radar_filter_request = None
  controller.frame = 100
  controls = SimpleNamespace(latActive=True, longActive=True)
  car_state = SimpleNamespace(out=SimpleNamespace(canValid=True, standstill=False))

  sends = controller.update_radar_configuration(controls, car_state)
  assert len(sends) == 1
  assert decode(sends[0], "RadarConfiguration")[valid_signal] == 1
  assert controller.params.values["TeslaRadarConfigResult"].split(",")[1] == "sent"


def test_controller_stores_nvm_while_moving_and_engaged():
  request_id = str(int(time.time() * 1000))
  controller = CarController.__new__(CarController)
  controller.ars408_can = ARS408CAN()
  controller.params = FakeParams({"TeslaRadarConfigRequest": f"{request_id},max_distance,240,1"})
  controller._radar_config_request = None
  controller._radar_filter_request = None
  controller.frame = 100
  controls = SimpleNamespace(latActive=False, longActive=False)
  car_state = SimpleNamespace(out=SimpleNamespace(canValid=True, standstill=True))

  assert len(controller.update_radar_configuration(controls, car_state)) == 1
  controller.params.values.update({"TeslaRadarStateMaxDistance": "240", "TeslaRadarStateSeq": "1"})
  car_state.out.standstill = False
  controls.latActive = True
  controls.longActive = True
  controller.frame += 1
  sends = controller.update_radar_configuration(controls, car_state)
  assert len(sends) == 1
  assert decode(sends[0], "RadarConfiguration")["RadarCfg_StoreInNVM_valid"] == 1


def test_controller_waits_only_for_valid_can_before_configuration():
  request_id = str(int(time.time() * 1000))
  controller = CarController.__new__(CarController)
  controller.ars408_can = ARS408CAN()
  controller.params = FakeParams({"TeslaRadarConfigRequest": f"{request_id},output_type,1,0"})
  controller._radar_config_request = None
  controller._radar_filter_request = None
  controller.frame = 100
  controls = SimpleNamespace(latActive=True, longActive=True)
  car_state = SimpleNamespace(out=SimpleNamespace(canValid=False, standstill=False))

  assert controller.update_radar_configuration(controls, car_state) == []
  assert controller.params.values["TeslaRadarConfigResult"].split(",")[1:] == ["waiting", "wait for valid CAN"]

  car_state.out.canValid = True
  controller.frame += 1
  sends = controller.update_radar_configuration(controls, car_state)
  assert len(sends) == 1
  assert decode(sends[0], "RadarConfiguration")["RadarCfg_OutputType_valid"] == 1


def test_controller_processes_queued_requests_without_overwriting():
  now_ms = int(time.time() * 1000)
  controller = CarController.__new__(CarController)
  controller.ars408_can = ARS408CAN()
  controller.params = FakeParams({
    "TeslaRadarConfigRequest": f"{now_ms},send_extended,0,0\n{now_ms + 1},output_type,0,0",
  })
  controller._radar_config_request = None
  controller._radar_filter_request = None
  controller.frame = 100
  controls = SimpleNamespace(latActive=False, longActive=False)
  car_state = SimpleNamespace(out=SimpleNamespace(canValid=True, standstill=True))

  first = controller.update_radar_configuration(controls, car_state)
  assert decode(first[0], "RadarConfiguration")["RadarCfg_SendExtInfo_valid"] == 1
  assert controller.params.values["TeslaRadarConfigRequest"].split(",")[1] == "output_type"
  controller.params.values.update({"TeslaRadarStateExtended": "0", "TeslaRadarStateSeq": "1"})
  controller.frame += 1
  assert controller.update_radar_configuration(controls, car_state) == []
  controller.frame += 1
  second = controller.update_radar_configuration(controls, car_state)
  assert decode(second[0], "RadarConfiguration")["RadarCfg_OutputType_valid"] == 1


def test_controller_discards_expired_request():
  old_ms = int(time.time() * 1000) - 31 * 60 * 1000
  controller = CarController.__new__(CarController)
  controller.ars408_can = ARS408CAN()
  controller.params = FakeParams({"TeslaRadarConfigRequest": f"{old_ms},max_distance,240,0"})
  controller._radar_config_request = None
  controller._radar_filter_request = None
  controller.frame = 100
  controls = SimpleNamespace(latActive=False, longActive=False)
  car_state = SimpleNamespace(out=SimpleNamespace(canValid=True, standstill=True))

  assert controller.update_radar_configuration(controls, car_state) == []
  assert controller.params.values["TeslaRadarConfigResult"].split(",")[1] == "expired"


def test_filter_write_queries_current_record_before_changing_to_48():
  request_id = str(int(time.time() * 1000))
  controller = CarController.__new__(CarController)
  controller.ars408_can = ARS408CAN()
  controller.params = FakeParams({
    "TeslaRadarFilterRequest": f"{request_id},0,1,0,48",
    "TeslaRadarFilterState": "0,1,0.0,32.0",
    "TeslaRadarFilterStateSeq": "4",
  })
  controller._radar_config_request = None
  controller._radar_filter_request = None
  controller.frame = 100
  controls = SimpleNamespace(latActive=False, longActive=False)
  car_state = SimpleNamespace(out=SimpleNamespace(canValid=True, standstill=True))

  query = controller.update_radar_configuration(controls, car_state)
  assert len(query) == 1
  assert decode(query[0], "FilterCfg")["FilterCfg_Valid"] == 0
  controller.frame += 1
  assert controller.update_radar_configuration(controls, car_state) == []
  assert controller._radar_filter_request is not None

  controller.params.values["TeslaRadarFilterStateSeq"] = "5"
  controller.frame += 1
  assert controller.update_radar_configuration(controls, car_state) == []
  assert controller.params.values["TeslaRadarFilterResult"].split(",")[1] == "queried"

  controller.frame += 1
  write = controller.update_radar_configuration(controls, car_state)
  assert len(write) == 1
  written = decode(write[0], "FilterCfg")
  assert written["FilterCfg_Valid"] == 1
  assert written["FilterCfg_Index"] == 0
  assert written["FilterCfg_Max_NofObj"] == 48

  controller.params.values.update({"TeslaRadarFilterState": "0,1,0.0,48.0", "TeslaRadarFilterStateSeq": "6"})
  controller.frame += 1
  assert controller.update_radar_configuration(controls, car_state) == []
  assert controller._radar_filter_request is None
  assert controller.params.values["TeslaRadarFilterResult"].split(",")[1] == "applied"


def test_filter_query_only_reports_index_zero_without_writing():
  request_id = str(int(time.time() * 1000))
  controller = CarController.__new__(CarController)
  controller.ars408_can = ARS408CAN()
  controller.params = FakeParams({
    "TeslaRadarFilterRequest": f"{request_id},query,0",
    "TeslaRadarFilterStateSeq": "0",
  })
  controller._radar_config_request = None
  controller._radar_filter_request = None
  controller.frame = 100
  controls = SimpleNamespace(latActive=True, longActive=True)
  car_state = SimpleNamespace(out=SimpleNamespace(canValid=True, standstill=False))

  sends = controller.update_radar_configuration(controls, car_state)
  assert len(sends) == 1
  assert decode(sends[0], "FilterCfg")["FilterCfg_Valid"] == 0

  controller.params.values.update({"TeslaRadarFilterState": "0,1,0.0,32.0", "TeslaRadarFilterStateSeq": "1"})
  controller.frame += 1
  assert controller.update_radar_configuration(controls, car_state) == []
  assert controller._radar_filter_request is None
  assert controller.params.values["TeslaRadarFilterResult"].split(",")[1:] == ["queried", "0:1:0.0:32.0"]


def test_filter_query_waits_only_for_valid_can():
  request_id = str(int(time.time() * 1000))
  controller = CarController.__new__(CarController)
  controller.ars408_can = ARS408CAN()
  controller.params = FakeParams({
    "TeslaRadarFilterRequest": f"{request_id},query,0",
    "TeslaRadarFilterStateSeq": "0",
  })
  controller._radar_config_request = None
  controller._radar_filter_request = None
  controller.frame = 100
  controls = SimpleNamespace(latActive=True, longActive=True)
  car_state = SimpleNamespace(out=SimpleNamespace(canValid=False, standstill=False))

  assert controller.update_radar_configuration(controls, car_state) == []
  assert controller.params.values["TeslaRadarFilterResult"].split(",")[1:] == ["waiting", "wait for valid CAN"]

  car_state.out.canValid = True
  controller.frame += 1
  sends = controller.update_radar_configuration(controls, car_state)
  assert len(sends) == 1
  assert decode(sends[0], "FilterCfg")["FilterCfg_Valid"] == 0


def test_filter_write_allows_moving_vehicle_when_controls_inactive():
  request_id = str(int(time.time() * 1000))
  controller = CarController.__new__(CarController)
  controller.ars408_can = ARS408CAN()
  controller.params = FakeParams({
    "TeslaRadarFilterRequest": f"{request_id},0,1,0,48",
    "TeslaRadarFilterStateSeq": "0",
  })
  controller._radar_config_request = None
  controller._radar_filter_request = None
  controller.frame = 100
  controls = SimpleNamespace(latActive=False, longActive=False)
  car_state = SimpleNamespace(out=SimpleNamespace(canValid=True, standstill=False))

  assert len(controller.update_radar_configuration(controls, car_state)) == 1
  controller.params.values.update({"TeslaRadarFilterState": "0,1,0.0,32.0", "TeslaRadarFilterStateSeq": "1"})
  controller.frame += 1
  assert controller.update_radar_configuration(controls, car_state) == []

  controller.frame += 1
  sends = controller.update_radar_configuration(controls, car_state)
  assert len(sends) == 1
  assert decode(sends[0], "FilterCfg")["FilterCfg_Max_NofObj"] == 48


@pytest.mark.parametrize("active_field", ["latActive", "longActive"])
def test_filter_write_allows_active_controls(active_field):
  request_id = str(int(time.time() * 1000))
  controller = CarController.__new__(CarController)
  controller.ars408_can = ARS408CAN()
  controller.params = FakeParams({
    "TeslaRadarFilterRequest": f"{request_id},0,1,0,48",
    "TeslaRadarFilterStateSeq": "0",
  })
  controller._radar_config_request = None
  controller._radar_filter_request = None
  controller.frame = 100
  controls = SimpleNamespace(latActive=False, longActive=False)
  car_state = SimpleNamespace(out=SimpleNamespace(canValid=True, standstill=False))

  assert len(controller.update_radar_configuration(controls, car_state)) == 1
  controller.params.values.update({"TeslaRadarFilterState": "0,1,0.0,32.0", "TeslaRadarFilterStateSeq": "1"})
  controller.frame += 1
  assert controller.update_radar_configuration(controls, car_state) == []

  setattr(controls, active_field, True)
  controller.frame += 1
  sends = controller.update_radar_configuration(controls, car_state)
  assert len(sends) == 1
  assert decode(sends[0], "FilterCfg")["FilterCfg_Max_NofObj"] == 48


def test_filter_write_stops_after_query_when_limit_is_already_48():
  request_id = str(int(time.time() * 1000))
  controller = CarController.__new__(CarController)
  controller.ars408_can = ARS408CAN()
  controller.params = FakeParams({
    "TeslaRadarFilterRequest": f"{request_id},0,1,0,48",
    "TeslaRadarFilterStateSeq": "0",
  })
  controller._radar_config_request = None
  controller._radar_filter_request = None
  controller.frame = 100
  controls = SimpleNamespace(latActive=False, longActive=False)
  car_state = SimpleNamespace(out=SimpleNamespace(canValid=True, standstill=True))

  assert len(controller.update_radar_configuration(controls, car_state)) == 1
  controller.params.values.update({"TeslaRadarFilterState": "0,1,0.0,48.0", "TeslaRadarFilterStateSeq": "1"})
  controller.frame += 1
  assert controller.update_radar_configuration(controls, car_state) == []
  assert controller._radar_filter_request is None
  assert controller.params.values["TeslaRadarFilterResult"].split(",")[1] == "applied"
