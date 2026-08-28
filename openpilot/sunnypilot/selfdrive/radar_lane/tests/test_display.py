from types import SimpleNamespace as namespace

from openpilot.sunnypilot.selfdrive.radar_lane.display import (
  LaneDisplayTargetStabilizer,
  SIDE_LANE_ORDER,
  filter_static_side_clutter,
  format_target_label,
  matches_rendered_lead,
  rendered_radar_track_ids,
  select_lane_display_targets,
  should_render_second_lead,
)


def _target(track_id, lane_mask, d_rel, *, y_rel=0.0, d_path=None, v_rel=0.0, cut_in=False, crossing=-1.0,
            object_class=7, dynamic_property=4):
  return namespace(
    present=True,
    trackId=track_id,
    laneMask=lane_mask,
    dRel=d_rel,
    yRel=y_rel,
    dPath=y_rel if d_path is None else d_path,
    vRel=v_rel,
    cutInCandidate=cut_in,
    timeToLaneCross=crossing,
    objectClass=object_class,
    dynamicProperty=dynamic_property,
  )


def test_display_selects_one_unique_target_per_lane_and_prioritizes_cut_in():
  targets = [
    _target(1, 1, 8.0),
    _target(2, 1, 30.0, cut_in=True, crossing=0.8),
    _target(3, 2, 12.0),
    _target(4, 4, 10.0),
    _target(5, 4, 20.0, cut_in=True, crossing=1.2),
  ]

  assert [target.trackId for target in select_lane_display_targets(targets)] == [2, 3, 5]


def test_boundary_target_is_not_drawn_twice():
  boundary = _target(7, 3, 15.0, cut_in=True, crossing=0.0)
  center = _target(8, 2, 20.0)

  selected = select_lane_display_targets([boundary, center])

  assert [target.trackId for target in selected] == [7, 8]


def test_side_display_never_adds_a_center_lane_marker():
  targets = [_target(1, 1, 20.0), _target(2, 2, 15.0), _target(3, 4, 25.0)]

  assert [target.trackId for target in select_lane_display_targets(targets, SIDE_LANE_ORDER)] == [1, 3]


def test_static_roadside_cluster_is_hidden_but_isolated_and_center_stops_remain():
  targets = [
    _target(1, 4, 15.0, y_rel=-4.1, d_path=-4.0, v_rel=-20.0),
    _target(2, 4, 35.0, y_rel=-4.2, d_path=-4.1, v_rel=-20.2),
    _target(3, 4, 55.0, y_rel=-4.0, d_path=-3.9, v_rel=-19.8),
    _target(4, 1, 25.0, y_rel=3.6, d_path=3.6, v_rel=-20.0),
    _target(5, 2, 30.0, y_rel=0.0, d_path=0.0, v_rel=-20.0),
    _target(6, 1, 40.0, y_rel=3.5, d_path=3.5, v_rel=-5.0),
  ]

  assert [target.trackId for target in filter_static_side_clutter(targets, 20.0)] == [4, 5, 6]


def test_classified_vehicle_and_vru_are_not_removed_with_static_roadside_cluster():
  targets = [
    _target(1, 4, 15.0, d_path=-4.0, v_rel=-20.0, object_class=0, dynamic_property=1),
    _target(2, 4, 35.0, d_path=-4.1, v_rel=-20.0, object_class=6, dynamic_property=3),
    _target(3, 4, 55.0, d_path=-3.9, v_rel=-20.0, object_class=0, dynamic_property=5),
    _target(4, 4, 25.0, d_path=-4.0, v_rel=-20.0, object_class=2, dynamic_property=1),
    _target(5, 4, 45.0, d_path=-4.0, v_rel=-20.0, object_class=3, dynamic_property=1),
  ]

  assert [target.trackId for target in filter_static_side_clutter(targets, 20.0)] == [4, 5]


