import numpy as np

from cereal import car
from cereal import messaging
from cereal.messaging import SubMaster, PubMaster
from openpilot.selfdrive.ui.soundd import MIN_VOLUME, SELFDRIVE_STATE_TIMEOUT, Soundd, check_selfdrive_timeout_alert

import time

AudibleAlert = car.CarControl.HUDControl.AudibleAlert


class TestSoundd:
  def test_get_sound_data_fills_buffer_across_loop_boundary(self):
    soundd = Soundd.__new__(Soundd)
    soundd.enabled = False
    soundd.current_alert = AudibleAlert.promptRepeat
    soundd.current_volume = MIN_VOLUME
    soundd.current_sound_frame = 0
    soundd.loaded_sounds = {AudibleAlert.promptRepeat: np.array([1.0, 2.0, 3.0], dtype=np.float32)}

    actual = soundd.get_sound_data(5)

    np.testing.assert_array_equal(actual, np.array([1.0, 2.0, 3.0, 1.0, 2.0], dtype=np.float32) * MIN_VOLUME)
    assert soundd.current_sound_frame == 5

  def test_alert_can_clear_exactly_after_one_play(self):
    soundd = Soundd.__new__(Soundd)
    soundd.current_alert = AudibleAlert.engage
    soundd.current_sound_frame = 3
    soundd.loaded_sounds = {AudibleAlert.engage: np.zeros(3, dtype=np.float32)}

    soundd.update_alert(AudibleAlert.none)

    assert soundd.current_alert == AudibleAlert.none
    assert soundd.current_sound_frame == 0

  def test_check_selfdrive_timeout_alert(self):
    sm = SubMaster(['selfdriveState', 'selfdriveStateSP'])
    pm = PubMaster(['selfdriveState', 'selfdriveStateSP'])

    for _ in range(100):
      cs = messaging.new_message('selfdriveState')
      cs.selfdriveState.enabled = True

      pm.send("selfdriveState", cs)

      time.sleep(0.01)

      sm.update(0)

      assert not check_selfdrive_timeout_alert(sm)

    for _ in range(SELFDRIVE_STATE_TIMEOUT * 110):
      sm.update(0)
      time.sleep(0.01)

    assert check_selfdrive_timeout_alert(sm)

  def test_check_selfdrive_timeout_alert_mads_lateral_only(self):
    sm = SubMaster(['selfdriveState', 'selfdriveStateSP'])
    pm = PubMaster(['selfdriveState', 'selfdriveStateSP'])

    for _ in range(100):
      cs = messaging.new_message('selfdriveState')
      cs.selfdriveState.enabled = False

      ss_sp = messaging.new_message('selfdriveStateSP')
      ss_sp.selfdriveStateSP.mads.enabled = True

      pm.send("selfdriveState", cs)
      pm.send("selfdriveStateSP", ss_sp)

      time.sleep(0.01)

      sm.update(0)

      assert not check_selfdrive_timeout_alert(sm)

    for _ in range(SELFDRIVE_STATE_TIMEOUT * 110):
      sm.update(0)
      time.sleep(0.01)

    assert check_selfdrive_timeout_alert(sm)

  # TODO: add test with micd for checking that soundd actually outputs sounds
