from types import SimpleNamespace

import pytest

from openpilot.selfdrive.controls.radard import RadarD


class FakeTrack:
  def __init__(self, identifier, d_rel, y_rel, v_lead):
    self.identifier = identifier
    self.dRel = d_rel
    self.yRel = y_rel
    self.vLead = v_lead
    self.in_lane_prob = 0.9
    self.in_lane_prob_future = 0.9
    self.cnt = 10
    self.cut_in_count = 0

  def get_RadarState(self, probability, _vision_y_rel):
    return {
      "status": True,
      "radar": True,
      "radarTrackId": self.identifier,
      "dRel": self.dRel,
      "yRel": self.yRel,
      "vRel": self.vLead - 25.0,
      "vLead": self.vLead,
      "vLat": 0.0,
      "dPath": 0.1,
      "modelProb": probability,
      "aLeadK": 0.0,
      "aLeadTau": 1.5,
      "aLead": 0.0,
      "fcw": False,
      "objectClass": 1,
      "radarTrackCnt": self.cnt,
    }


def run_compute_leads(second_distance):
  radar = RadarD.__new__(RadarD)
  radar.radar_state = SimpleNamespace(
    leadOne=SimpleNamespace(status=True, radar=True, radarTrackId=10, dRel=40.0, yRel=0.2, vRel=-1.0),
  )
  radar.lane_line_available = True
  model = SimpleNamespace(
    position=SimpleNamespace(x=[0.0] * 33),
    leadsV3=[SimpleNamespace(prob=0.9, y=[0.0])],
  )
  tracks = {
    10: FakeTrack(10, 40.0, 0.2, 24.0),
    11: FakeTrack(11, second_distance, 0.22, 23.9),
  }

  radar.compute_leads(3.0, 25.0, tracks, model)
  return radar.leadTwo


def test_overlapping_duplicate_cannot_become_lead_two():
  assert run_compute_leads(40.4) is None


def test_real_second_vehicle_remains_available_to_lead_two():
  lead_two = run_compute_leads(55.0)

  assert lead_two is not None
  assert lead_two["radarTrackId"] == 11
  assert lead_two["dRel"] == pytest.approx(47.0)
