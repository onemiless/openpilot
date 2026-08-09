import pytest

from opendbc.can import CANPacker
from opendbc.car import structs
from opendbc.car.tesla.radar_interface import (
  ARS408_ADDRESS_OFFSET, ARS408_BUS, ARS408_EXTENDED, ARS408_GENERAL, ARS408_QUALITY, ARS408_TRACK_GRACE_CYCLES,
  ARS408_STARTUP_GRACE_UPDATES, RadarInterface, object_is_usable, object_rejection_reason,
)


def object_data(**overrides):
  obj = {
    "Obj_MeasState": 2,
    "Obj_ProbOfExist": 5,
    "Obj_DistLong": 40.0,
    "Obj_DistLat": 0.0,
    "Obj_VrelLong": 0.0,
    "Obj_VrelLat": 0.0,
    "Obj_DynProp": 0,
  }
  obj.update(overrides)
  return obj


def test_rejects_low_probability_and_new_predicted_targets():
  assert not object_is_usable(object_data(Obj_ProbOfExist=2))
  assert object_is_usable(object_data(Obj_ProbOfExist=2), previously_tracked=True)
  assert not object_is_usable(object_data(Obj_MeasState=3), previously_tracked=False)
  assert object_is_usable(object_data(Obj_MeasState=3), previously_tracked=True)


def test_filters_roadside_static_objects_but_keeps_adjacent_lane_and_stopped_targets():
  assert not object_is_usable(object_data(Obj_DynProp=1, Obj_DistLat=8.0, Obj_ProbOfExist=7))
  assert object_is_usable(object_data(Obj_DynProp=1, Obj_DistLat=3.7, Obj_ProbOfExist=5))
  assert object_is_usable(object_data(Obj_DynProp=7, Obj_DistLat=3.7, Obj_ProbOfExist=3))


def test_object_rejection_reason_is_stable_for_diagnostics():
  assert object_rejection_reason(object_data(Obj_MeasState=0)) == "invalid"
  assert object_rejection_reason(object_data(Obj_ProbOfExist=1)) == "low probability"
  assert object_rejection_reason(object_data(Obj_DistLong=301.0)) == "out of range"
  assert object_rejection_reason({}, timed_out=True) == "timeout"


def test_incomplete_object_cycle_is_not_reported_as_can_disconnect():
  radar = RadarInterface.__new__(RadarInterface)
  radar.incomplete_cycles = 0
  radar.last_logged_incomplete = 0
  radar.expected_objects = 2
  radar.part_counts = {ARS408_GENERAL: 1, ARS408_QUALITY: 0}
  radar.part_ids = {ARS408_GENERAL: {1}, ARS408_QUALITY: set()}
  radar.pts = {}
  radar.last_radar_state = None
  radar.radar_mode = 2
  radar.last_rejection_reasons = {}
  radar.v_ego = 0.0
  radar.rcp = type("FakeParser", (), {"can_valid": True})()

  result = radar._incomplete_result()

  assert not result.errors.canError
  assert radar.incomplete_cycles == 1


def test_monitor_mode_never_publishes_cached_points_on_incomplete_cycle():
  point = structs.RadarData.RadarPoint()
  point.trackId = 7
  radar = RadarInterface.__new__(RadarInterface)
  radar.incomplete_cycles = 0
  radar.last_logged_incomplete = 0
  radar.expected_objects = 1
  radar.part_counts = {ARS408_GENERAL: 1, ARS408_QUALITY: 0}
  radar.part_ids = {ARS408_GENERAL: {7}, ARS408_QUALITY: set()}
  radar.pts = {7: point}
  radar.last_radar_state = None
  radar.radar_mode = 1
  radar.last_rejection_reasons = {}
  radar.v_ego = 0.0
  radar.rcp = type("FakeParser", (), {"can_valid": True})()

  result = radar._incomplete_result()

  assert len(result.points) == 0


