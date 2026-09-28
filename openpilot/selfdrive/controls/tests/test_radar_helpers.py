import pytest

from openpilot.selfdrive.controls.lib.radar_helpers import is_radar_velocity_sane


def test_1211_tunnel_stationary_reflection_conflicting_with_moving_vision_is_rejected():
  # rlog segment 10: vEgo 62.1 km/h, track 4409 vRel -13.75 m/s,
  # while the model lead was moving at 17.97 m/s.
  assert is_radar_velocity_sane(62.1 / 3.6, -13.75, 17.97)
  assert not is_radar_velocity_sane(62.1 / 3.6, -13.75, 17.97, ars408_stationary_conflict_guard=True)


@pytest.mark.parametrize(("v_ego", "v_rel", "vision_speed"), [
  (10.0, -10.0, 0.0),
  (10.0, -1.0, 9.5),
  (10.0, -5.0, 1.0),
])
def test_ars408_guard_preserves_non_conflicting_leads(v_ego, v_rel, vision_speed):
  assert is_radar_velocity_sane(v_ego, v_rel, vision_speed, ars408_stationary_conflict_guard=True)


@pytest.mark.parametrize(("radar_speed", "vision_speed", "expected"), [
  (5.0, 15.0, True),
  (4.99, 14.99, False),
  (4.99, 14.989, True),
])
def test_ars408_stationary_conflict_boundaries(radar_speed, vision_speed, expected):
  assert is_radar_velocity_sane(
    v_ego=10.0,
    v_rel=radar_speed - 10.0,
    vision_lead_speed=vision_speed,
    ars408_stationary_conflict_guard=True,
  ) is expected
