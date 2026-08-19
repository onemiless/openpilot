from types import SimpleNamespace
import math
import time

import pytest

from opendbc.can import CANParser
from opendbc.car import gen_empty_fingerprint, structs
from opendbc.car.tesla.ars408_can import ARS408_BUS, ARS408_FILTER_SIGNALS, ARS408CAN
from opendbc.car.tesla.ars408_controller import ARS408Controller, calculate_yaw_rate
from opendbc.car.tesla.carcontroller import CarController
from opendbc.car.tesla.ars408_radar_interface import ARS408RadarInterface, object_is_usable
from opendbc.car.tesla.interface import CarInterface
from opendbc.car.tesla.radar_interface import RadarInterface
from opendbc.car.tesla.values import CAR, DBC, TeslaFlags, TeslaSafetyFlags
from openpilot.common.params import Params


def decode(message, name):
  address, data, bus = message
  parser = CANParser("ARS408", [(name, math.nan)], bus)
  parser.update([(1_000_000_000, [(address, data, bus)])])
  return parser.vl[name]


def make_ars408_controller():
  CP = CarInterface.get_non_essential_params(CAR.TESLA_MODEL_Y)
  return ARS408Controller(CP)


def wait_for_param(params, key, expected, timeout=1.0):
  deadline = time.monotonic() + timeout
  while time.monotonic() < deadline:
    value = params.get(key)
    if value is not None and expected in value:
      return value
    time.sleep(0.01)
  raise AssertionError(f"{key} did not contain {expected!r}")


def wait_for_value(params, key, expected, timeout=1.0):
  deadline = time.monotonic() + timeout
  while time.monotonic() < deadline:
    if params.get(key) == expected:
      return
    time.sleep(0.01)
  raise AssertionError(f"{key} did not become {expected!r}")


def wait_for_positive(params, key, timeout=1.0):
  deadline = time.monotonic() + timeout
  while time.monotonic() < deadline:
    value = params.get(key)
    if isinstance(value, int) and value > 0:
      return value
    time.sleep(0.01)
  raise AssertionError(f"{key} did not become positive")


class FakeVehicleModel:
  def calc_curvature(self, steering_angle_rad, speed_mps, roll):
    assert speed_mps >= 0.0 and roll == 0.0
    return steering_angle_rad * 0.02


def test_tesla_yaw_rate_uses_vehicle_model_and_handles_invalid_input():
  vm = FakeVehicleModel()
  left = calculate_yaw_rate(vm, 10.0, 5.0)
  right = calculate_yaw_rate(vm, 10.0, -5.0)
  assert left == -right
  assert left < 0.0
  assert calculate_yaw_rate(vm, 0.0, 20.0) == 0.0
  assert calculate_yaw_rate(vm, float("nan"), 20.0) == 0.0


def test_ars408_mode_latches_python_and_panda_safety_flags():
  params = Params()
  params.put_int("TeslaRadarMode", 2)
  CP = CarInterface.get_params(CAR.TESLA_MODEL_Y, gen_empty_fingerprint(), [], False, False, False)
  assert CP.flags & TeslaFlags.ARS408_RADAR
  assert CP.safetyConfigs[0].safetyParam & TeslaSafetyFlags.ARS408
  assert not CP.radarUnavailable

  params.put_int("TeslaRadarMode", 0)
  factory_CP = CarInterface.get_params(CAR.TESLA_MODEL_Y, gen_empty_fingerprint(), [], False, False, False)
  assert not factory_CP.flags & TeslaFlags.ARS408_RADAR
  assert not factory_CP.safetyConfigs[0].safetyParam & TeslaSafetyFlags.ARS408


def test_tesla_controller_publishes_active_ars408_mode():
  params = Params()
  params.put_int("TeslaRadarMode", 2)
  CP = CarInterface.get_params(CAR.TESLA_MODEL_Y, gen_empty_fingerprint(), [], False, False, False)
  CarController(DBC[CP.carFingerprint], CP)
  wait_for_value(params, "TeslaRadarControllerActive", True)
  wait_for_value(params, "TeslaRadarActiveMode", 2)
  wait_for_value(params, "TeslaRadarVehicleDetected", True)


def test_ars408_can_addresses_and_lengths():
  can = ARS408CAN()
  messages = [
    can.create_radar_configuration("max_distance", 250),
    can.create_radar_configuration("send_extended", 1),
    can.create_radar_configuration("output_type", 1),
    can.create_filter_query(0),
    can.create_speed_information(12.5, 1),
    can.create_yaw_rate_information(-3.25),
  ]
  assert [(address, len(data), bus) for address, data, bus in messages] == [
    (0x200, 8, ARS408_BUS),
    (0x200, 8, ARS408_BUS),
    (0x200, 8, ARS408_BUS),
    (0x202, 5, ARS408_BUS),
    (0x300, 2, ARS408_BUS),
    (0x301, 2, ARS408_BUS),
  ]


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


