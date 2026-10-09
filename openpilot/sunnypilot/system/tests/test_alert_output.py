import os
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest

import openpilot.system.manager.process_config as process_config
from openpilot.sunnypilot.system.alert_output import BEEP_GAP_SECONDS, BEEP_PULSE_SECONDS, Beepd
from openpilot.sunnypilot.hardware.profile import HardwareProfile


@pytest.fixture
def beepd():
  beep = Beepd.__new__(Beepd)
  beep.mads_enabled = None
  beep.maneuver_initialized = False
  beep.maneuver_action = None
  beep.maneuver_pending_until = 0.0
  beep.dispatch_beep = Mock(return_value=True)
  return beep


def test_mads_initial_state_is_silent(beepd):
  beepd.update_mads(True)

  beepd.dispatch_beep.assert_not_called()


def test_mads_enable_and_disable_have_distinct_beeps(beepd):
  beepd.update_mads(False)
  beepd.update_mads(True)
  beepd.update_mads(True)
  beepd.update_mads(False)

  assert beepd.dispatch_beep.call_args_list == [call(beepd.engage), call(beepd.disengage)]


def maneuver(beepd, state=0, direction=0, turn=0, reason='', enabled=True, healthy=True):
  meta = SimpleNamespace(laneChangeState=SimpleNamespace(raw=state), laneChangeDirection=SimpleNamespace(raw=direction))
  model = SimpleNamespace(laneTurnDirection=SimpleNamespace(raw=turn), turnDecisionReason=reason)
  beepd.update_maneuver(meta, model, enabled=enabled, healthy=healthy)


def test_maneuver_beeps_at_start_not_preparation_and_once_through_finishing(beepd):
  maneuver(beepd)
  maneuver(beepd, 1, 1)
  beepd.dispatch_beep.assert_not_called()
  maneuver(beepd, 2, 1)
  maneuver(beepd, 2, 1)
  maneuver(beepd, 3, 1)
  maneuver(beepd)
  maneuver(beepd, 2, 1)  # Same direction/request/session may perform another action.
  assert beepd.dispatch_beep.call_args_list == [call(beepd.engage)] * 2


def test_turn_start_without_lane_ready_is_announced(beepd):
  maneuver(beepd)
  maneuver(beepd, turn=2, reason='turnWaiting')
  maneuver(beepd, turn=2, reason='turnActive')
  maneuver(beepd, turn=2, reason='turnActive')
  maneuver(beepd, reason='signalConsumed')
  maneuver(beepd, turn=1, reason='turnActive')
  assert beepd.dispatch_beep.call_args_list == [call(beepd.engage)] * 2


def test_initial_active_disabled_and_stale_states_are_silent(beepd):
  maneuver(beepd, 2, 1)
  maneuver(beepd)
  maneuver(beepd, 2, 2, enabled=False)
  maneuver(beepd, 2, 2)
  maneuver(beepd, healthy=False)
  maneuver(beepd, turn=1, reason='turnActive')
  beepd.dispatch_beep.assert_not_called()


def test_queue_full_retries_only_during_short_active_window(beepd, monkeypatch):
  clock = [100.0]
  monkeypatch.setattr('openpilot.sunnypilot.system.alert_output.time.monotonic', lambda: clock[0])
  beepd.dispatch_beep.side_effect = [False, True]
  maneuver(beepd)
  maneuver(beepd, 2, 1)
  clock[0] += 0.1
  maneuver(beepd, 2, 1)
  maneuver(beepd, 3, 1)
  assert beepd.dispatch_beep.call_count == 2
  beepd.dispatch_beep.side_effect = None
  beepd.dispatch_beep.return_value = False
  maneuver(beepd)
  maneuver(beepd, 2, 2)
  clock[0] += 0.6
  maneuver(beepd, 2, 2)
  assert beepd.dispatch_beep.call_count == 3


def test_cancelled_action_does_not_retry_pending_beep(beepd):
  beepd.dispatch_beep.return_value = False
  maneuver(beepd)
  maneuver(beepd, 2, 1)
  maneuver(beepd)
  maneuver(beepd)
  assert beepd.dispatch_beep.call_count == 1


