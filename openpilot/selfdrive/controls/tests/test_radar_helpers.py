import pytest
from types import SimpleNamespace as ns

from openpilot.selfdrive.controls.lib.radar_helpers import is_radar_velocity_sane
from openpilot.selfdrive.controls.radard import get_lead
from opendbc.sunnypilot.car.tesla.values import TeslaFlagsSP


def test_ars408_stationary_trace_conflicting_with_moving_vision_is_rejected():
  assert is_radar_velocity_sane(10.0, -9.37, 10.38)
  assert not is_radar_velocity_sane(10.0, -9.37, 10.38, ars408_stationary_conflict_guard=True)


@pytest.mark.parametrize(("radar_speed", "vision_speed"), [
  (0.63, 10.38), (0.62, 9.71), (-0.66, 9.33), (0.63, 10.53),
  (0.41, 10.28), (0.33, 10.25), (2.11, 10.51), (0.02, 8.90),
])
def test_all_documented_stationary_trace_conflicts_are_rejected(radar_speed, vision_speed):
  assert not is_radar_velocity_sane(
    v_ego=10.0,
    v_rel=radar_speed - 10.0,
    vision_lead_speed=vision_speed,
    ars408_stationary_conflict_guard=True,
  )


@pytest.mark.parametrize(("v_ego", "v_rel", "vision_speed"), [
  (10.0, -10.0, 0.0),  # radar and vision agree on a stopped vehicle
  (10.0, -1.0, 9.5),   # radar and vision agree on a moving lead
  (10.0, -5.0, 1.0),   # radar sees launch before vision catches up
])
def test_ars408_guard_preserves_non_conflicting_leads(v_ego, v_rel, vision_speed):
  assert is_radar_velocity_sane(v_ego, v_rel, vision_speed, ars408_stationary_conflict_guard=True)


@pytest.mark.parametrize(("radar_speed", "vision_speed", "expected"), [
  (3.0, 8.0, True),       # stationary threshold is strict
  (2.5, 7.5, False),      # speed delta threshold includes exactly 5 m/s
  (2.5, 7.499, True),
])
def test_ars408_stationary_conflict_boundaries(radar_speed, vision_speed, expected):
  assert is_radar_velocity_sane(
    v_ego=10.0,
    v_rel=radar_speed - 10.0,
    vision_lead_speed=vision_speed,
    ars408_stationary_conflict_guard=True,
  ) is expected


class FakeTrack:
  dRel = 30.0
  yRel = 0.0
  vRel = -9.37

  def get_RadarState(self, model_prob=0.0):
    return {"present": True, "radar": True, "dRel": self.dRel, "yRel": self.yRel,
            "vRel": self.vRel, "modelProb": model_prob}

  def potential_low_speed_lead(self, _v_ego):
    return False


def vision_lead():
  return ns(x=[31.52], xStd=[1.0], y=[0.0], yStd=[1.0],
            v=[10.38], vStd=[1.0], a=[0.0])


@pytest.mark.parametrize(("brand", "flags", "expect_radar"), [
  ("tesla", int(TeslaFlagsSP.ARS408_RADAR), False),
  ("tesla", 0, True),
  ("toyota", int(TeslaFlagsSP.ARS408_RADAR), True),
])
def test_get_lead_enables_stationary_conflict_guard_only_for_tesla_ars408(brand, flags, expect_radar):
  lead = get_lead(
    10.0, True, {1: FakeTrack()}, vision_lead(), 10.0, 0.9,
    ns(brand=brand), ns(flags=flags), low_speed_override=False,
  )
  assert lead["present"]
  assert lead["radar"] is expect_radar
