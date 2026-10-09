import unittest
from types import SimpleNamespace

from opendbc.car import structs
from opendbc.sunnypilot.car.tesla.values import TeslaFlagsSP
from openpilot.selfdrive.controls.radard import RadarD


class SubMasterStub:
  def __init__(self, ars408=True):
    self.cp = SimpleNamespace(brand="tesla")
    self.cp_sp = SimpleNamespace(flags=TeslaFlagsSP.ARS408_RADAR if ars408 else 0)
    self.seen = {'modelV2': True}
    self.recv_frame = {'carState': 0}
    self.logMonoTime = {'radarTracks': 1_000_000_000, 'modelV2': 1_000_000_000}
    lead = SimpleNamespace(prob=0.0, x=[11.52], y=[0.0], v=[0.0], a=[0.0], xStd=[1.0], yStd=[1.0], vStd=[1.0])
    self.messages = {'carState': SimpleNamespace(vEgo=0.0),
                     'modelV2': SimpleNamespace(velocity=SimpleNamespace(x=[0.0]), leadsV3=[lead, lead])}

  def __getitem__(self, key):
    return self.messages[key]

  def all_checks(self):
    return True

  def advance(self, radar=True, elapsed_ns=75_000_000):
    self.logMonoTime['modelV2'] += elapsed_ns
    if radar:
      self.logMonoTime['radarTracks'] = self.logMonoTime['modelV2']


def radar_point(measured=True, v_rel=0.0):
  point = structs.RadarData.RadarPoint()
  point.trackId, point.dRel, point.yRel, point.vRel = 1, 10.0, 0.0, v_rel
  point.deprecated.measured = measured
  return structs.RadarData(points=[point])


class TestARS408Fusion(unittest.TestCase):
  def setup_radar(self, ars408=True):
    sm = SubMasterStub(ars408)
    return sm, RadarD(sm.cp, sm.cp_sp)

  def test_model_ticks_do_not_recount_or_refilter_same_package(self):
    sm, radar = self.setup_radar()
    radar.update(sm, radar_point())
    state = radar.tracks[1].kf.x
    for _ in range(3):
      sm.advance(radar=False, elapsed_ns=50_000_000)
      radar.update(sm, radar_point(v_rel=7.0))
    self.assertEqual(radar.tracks[1].cnt, 1)
    self.assertEqual(radar.tracks[1].kf.x, state)
    self.assertEqual(radar.tracks[1].vRel, 0.0)
    self.assertFalse(radar.radar_state.leadOne.present)

  def test_radar_only_lead_requires_three_distinct_measurements(self):
    sm, radar = self.setup_radar()
    for count in range(1, 4):
      radar.update(sm, radar_point())
      self.assertEqual(radar.tracks[1].cnt, count)
      self.assertEqual(radar.radar_state.leadOne.present, count == 3)
      sm.advance()

  def test_prediction_is_never_a_fused_measurement_and_recovery_resets_filter(self):
    sm, radar = self.setup_radar()
    radar.update(sm, radar_point(v_rel=10.0))
    for _ in range(10):
      sm.advance()
      radar.update(sm, radar_point(measured=False))
      self.assertEqual(radar.tracks[1].cnt, 0)
      self.assertFalse(radar.radar_state.leadOne.present)
    sm.advance()
    radar.update(sm, radar_point(v_rel=0.0))
    self.assertEqual(radar.tracks[1].cnt, 1)
    self.assertEqual(radar.tracks[1].vLeadK, 0.0)
    self.assertEqual(radar.tracks[1].aLeadK, 0.0)

  def test_prediction_cannot_create_fusion_track(self):
    sm, radar = self.setup_radar()
    radar.update(sm, radar_point(measured=False))
    self.assertEqual(radar.tracks, {})
    self.assertFalse(radar.radar_state.leadOne.present)

  def test_visual_confirmation_can_match_first_measurement_then_falls_back_on_prediction(self):
    sm, radar = self.setup_radar()
    sm['modelV2'].leadsV3[0].prob = 1.0
    radar.update(sm, radar_point())
    self.assertTrue(radar.radar_state.leadOne.radar)
    sm.advance()
    radar.update(sm, radar_point(measured=False))
    self.assertTrue(radar.radar_state.leadOne.present)
    self.assertFalse(radar.radar_state.leadOne.radar)

  def test_stale_or_faulted_package_cannot_supply_fused_lead(self):
    for fault in (False, True):
      sm, radar = self.setup_radar()
      sm['modelV2'].leadsV3[0].prob = 1.0
      radar.update(sm, radar_point())
      sm.advance(radar=False, elapsed_ns=200_000_001)
      rr = radar_point()
      if fault:
        sm.advance()
        rr.errors.canError = True
      radar.update(sm, rr)
      self.assertTrue(radar.radar_state.leadOne.present)
      self.assertFalse(radar.radar_state.leadOne.radar)

  def test_filter_uses_radar_package_interval(self):
    sm, radar = self.setup_radar()
    radar.update(sm, radar_point())
    sm.advance(elapsed_ns=80_000_000)
    radar.update(sm, radar_point(v_rel=2.0))
    self.assertEqual(radar.tracks[1].kf.A0_1, 0.08)
    self.assertEqual(radar.tracks[1].aLeadTau.dt, 0.08)

  def test_oem_radar_keeps_existing_measurement_and_model_tick_behavior(self):
    sm, radar = self.setup_radar(ars408=False)
    for _ in range(3):
      radar.update(sm, radar_point(measured=False))
    self.assertEqual(radar.tracks[1].cnt, 3)
    self.assertTrue(radar.radar_state.leadOne.present)
    self.assertEqual(radar.tracks[1].kf.A0_1, 0.05)

  def test_new_empty_package_removes_fusion_track(self):
    sm, radar = self.setup_radar()
    radar.update(sm, radar_point())
    sm.advance()
    radar.update(sm, structs.RadarData())
    self.assertEqual(radar.tracks, {})

  def test_long_gap_recovery_restarts_measurement_confirmation(self):
    sm, radar = self.setup_radar()
    for _ in range(3):
      radar.update(sm, radar_point(v_rel=10.0))
      sm.advance()
    sm.advance(elapsed_ns=250_000_000)
    radar.update(sm, radar_point())
    self.assertEqual(radar.tracks[1].cnt, 1)
    self.assertEqual(radar.tracks[1].vLeadK, 0.0)
    self.assertFalse(radar.radar_state.leadOne.present)

  def test_faulted_measurements_do_not_confirm_recovery(self):
    sm, radar = self.setup_radar()
    for _ in range(3):
      rr = radar_point()
      rr.errors.canError = True
      radar.update(sm, rr)
      sm.advance()
    self.assertEqual(radar.tracks, {})
    radar.update(sm, radar_point())
    self.assertEqual(radar.tracks[1].cnt, 1)
    self.assertFalse(radar.radar_state.leadOne.present)

  def test_reversed_timestamp_cannot_reuse_previous_fusion_track(self):
    sm, radar = self.setup_radar()
    sm['modelV2'].leadsV3[0].prob = 1.0
    radar.update(sm, radar_point())
    sm.logMonoTime['radarTracks'] -= 1
    radar.update(sm, radar_point())
    self.assertEqual(radar.tracks[1].cnt, 1)
    self.assertFalse(radar.radar_state.leadOne.radar)