def make_result_radar(points=None):
  radar = RadarInterface.__new__(RadarInterface)
  radar.v_ego = 0.0
  radar.expected_objects = 0
  radar.cycle_invalid = False
  radar.part_counts = {ARS408_GENERAL: 0, ARS408_QUALITY: 0}
  radar.part_ids = {ARS408_GENERAL: set(), ARS408_QUALITY: set()}
  radar.pts = points or {}
  radar.track_miss_counts = {track_id: 0 for track_id in radar.pts}
  radar.incomplete_cycles = 0
  radar.last_logged_incomplete = 0
  radar.last_radar_state = None
  radar.radar_mode = 2
  radar.last_rejection_reasons = {}
  radar.rcp = type("FakeParser", (), {"can_valid": True})()
  radar._decode_cycle = lambda _timestamp: {}
  return radar


def test_zero_object_cycles_publish_empty_data_without_can_error():
  radar = make_result_radar()

  result = radar._build_result(1_000_000_000)

  assert len(result.points) == 0
  assert not result.errors.canError


def test_existing_track_survives_brief_empty_cycle_then_expires():
  point = structs.RadarData.RadarPoint()
  point.trackId = 7
  point.dRel = 35.0
  point.measured = True
  radar = make_result_radar({7: point})

  for _ in range(ARS408_TRACK_GRACE_CYCLES):
    result = radar._build_result(1_000_000_000)
    assert [pt.trackId for pt in result.points] == [7]
    assert not result.points[0].measured

  result = radar._build_result(1_000_000_000)
  assert len(result.points) == 0


def test_partial_cycle_keeps_objects_with_both_general_and_quality_frames():
  radar = RadarInterface.__new__(RadarInterface)
  radar.expected_objects = 2
  radar.cycle_frames = []
  radar.part_ids = {ARS408_GENERAL: {1, 2}, ARS408_QUALITY: {1}, ARS408_EXTENDED: set()}
  radar.part_counts = {ARS408_GENERAL: 2, ARS408_QUALITY: 1, ARS408_EXTENDED: 0}
  radar.rcp = type("FakeParser", (), {
    "update": lambda *_args: None,
    "vl_all": {
      "Obj_1_General": {
        "Obj_ID": [1, 2], "Obj_DistLong": [30.0, 60.0], "Obj_DistLat": [0.0, 3.5],
        "Obj_VrelLong": [0.0, 0.0], "Obj_VrelLat": [0.0, 0.0], "Obj_RCS": [10.0, 10.0],
        "Obj_DynProp": [0, 0],
      },
      "Obj_2_Quality": {
        "Obj_ID": [1], "Obj_ProbOfExist": [5], "Obj_MeasState": [2],
      },
      "Obj_3_Extended": {
        "Obj_ID": [], "Obj_ArelLong": [], "Obj_Class": [],
      },
    },
  })()

  objects = radar._decode_cycle(1_000_000_000)

  assert set(objects) == {1}
  assert objects[1]["Obj_DistLong"] == 30.0
  assert objects[1]["Obj_ProbOfExist"] == 5


def test_raw_sensor_zero_extended_cycle_produces_classified_radar_point():
  cp = structs.CarParams()
  cp.radarUnavailable = False
  radar = RadarInterface(cp)
  packer = CANPacker("ARS408")

  def shifted_frame(message, values):
    address, data, bus = packer.make_can_msg(message, ARS408_BUS, values)
    return address + ARS408_ADDRESS_OFFSET, data, bus

  status = shifted_frame("Obj_0_Status", {"Obj_NofObjects": 1, "Obj_InterfaceVersion": 1})
  general = shifted_frame("Obj_1_General", {
    "Obj_ID": 7, "Obj_DistLong": 42.0, "Obj_DistLat": -1.5,
    "Obj_VrelLong": -2.0, "Obj_VrelLat": 0.25, "Obj_DynProp": 0,
  })
  quality = shifted_frame("Obj_2_Quality", {"Obj_ID": 7, "Obj_ProbOfExist": 5, "Obj_MeasState": 2})
  extended = shifted_frame("Obj_3_Extended", {"Obj_ID": 7, "Obj_ArelLong": -0.5, "Obj_Class": 1})

  assert radar.update([(1_000_000_000, [status])]) is None
  assert radar.update([(1_010_000_000, [general, quality, extended])]) is None
  result = radar.update([(1_070_000_000, [status])])

  assert result is not None
  assert len(result.points) == 1
  assert result.points[0].trackId == 7
  assert result.points[0].dRel == 42.0
  assert result.points[0].yRel == pytest.approx(1.5, abs=0.11)
  assert result.points[0].vRel == -2.0
  assert result.points[0].aRel == pytest.approx(-0.5, abs=0.02)
  assert result.points[0].objectClass == 1
  assert result.points[0].measured


