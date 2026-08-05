from openpilot.sunnypilot.selfdrive.controls.lib.speed_limit import resolve_pcm_long_required_max


def test_metric_confirmation_speed_tracks_speed_limit_segment():
  assert round(resolve_pcm_long_required_max(True, 50, True) * 3.6) == 50
  assert round(resolve_pcm_long_required_max(True, 51, True) * 3.6) == 60
  assert round(resolve_pcm_long_required_max(True, 120, True) * 3.6) == 120


def test_imperial_confirmation_speed_tracks_speed_limit_segment():
  assert round(resolve_pcm_long_required_max(False, 35, True) / 0.44704) == 35
  assert round(resolve_pcm_long_required_max(False, 36, True) / 0.44704) == 40


def test_missing_limit_uses_safe_maximum_confirmation_speed():
  assert round(resolve_pcm_long_required_max(True, 0, False) * 3.6) == 130
  assert round(resolve_pcm_long_required_max(False, 0, False) / 0.44704) == 90
