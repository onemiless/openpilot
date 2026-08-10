import pytest

from opendbc.can import CANPacker
from opendbc.car import structs
from opendbc.car.tesla.radar_interface import (
  ARS408_ADDRESS_OFFSET, ARS408_BUS, ARS408_EXTENDED, ARS408_GENERAL, ARS408_INTERFERENCE_CONFIRM_FRAMES,
  ARS408_QUALITY, ARS408_TRACK_GRACE_CYCLES, ARS408_STARTUP_GRACE_UPDATES, RadarInterface, object_is_usable,
  object_rejection_reason,
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


def test_merge_handover_reuses_logical_track_without_publishing_duplicate():
  point = structs.RadarData.RadarPoint()
  point.trackId = 10
  point.dRel = 40.0
  point.yRel = 0.2
  point.vRel = -1.0
  point.yvRel = 0.0
  point.measured = True
  radar = make_result_radar({10: point})
  radar.expected_objects = 2
  radar._decode_cycle = lambda _timestamp: {
    10: object_data(Obj_MeasState=4, Obj_DistLong=40.1, Obj_DistLat=-0.2, Obj_VrelLong=-1.0),
    11: object_data(Obj_MeasState=5, Obj_DistLong=40.4, Obj_DistLat=-0.22, Obj_VrelLong=-1.1),
  }

  result = radar._build_result(1_000_000_000)

  assert [(pt.trackId, pt.measured) for pt in result.points] == [(10, True)]
  assert result.points[0].dRel == pytest.approx(40.4)


def test_new_overlapping_raw_target_does_not_create_second_logical_track():
  point = structs.RadarData.RadarPoint()
  point.trackId = 10
  point.dRel = 40.0
  point.yRel = 0.2
  point.vRel = -1.0
  point.yvRel = 0.0
  point.measured = True
  radar = make_result_radar({10: point})
  radar.expected_objects = 2
  radar._decode_cycle = lambda _timestamp: {
    10: object_data(Obj_DistLong=40.1, Obj_DistLat=-0.2, Obj_VrelLong=-1.0),
    11: object_data(Obj_DistLong=40.5, Obj_DistLat=-0.25, Obj_VrelLong=-1.1),
  }

  result = radar._build_result(1_000_000_000)

  assert [pt.trackId for pt in result.points] == [10]


def test_spatially_distinct_raw_targets_remain_separate():
  radar = make_result_radar()
  radar.expected_objects = 2
  radar._decode_cycle = lambda _timestamp: {
    10: object_data(Obj_DistLong=40.0, Obj_DistLat=0.0, Obj_VrelLong=-1.0),
    11: object_data(Obj_DistLong=47.0, Obj_DistLat=0.1, Obj_VrelLong=-1.2),
  }

  result = radar._build_result(1_000_000_000)

  assert sorted(pt.trackId for pt in result.points) == [10, 11]


def test_two_established_overlapping_tracks_are_not_merged_without_radar_merge_state():
  first = structs.RadarData.RadarPoint()
  first.trackId = 10
  first.dRel = 40.0
  first.yRel = 0.2
  first.vRel = -1.0
  first.yvRel = 0.0
  first.measured = True
  second = structs.RadarData.RadarPoint()
  second.trackId = 11
  second.dRel = 40.4
  second.yRel = 0.22
  second.vRel = -1.1
  second.yvRel = 0.0
  second.measured = True
  radar = make_result_radar({10: first, 11: second})
  radar.expected_objects = 2
  radar._decode_cycle = lambda _timestamp: {
    10: object_data(Obj_DistLong=40.1, Obj_DistLat=-0.2, Obj_VrelLong=-1.0),
    11: object_data(Obj_DistLong=40.5, Obj_DistLat=-0.22, Obj_VrelLong=-1.1),
  }

  result = radar._build_result(1_000_000_000)

  assert sorted(pt.trackId for pt in result.points) == [10, 11]


def test_missing_raw_id_hands_over_to_tightly_colocated_replacement():
  point = structs.RadarData.RadarPoint()
  point.trackId = 10
  point.dRel = 40.0
  point.yRel = 0.2
  point.vRel = -1.0
  point.yvRel = 0.0
  point.measured = True
  radar = make_result_radar({10: point})
  radar.expected_objects = 1
  radar._decode_cycle = lambda _timestamp: {
    11: object_data(Obj_DistLong=40.4, Obj_DistLat=-0.22, Obj_VrelLong=-1.1),
  }

  result = radar._build_result(1_000_000_000)

  assert [(pt.trackId, pt.measured) for pt in result.points] == [(10, True)]


def test_reused_raw_id_gets_new_logical_track_after_previous_target_expires():
  point = structs.RadarData.RadarPoint()
  point.trackId = 7
  point.dRel = 40.0
  point.yRel = 0.0
  point.vRel = 0.0
  point.yvRel = 0.0
  point.measured = True
  radar = make_result_radar({7: point})

  for _ in range(ARS408_TRACK_GRACE_CYCLES + 1):
    radar._build_result(1_000_000_000)
  radar.expected_objects = 1
  radar._decode_cycle = lambda _timestamp: {7: object_data(Obj_DistLong=60.0)}

  result = radar._build_result(1_100_000_000)

  assert len(result.points) == 1
  assert result.points[0].trackId >= 256


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


def test_non_critical_radar_configuration_differences_do_not_request_takeover():
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
    "RadarState_CtrlRelayCfg": 1,
    "RadarState_SortIndex": 2,
    "RadarState_RCS_Threshold": 1,
    "RadarState_RadarPowerCfg": 3,
    "RadarState_MaxDistanceCfg": 250,
    "RadarState_MotionRxState": 3,
  }
  radar.radar_state_frames = 10
  radar.last_fault_signature = None
  radar.interference_frames = 0
  result = structs.RadarData()

  radar._apply_radar_state_errors(result)

  assert not result.errors.wrongConfig
  assert not result.errors.radarFault
  assert not result.errors.radarUnavailableTemporary