def test_actual_message_entry_requires_fresh_models_and_lateral_control(beepd):
  beepd.settings_cache = SimpleNamespace(read=lambda: SimpleNamespace(lane_change_buzzer_enabled=True))
  meta = SimpleNamespace(laneChangeState=SimpleNamespace(raw=0), laneChangeDirection=SimpleNamespace(raw=0))
  turn = SimpleNamespace(laneTurnDirection=SimpleNamespace(raw=0), turnDecisionReason='')
  messages = {'modelV2': SimpleNamespace(meta=meta), 'modelDataV2SP': turn,
              'carControl': SimpleNamespace(latActive=True)}
  sm = Mock()
  sm.updated = {'selfdriveState': False, 'selfdriveStateSP': False, 'modelV2': True, 'modelDataV2SP': True}
  sm.__getitem__ = Mock(side_effect=messages.__getitem__)
  sm.all_checks.return_value = True
  beepd.get_audible_alert(sm)
  meta.laneChangeState.raw, meta.laneChangeDirection.raw = 2, 1
  beepd.get_audible_alert(sm)
  beepd.get_audible_alert(sm)
  beepd.dispatch_beep.assert_called_once_with(beepd.engage)
  sm.all_checks.assert_called_with(['modelV2', 'modelDataV2SP', 'carControl'])
  beepd.dispatch_beep.reset_mock()
  sm.all_checks.return_value = False
  beepd.get_audible_alert(sm)
  sm.all_checks.return_value = True
  beepd.get_audible_alert(sm)  # Already-active state after an outage is not replayed.
  messages['carControl'].latActive = False
  meta.laneChangeDirection.raw = 2
  beepd.get_audible_alert(sm)
  beepd.dispatch_beep.assert_not_called()

def test_warning_and_prompt_repeat_follow_legacy_beep_rules(beepd, monkeypatch):
  from opendbc.car.structs import car

  alert = car.CarControl.HUDControl.AudibleAlert
  beepd.current_alert = alert.none
  beepd.prompt_suppress_until = 0
  timestamps = iter((100.0, 100.5, 101.0, 101.5, 102.0, 102.5, 111.0, 111.5))
  monkeypatch.setattr("openpilot.sunnypilot.system.alert_output.time.monotonic", lambda: next(timestamps))

  beepd.update_alert(alert.warningSoft)
  beepd.update_alert(alert.none)
  beepd.update_alert(alert.promptRepeat)
  beepd.update_alert(alert.none)
  beepd.update_alert(alert.promptRepeat)
  beepd.update_alert(alert.none)
  beepd.update_alert(alert.promptRepeat)
  beepd.update_alert(alert.none)

  assert beepd.dispatch_beep.call_args_list == [
    call(beepd.warning),
    call(beepd.engage),
    call(beepd.engage),
  ]


def test_mads_beeps_use_very_short_pulses(monkeypatch):
  assert BEEP_PULSE_SECONDS == pytest.approx(0.010)
  beep = Beepd.__new__(Beepd)
  beep._beep = Mock()
  sleep = Mock()
  monkeypatch.setattr("openpilot.sunnypilot.system.alert_output.time.sleep", sleep)

  beep.engage()
  assert beep._beep.call_args_list == [call(True), call(False)]
  sleep.assert_called_once_with(BEEP_PULSE_SECONDS)

  beep._beep.reset_mock()
  sleep.reset_mock()
  beep.disengage()
  assert beep._beep.call_args_list == [call(True), call(False), call(True), call(False)]
  assert sleep.call_args_list == [call(BEEP_PULSE_SECONDS), call(BEEP_GAP_SECONDS), call(BEEP_PULSE_SECONDS)]

  beep._beep.reset_mock()
  sleep.reset_mock()
  beep.warning()
  assert beep._beep.call_args_list == [call(True), call(False)] * 3
  assert sleep.call_args_list == [
    call(BEEP_PULSE_SECONDS), call(BEEP_GAP_SECONDS),
    call(BEEP_PULSE_SECONDS), call(BEEP_GAP_SECONDS),
    call(BEEP_PULSE_SECONDS),
  ]