def test_missing_ars408_status_is_detected_independently_of_shared_can_validity():
  radar = RadarInterface.__new__(RadarInterface)
  radar.update_count = ARS408_STARTUP_GRACE_UPDATES + 1
  radar.last_status_update = None
  radar.last_radar_state_update = radar.update_count

  assert radar._missing_can_signature() == (True, False)


def test_monitor_mode_decodes_objects_without_publishing_fusion_points():
  radar = make_result_radar()
  radar.radar_mode = 1
  radar._decode_cycle = lambda _timestamp: {7: object_data()}

  result = radar._build_result(1_000_000_000)

  assert result.objectCount == 0
  assert len(radar.pts) == 1
  assert radar.pts[7].objectClass == 7
  assert len(result.points) == 0


def test_radar_state_accepts_250_m_config_and_ignores_missing_motion_inputs():
  radar = RadarInterface.__new__(RadarInterface)
  radar.last_radar_state = {
    "RadarState_Interference": 0,
    "RadarState_Temperature_Error": 0,
    "RadarState_Temporary_Error": 0,
    "RadarState_Voltage_Error": 0,
    "RadarState_Persistent_Error": 0,
    "RadarState_SensorID": 0,
    "RadarState_OutputTypeCfg": 1,
    "RadarState_SendQualityCfg": 1,
    "RadarState_SendExtInfoCfg": 1,
    "RadarState_CtrlRelayCfg": 0,
    "RadarState_SortIndex": 1,
    "RadarState_RCS_Threshold": 0,
    "RadarState_RadarPowerCfg": 0,
    "RadarState_MaxDistanceCfg": 250,
    "RadarState_MotionRxState": 3,
  }
  radar.radar_state_frames = 10
  radar.last_fault_signature = None
  result = structs.RadarData()

  radar._apply_radar_state_errors(result)

  assert not result.errors.wrongConfig
  assert not result.errors.radarFault
  assert not result.errors.radarUnavailableTemporary

  radar.last_radar_state["RadarState_MaxDistanceCfg"] = 300
  radar._apply_radar_state_errors(result)
  assert result.errors.wrongConfig


def test_single_interference_state_does_not_request_takeover():
  radar = RadarInterface.__new__(RadarInterface)
  radar.last_radar_state = {
    "RadarState_Interference": 1,
    "RadarState_Temperature_Error": 0,
    "RadarState_Temporary_Error": 0,
    "RadarState_Voltage_Error": 0,
    "RadarState_Persistent_Error": 0,
    "RadarState_SensorID": 0,
    "RadarState_OutputTypeCfg": 1,
    "RadarState_SendQualityCfg": 1,
    "RadarState_SendExtInfoCfg": 1,
    "RadarState_CtrlRelayCfg": 0,
    "RadarState_SortIndex": 1,
    "RadarState_RCS_Threshold": 0,
    "RadarState_RadarPowerCfg": 0,
    "RadarState_MaxDistanceCfg": 250,
    "RadarState_MotionRxState": 3,
  }
  radar.radar_state_frames = 10
  radar.last_fault_signature = None
  radar.interference_frames = 0

  first = structs.RadarData()
  radar._apply_radar_state_errors(first)
  assert not first.errors.radarUnavailableTemporary

  second = structs.RadarData()
  radar._apply_radar_state_errors(second)
  assert second.errors.radarUnavailableTemporary

  radar.last_radar_state["RadarState_Interference"] = 0
  recovered = structs.RadarData()
  radar._apply_radar_state_errors(recovered)
  assert not recovered.errors.radarUnavailableTemporary