@pytest.mark.parametrize(("field", "value"), (
  ("RadarState_SensorID", 1),
  ("RadarState_SendQualityCfg", 0),
  ("RadarState_OutputTypeCfg", 2),
  ("RadarState_MaxDistanceCfg", 300),
))
def test_critical_radar_configuration_differences_still_request_takeover(field, value):
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
  radar.last_radar_state[field] = value
  radar.radar_state_frames = 10
  radar.last_fault_signature = None
  radar.interference_frames = 0
  result = structs.RadarData()

  radar._apply_radar_state_errors(result)

  assert result.errors.wrongConfig


def test_interference_requires_confirmation_before_requesting_takeover():
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

  for _ in range(ARS408_INTERFERENCE_CONFIRM_FRAMES - 1):
    radar._update_interference_counter(radar.last_radar_state)
    unconfirmed = structs.RadarData()
    radar._apply_radar_state_errors(unconfirmed)
    assert not unconfirmed.errors.radarUnavailableTemporary

  radar._update_interference_counter(radar.last_radar_state)
  confirmed = structs.RadarData()
  radar._apply_radar_state_errors(confirmed)
  assert confirmed.errors.radarUnavailableTemporary

  radar.last_radar_state["RadarState_Interference"] = 0
  radar._update_interference_counter(radar.last_radar_state)
  recovered = structs.RadarData()
  radar._apply_radar_state_errors(recovered)
  assert not recovered.errors.radarUnavailableTemporary


def test_repeated_object_results_do_not_confirm_stale_interference_state():
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

  radar._update_interference_counter(radar.last_radar_state)
  for _ in range(ARS408_INTERFERENCE_CONFIRM_FRAMES * 2):
    result = structs.RadarData()
    radar._apply_radar_state_errors(result)
    assert not result.errors.radarUnavailableTemporary

  assert radar.interference_frames == 1


def test_runtime_max_distance_extended_and_output_are_dynamic():
  point = structs.RadarData.RadarPoint()
  point.trackId = 7
  point.dRel = 190.0
  point.yRel = 0.0
  point.aRel = 1.5
  point.objectClass = 1
  radar = RadarInterface.__new__(RadarInterface)
  radar.params = type("FakeParams", (), {"put_nonblocking": lambda *_args: None})()
  far_point = structs.RadarData.RadarPoint()
  far_point.trackId = 8
  far_point.dRel = 220.0
  radar.pts = {7: point, 8: far_point}
  radar.track_miss_counts = {7: 0, 8: 0}
  radar.raw_to_track_id = {7: 7, 8: 8}
  radar.cycle_started = True
  radar.expected_objects = 1
  radar.runtime_max_distance = 250
  radar.runtime_output_type = 1
  radar.runtime_extended_enabled = True
  radar.last_published_radar_config = None
  state = {
    "RadarState_MaxDistanceCfg": 200,
    "RadarState_OutputTypeCfg": 1,
    "RadarState_SendExtInfoCfg": 0,
    "RadarState_SendQualityCfg": 1,
    "RadarState_SensorID": 0,
    "RadarState_MotionRxState": 3,
    "RadarState_NVMReadStatus": 0,
    "RadarState_NVMwriteStatus": 0,
  }

  radar._apply_runtime_configuration(state)
  assert radar.runtime_max_distance == 200
  assert radar.runtime_extended_enabled is False
  assert list(radar.pts) == [7]
  assert radar.pts[7].aRel == 0.0
  assert radar.pts[7].objectClass == 7

  radar.pts = {7: point}
  state["RadarState_MaxDistanceCfg"] = 250
  state["RadarState_OutputTypeCfg"] = 0
  radar._apply_runtime_configuration(state)
  assert radar.runtime_output_type == 0
  assert radar.pts == {}
  assert radar.expected_objects == 0