def test_object_filter_write_and_query_encode_complete_records():
  state = decode(ARS408CAN().create_filter_configuration(1, True, 10.0, 200.0), "FilterCfg")
  assert state["FilterCfg_Type"] == 1
  assert state["FilterCfg_Index"] == 1
  assert state["FilterCfg_Active"] == 1
  assert state["FilterCfg_Valid"] == 1
  assert state["FilterCfg_Min_Distance"] == 10.0
  assert state["FilterCfg_Max_Distance"] == 200.0

  query = decode(ARS408CAN().create_filter_query(0), "FilterCfg")
  assert query["FilterCfg_Type"] == 1
  assert query["FilterCfg_Index"] == 0
  assert query["FilterCfg_Active"] == 0
  assert query["FilterCfg_Valid"] == 0
  assert query["FilterCfg_Min_NofObj"] == 0
  assert query["FilterCfg_Max_NofObj"] == 0


def test_all_supported_object_filter_indices_pack():
  for index, (_suffix, lower, upper, _resolution) in ARS408_FILTER_SIGNALS.items():
    state = decode(ARS408CAN().create_filter_configuration(index, True, lower, upper), "FilterCfg")
    assert state["FilterCfg_Index"] == index
    assert state["FilterCfg_Type"] == 1


def test_ars408_object_filtering_keeps_confident_in_range_target():
  obj = {
    "Obj_MeasState": 2,
    "Obj_ProbOfExist": 5,
    "Obj_DistLong": 40.0,
    "Obj_DistLat": -0.5,
    "Obj_VrelLong": -2.0,
    "Obj_VrelLat": 0.1,
    "Obj_DynProp": 0,
  }
  assert object_is_usable(obj)
  assert not object_is_usable(obj | {"Obj_ProbOfExist": 1})
  assert not object_is_usable(obj | {"Obj_DistLong": 260.0})


def test_tesla_radar_wrapper_delegates_carrot_update_to_ars408(monkeypatch):
  CP = structs.CarParams()
  CP.flags = TeslaFlags.ARS408_RADAR.value
  CP.radarUnavailable = False
  CP.radarTimeStep = 1.0 / 14.0
  radar = RadarInterface(CP)
  assert isinstance(radar.ars408, ARS408RadarInterface)

  sentinel = object()
  monkeypatch.setattr(radar.ars408, "update_carrot", lambda *args: sentinel)
  assert radar.update_carrot(0.0, 0.0, 0.0, []) is sentinel


def test_ars408_controller_sends_motion_without_overwriting_persisted_configuration():
  Params().put_bool("TeslaRadarMotionInput", True)
  controller = make_ars408_controller()
  CS = SimpleNamespace(out=SimpleNamespace(
    vEgoRaw=12.5,
    yawRate=0.05,
    steeringAngleDeg=5.0,
    canValid=True,
    gearShifter=structs.CarState.GearShifter.drive,
    standstill=False,
  ))

  sends = controller.update(SimpleNamespace(enabled=False), CS, 10)
  assert [(address, len(data), bus) for address, data, bus in sends] == [
    (0x300, 2, ARS408_BUS),
    (0x301, 2, ARS408_BUS),
  ]
  wait_for_value(Params(), "TeslaRadarVehicleStandstill", False)
  wait_for_value(Params(), "TeslaRadarControlsEnabled", False)
  wait_for_positive(Params(), "TeslaRadarApplyHeartbeat")


def test_ars408_runtime_config_waits_for_radar_confirmation():
  params = Params()
  request_id = str(int(time.monotonic() * 1000))
  params.put("TeslaRadarConfigRequest", f"{request_id},max_distance,248,0")
  params.put_int("TeslaRadarStateSeq", 0)
  controller = make_ars408_controller()
  CS = SimpleNamespace(out=SimpleNamespace(
    vEgoRaw=0.0, yawRate=0.0, steeringAngleDeg=0.0, canValid=True,
    gearShifter=structs.CarState.GearShifter.park, standstill=True,
  ))

  sends = controller.update(SimpleNamespace(enabled=False), CS, 9)
  assert [(address, len(data), bus) for address, data, bus in sends] == [(0x200, 8, ARS408_BUS)]
  assert params.get("TeslaRadarConfigRequest") is not None
  wait_for_param(params, "TeslaRadarConfigResult", ",sent,max_distance")

  params.put_int("TeslaRadarStateMaxDistance", 248)
  params.put_int("TeslaRadarStateSeq", 1)
  # Completing a manual request must not append hidden configuration writes.
  assert controller.update(SimpleNamespace(enabled=False), CS, 10) == []
  wait_for_param(params, "TeslaRadarConfigResult", ",applied,max_distance")
  assert params.get("TeslaRadarConfigRequest") is None