def test_gpio_edges_use_persistent_fd_without_subprocess(monkeypatch):
  beep = Beepd.__new__(Beepd)
  beep.gpio_fd = 42
  run = Mock()
  seek = Mock()
  write = Mock(return_value=1)
  monkeypatch.setattr("openpilot.sunnypilot.system.alert_output.subprocess.run", run)
  monkeypatch.setattr("openpilot.sunnypilot.system.alert_output.os.lseek", seek)
  monkeypatch.setattr("openpilot.sunnypilot.system.alert_output.os.write", write)

  beep._beep(True)
  beep._beep(False)

  run.assert_not_called()
  assert seek.call_args_list == [call(42, 0, os.SEEK_SET), call(42, 0, os.SEEK_SET)]
  assert write.call_args_list == [call(42, b"1"), call(42, b"0")]


def test_gpio_unavailable_and_short_write_are_reported(monkeypatch):
  beep = Beepd.__new__(Beepd)
  beep.gpio_fd = None
  with pytest.raises(OSError, match='unavailable'):
    beep._beep(True)
  beep.gpio_fd = 42
  monkeypatch.setattr('openpilot.sunnypilot.system.alert_output.os.lseek', Mock())
  monkeypatch.setattr('openpilot.sunnypilot.system.alert_output.os.write', Mock(return_value=0))
  with pytest.raises(OSError, match='short'):
    beep._beep(True)


def test_worker_survives_failed_output_and_queue_reports_full(beepd):
  import queue
  beepd.beep_queue = queue.Queue(maxsize=2)
  fail = Mock(side_effect=OSError('edge failed'))
  succeed = Mock()
  beepd.beep_queue.put(fail)
  beepd.beep_queue.put(succeed)
  # Test the real worker with a bounded end-of-input, never start a GPIO thread.
  original_get = beepd.beep_queue.get
  beepd.beep_queue.get = Mock(side_effect=[original_get(), original_get(), KeyboardInterrupt()])
  with pytest.raises(KeyboardInterrupt):
    beepd._worker()
  fail.assert_called_once()
  succeed.assert_called_once()
  assert beepd.beep_queue.unfinished_tasks == 0
  assert Beepd.dispatch_beep(beepd, succeed)
  assert Beepd.dispatch_beep(beepd, succeed)
  assert not Beepd.dispatch_beep(beepd, succeed)


def test_standard_profile_never_probes_gpio42(monkeypatch):
  run = Mock()
  monkeypatch.setattr("openpilot.sunnypilot.system.alert_output.get_hardware_profile",
                      lambda: HardwareProfile.STANDARD)
  monkeypatch.setattr("openpilot.sunnypilot.system.alert_output.subprocess.run", run)
  monkeypatch.setattr("openpilot.sunnypilot.system.alert_output.threading.Thread.start", lambda _: None)

  beep = Beepd()

  assert beep.gpio_fd is None
  run.assert_not_called()


def test_c3xl_buzzer_process_is_always_on_without_enable_param(monkeypatch):
  params = Mock()
  monkeypatch.setattr(process_config, "PC", False)
  monkeypatch.setattr(process_config, "get_hardware_profile", lambda: HardwareProfile.C3XL, raising=False)

  assert process_config.use_external_buzzer(False, params, Mock())
  assert process_config.use_external_buzzer(True, params, Mock())
  params.get_bool.assert_not_called()

  monkeypatch.setattr(process_config, "get_hardware_profile", lambda: HardwareProfile.STANDARD)
  assert not process_config.use_external_buzzer(False, params, Mock())


def test_beep_subscription_frequency_matches_worker_rate(monkeypatch, beepd):
  sm = Mock()
  subscriber = Mock(return_value=sm)
  ratekeeper = Mock(return_value=Mock(keep_time=Mock(side_effect=StopIteration)))
  monkeypatch.setattr('openpilot.sunnypilot.system.alert_output.messaging.SubMaster', subscriber)
  monkeypatch.setattr('openpilot.sunnypilot.system.alert_output.Ratekeeper', ratekeeper)
  beepd.get_audible_alert = Mock()
  with pytest.raises(StopIteration):
    beepd.beepd_thread()
  subscriber.assert_called_once_with(['selfdriveState', 'selfdriveStateSP', 'modelV2', 'modelDataV2SP', 'carControl'], frequency=20)
  ratekeeper.assert_called_once_with(20)
  sm.update.assert_called_once_with(0)
  beepd.get_audible_alert.assert_called_once_with(sm)
