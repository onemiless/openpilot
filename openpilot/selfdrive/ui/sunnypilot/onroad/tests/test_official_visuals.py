from types import SimpleNamespace

import pyray as rl

from openpilot.selfdrive.ui.sunnypilot.onroad import circular_alerts, speed_limit


def _speed_limit_renderer():
  renderer = object.__new__(speed_limit.SpeedLimitRenderer)
  renderer.speed_limit_valid = True
  renderer.speed_limit_last_valid = True
  renderer.speed_limit_final_last = 50
  renderer.speed = 40
  renderer.speed_limit_last = 50
  renderer.speed_limit_offset = 0
  return renderer


def test_speed_limit_sign_style_follows_units(monkeypatch):
  renderer = _speed_limit_renderer()
  calls = []
  renderer._render_vienna = lambda *args: calls.append("vienna")
  renderer._render_mutcd = lambda *args: calls.append("mutcd")
  monkeypatch.setattr(speed_limit.ui_state, "speed_limit_mode", speed_limit.SpeedLimitMode.information)

  monkeypatch.setattr(speed_limit.ui_state, "is_metric", True)
  renderer._draw_sign_main(rl.Rectangle(0, 0, 200, 200))
  assert calls == ["vienna"]

  calls.clear()
  monkeypatch.setattr(speed_limit.ui_state, "is_metric", False)
  renderer._draw_sign_main(rl.Rectangle(0, 0, 200, 200))
  assert calls == ["mutcd"]


def test_speed_limit_sign_width_follows_units(monkeypatch):
  renderer = _speed_limit_renderer()
  renderer._pre_active_fade = SimpleNamespace(alpha=1.0)
  renderer.speed_limit_assist_state = speed_limit.AssistState.disabled
  rendered_widths = []
  renderer._draw_sign_main = lambda rect, alpha: rendered_widths.append(rect.width)
  renderer._draw_ahead_info = lambda rect: None

  monkeypatch.setattr(speed_limit.ui_state, "speed_limit_mode", speed_limit.SpeedLimitMode.information)
  monkeypatch.setattr(speed_limit.ui_state, "is_metric", False)
  renderer._render(rl.Rectangle(0, 0, 1920, 1080))

  assert rendered_widths == [speed_limit.UI_CONFIG.set_speed_width_imperial]


def test_circular_alert_assets_use_official_size(monkeypatch):
  calls = []

  def texture(path, width, height):
    calls.append((path, width, height))
    return SimpleNamespace(width=width, height=height)

  monkeypatch.setattr(circular_alerts.gui_app, "texture", texture)
  circular_alerts.CircularAlertsRenderer()

  assert calls == [
    ("../../sunnypilot/selfdrive/assets/images/green_light.png", 250, 250),
    ("../../sunnypilot/selfdrive/assets/images/lead_depart.png", 250, 250),
  ]


def test_circular_alert_background_uses_official_opacity(monkeypatch):
  renderer = object.__new__(circular_alerts.CircularAlertsRenderer)
  renderer._allow_e2e_alerts = True
  renderer._e2e_alert_display_timer = 1
  renderer._e2e_alert_frame = 0
  renderer._is_standstill = False
  renderer._alert_img = None
  renderer._alert_text = ""

  monkeypatch.setattr(circular_alerts.ui_state, "standstill_timer", False)
  monkeypatch.setattr(circular_alerts.ui_state, "developer_ui", circular_alerts.DeveloperUiState.OFF)
  circles = []
  monkeypatch.setattr(circular_alerts.rl, "draw_circle_v", lambda center, radius, color: circles.append(color))
  monkeypatch.setattr(circular_alerts.rl, "draw_ring", lambda *args: None)
  monkeypatch.setattr(circular_alerts.rl, "draw_text_ex", lambda *args: None)
  monkeypatch.setattr(circular_alerts.gui_app, "font", lambda *args: None)
  monkeypatch.setattr(circular_alerts, "measure_text_cached", lambda *args: rl.Vector2(0, 0))

  renderer.render(rl.Rectangle(0, 0, 1920, 1080))

  assert len(circles) == 1
  assert circles[0].a == 190