def test_ars408_configuration_waits_while_vehicle_is_moving():
  params = Params()
  request_id = str(int(time.monotonic() * 1000))
  params.put("TeslaRadarConfigRequest", f"{request_id},max_distance,248,0")
  controller = make_ars408_controller()
  CS = SimpleNamespace(out=SimpleNamespace(
    vEgoRaw=5.0, yawRate=0.0, steeringAngleDeg=0.0, canValid=True,
    gearShifter=structs.CarState.GearShifter.drive, standstill=False,
  ))
  assert controller.update(SimpleNamespace(enabled=False), CS, 1) == []
  assert params.get("TeslaRadarConfigRequest") is not None
  wait_for_param(params, "TeslaRadarConfigResult", ",waiting,vehicle must be stationary")


def test_malformed_request_is_rejected_without_escaping_control_loop():
  params = Params()
  params.put("TeslaRadarConfigRequest", "broken,max_distance,248,0")
  controller = make_ars408_controller()
  CS = SimpleNamespace(out=SimpleNamespace(
    vEgoRaw=0.0, yawRate=0.0, steeringAngleDeg=0.0, canValid=True,
    gearShifter=structs.CarState.GearShifter.park, standstill=True,
  ))
  assert controller.update(SimpleNamespace(enabled=False), CS, 1) == []
  assert controller.config_request is None
  assert params.get("TeslaRadarConfigRequest") is None
  wait_for_param(params, "TeslaRadarConfigResult", ",rejected,")


def test_ars408_filter_write_queries_before_modifying():
  params = Params()
  request_id = str(int(time.monotonic() * 1000))
  params.put("TeslaRadarFilterRequest", f"{request_id},0,1,0,48")
  params.put_int("TeslaRadarFilterStateSeq", 0)
  controller = make_ars408_controller()
  CS = SimpleNamespace(out=SimpleNamespace(
    vEgoRaw=0.0, yawRate=0.0, steeringAngleDeg=0.0, canValid=True,
    gearShifter=structs.CarState.GearShifter.park, standstill=True,
  ))

  query = controller.update(SimpleNamespace(enabled=False), CS, 1)
  assert [(address, len(data), bus) for address, data, bus in query] == [(0x202, 5, ARS408_BUS)]
  assert params.get("TeslaRadarFilterRequest") is not None
  params.put("TeslaRadarFilterState", "0,1,0,32")
  params.put_int("TeslaRadarFilterStateSeq", 1)
  assert controller.update(SimpleNamespace(enabled=False), CS, 2) == []

  assert controller.update(SimpleNamespace(enabled=True), CS, 3) == []
  assert params.get("TeslaRadarFilterRequest") is not None
  wait_for_param(params, "TeslaRadarFilterResult", ",waiting,openpilot must be disengaged")

  write = controller.update(SimpleNamespace(enabled=False), CS, 4)
  assert [(address, len(data), bus) for address, data, bus in write] == [(0x202, 5, ARS408_BUS)]
  params.put("TeslaRadarFilterState", "0,1,0,48")
  params.put_int("TeslaRadarFilterStateSeq", 2)
  assert controller.update(SimpleNamespace(enabled=False), CS, 5) == []
  wait_for_param(params, "TeslaRadarFilterResult", ",applied,0")
  assert params.get("TeslaRadarFilterRequest") is None


def test_ars408_nvm_write_occurs_only_after_state_confirmation():
  params = Params()
  request_id = str(int(time.monotonic() * 1000))
  params.put("TeslaRadarConfigRequest", f"{request_id},send_extended,1,1")
  params.put_int("TeslaRadarStateSeq", 0)
  controller = make_ars408_controller()
  CS = SimpleNamespace(out=SimpleNamespace(
    vEgoRaw=0.0, yawRate=0.0, steeringAngleDeg=0.0, canValid=True,
    gearShifter=structs.CarState.GearShifter.park, standstill=True,
  ))

  apply_send = controller.update(SimpleNamespace(enabled=False), CS, 1)
  assert [(address, len(data), bus) for address, data, bus in apply_send] == [(0x200, 8, ARS408_BUS)]
  assert apply_send[0][1][0] == 0x20

  params.put_int("TeslaRadarStateExtended", 1)
  params.put_int("TeslaRadarStateSeq", 1)
  assert controller.update(SimpleNamespace(enabled=True), CS, 2) == []
  assert params.get("TeslaRadarConfigRequest") is not None
  wait_for_param(params, "TeslaRadarConfigResult", ",waiting,openpilot must be disengaged")

  nvm_send = controller.update(SimpleNamespace(enabled=False), CS, 3)
  assert [(address, len(data), bus) for address, data, bus in nvm_send] == [(0x200, 8, ARS408_BUS)]
  assert nvm_send[0][1][0] == 0x80
  wait_for_param(params, "TeslaRadarConfigResult", ",nvm_sent,")
  assert params.get("TeslaRadarConfigRequest") is None


def test_radar_sequence_continues_across_card_restarts():
  params = Params()
  params.put_int("TeslaRadarStateSeq", 123)
  params.put_int("TeslaRadarFilterStateSeq", 45)
  CP = structs.CarParams()
  CP.radarUnavailable = False
  radar = ARS408RadarInterface(CP)
  assert radar.radar_state_seq == 123
  assert radar.filter_state_seq == 45
