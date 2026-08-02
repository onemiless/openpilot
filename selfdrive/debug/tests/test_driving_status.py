from openpilot.selfdrive.debug.driving_status import _set_speed_kph


def test_set_speed_matches_device_hud_units_and_fallback():
  assert _set_speed_kph(110.0, 35.0) == 110.0
  assert _set_speed_kph(0.0, 35.0) == 35.0