def test_target_label_reports_distance_and_estimated_absolute_speed():
  assert format_target_label(30.0, -2.0, 20.0, True) == "30m  65km/h"
  assert format_target_label(30.0, -2.0, 20.0, False) == "98ft  40mph"
  assert format_target_label(30.0, -2.0, 20.0, True, 2) == "货车  30m  65km/h"
  assert format_target_label(30.0, -2.0, 20.0, True, 3) == "行人  30m  65km/h"


def test_side_target_stabilizer_resists_small_closest_target_changes():
  stabilizer = LaneDisplayTargetStabilizer()
  assert [target.trackId for target in stabilizer.update([_target(1, 1, 30.0)])] == [1]
  stable = stabilizer.update([_target(1, 1, 30.0), _target(2, 1, 27.0)])
  assert [target.trackId for target in stable] == [1]


def test_side_target_stabilizer_switches_for_clear_distance_advantage_or_cut_in():
  stabilizer = LaneDisplayTargetStabilizer()
  stabilizer.update([_target(1, 1, 30.0)])
  closer = stabilizer.update([_target(1, 1, 30.0), _target(2, 1, 20.0)])
  assert [target.trackId for target in closer] == [2]

  cut_in = stabilizer.update([
    _target(2, 1, 20.0), _target(3, 1, 28.0, cut_in=True, crossing=0.8),
  ])
  assert [target.trackId for target in cut_in] == [3]


def test_side_target_stabilizer_follows_radar_track_lifecycle_without_ui_hold():
  stabilizer = LaneDisplayTargetStabilizer()
  stabilizer.update([_target(10, 4, 30.0, y_rel=-3.5)])
  assert stabilizer.update([]) == ()
  replacement = stabilizer.update([_target(20, 4, 32.0, y_rel=-3.2)])
  assert [target.trackId for target in replacement] == [20]


def test_existing_radar_chevrons_are_not_drawn_twice():
  radar_state = namespace(
    leadOne=namespace(present=True, radar=True, radarTrackId=7),
    leadTwo=namespace(present=True, radar=True, radarTrackId=8),
  )

  assert rendered_radar_track_ids(radar_state) == frozenset({7, 8})
  assert rendered_radar_track_ids(radar_state, include_lead_two=False) == frozenset({7})
  assert rendered_radar_track_ids(None) == frozenset()


def test_spatially_matching_lead_is_not_redrawn_when_track_ids_differ():
  radar_state = namespace(
    leadOne=_lead(track_id=80, d_rel=30.0, y_rel=-3.4),
    leadTwo=_lead(present=False),
  )

  assert matches_rendered_lead(_target(81, 4, 32.0, y_rel=-3.0), radar_state)
  assert not matches_rendered_lead(_target(82, 4, 40.0, y_rel=-3.0), radar_state)


def _lead(*, present=True, radar=True, track_id=-1, d_rel=20.0, y_rel=0.0):
  return namespace(present=present, radar=radar, radarTrackId=track_id, dRel=d_rel, yRel=y_rel)


def test_second_lead_with_same_radar_track_is_always_suppressed():
  assert not should_render_second_lead(_lead(track_id=4), _lead(track_id=4, d_rel=30.0), True)


def test_second_lead_uses_distance_hysteresis_for_unstable_association():
  lead_one = _lead(radar=False, d_rel=20.0)
  assert not should_render_second_lead(lead_one, _lead(radar=False, d_rel=24.0), False)
  assert should_render_second_lead(lead_one, _lead(radar=False, d_rel=24.0), True)
  assert should_render_second_lead(lead_one, _lead(radar=False, d_rel=26.0), False)
  assert not should_render_second_lead(lead_one, _lead(radar=False, d_rel=22.0), True)


def test_laterally_separate_second_lead_is_preserved():
  assert should_render_second_lead(_lead(d_rel=20.0, y_rel=-1.0), _lead(d_rel=20.0, y_rel=1.0), False)
