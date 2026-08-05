from opendbc.car import structs
from opendbc.car.tesla.radar_interface import (
  ARS408_EXTENDED, ARS408_GENERAL, ARS408_QUALITY, ARS408_TRACK_GRACE_CYCLES,
  RadarInterface, object_is_usable,
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


def test_incomplete_object_cycle_is_not_reported_as_can_disconnect():
  radar = RadarInterface.__new__(RadarInterface)
  radar.incomplete_cycles = 0
  radar.last_logged_incomplete = 0
  radar.expected_objects = 2
  radar.part_counts = {ARS408_GENERAL: 1, ARS408_QUALITY: 0}
  radar.part_ids = {ARS408_GENERAL: {1}, ARS408_QUALITY: set()}
  radar.pts = {}
  radar.last_radar_state = None
  radar.rcp = type("FakeParser", (), {"can_valid": True})()

  result = radar._incomplete_result()

  assert not result.errors.canError
  assert radar.incomplete_cycles == 1


def make_result_radar(points=None):
  radar = RadarInterface.__new__(RadarInterface)
  radar.expected_objects = 0
  radar.cycle_invalid = False
  radar.part_counts = {ARS408_GENERAL: 0, ARS408_QUALITY: 0}
  radar.part_ids = {ARS408_GENERAL: set(), ARS408_QUALITY: set()}
  radar.pts = points or {}
  radar.track_miss_counts = {track_id: 0 for track_id in radar.pts}
  radar.incomplete_cycles = 0
  radar.last_logged_incomplete = 0
  radar.last_radar_state = None
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
