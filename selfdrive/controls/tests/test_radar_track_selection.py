from openpilot.selfdrive.controls.radard import Track


def make_track(d_rel_rate):
  track = Track.__new__(Track)
  track.measured = True
  track.cnt = 8
  track.in_lane_prob = 1.0
  track.dRel = 30.0
  track.dRel_rate = d_rel_rate
  return track


def test_mode_three_rejects_stationary_infrastructure_without_motion_inputs():
  # At 20 m/s ego speed, a fixed pole approaches at roughly -20 m/s.
  assert not make_track(-20.0).is_stable_radar_only_vehicle(20.0)


def test_mode_three_accepts_stable_moving_vehicle_without_vision_match():
  # A vehicle maintaining its range has approximately zero range rate.
  assert make_track(0.0).is_stable_radar_only_vehicle(20.0)


def test_mode_three_waits_for_track_stability():
  track = make_track(0.0)
  track.cnt = 3
  assert not track.is_stable_radar_only_vehicle(20.0)
