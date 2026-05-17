"""
Drive mode quick switch — toggles between E2E (experimental+alpha) and stock ACC.
"""

import pyray as rl
from openpilot.common.params import Params
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import gui_app, FontWeight
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.widgets import Widget


class DriveModeSwitch(Widget):
  """Toggle button: offroad sets E2E, onroad switches to stock ACC."""

  def __init__(self, onroad: bool = False):
    super().__init__()
    self.params = Params()
    self._onroad_mode = onroad
    self._font_bold = gui_app.font(FontWeight.BOLD)
    self._font_normal = gui_app.font(FontWeight.NORMAL)

    # cached display state (refreshed on click or periodically)
    self._mode_text = ""
    self._hint_text = ""
    self._color = rl.Color(35, 149, 255, 220)
    self._frame = 0
    self._refresh_params()

  def _refresh_params(self):
    self._exp = self.params.get_bool("ExperimentalMode")
    self._alpha = self.params.get_bool("AlphaLongitudinalEnabled")
    if self._exp and self._alpha:
      self._mode_text = tr("E2E MODE")
      self._color = rl.Color(219, 56, 34, 220)
    elif self._exp and not self._alpha:
      self._mode_text = tr("EXP (ACC)")
      self._color = rl.Color(255, 155, 63, 220)
    elif self._alpha and not self._exp:
      self._mode_text = tr("ALPHA (ACC)")
      self._color = rl.Color(255, 155, 63, 220)
    else:
      self._mode_text = tr("STOCK ACC")
      self._color = rl.Color(35, 149, 255, 220)

    if self._onroad_mode:
      self._hint_text = tr("Tap: exit E2E > ACC")
    elif self._exp and self._alpha:
      self._hint_text = tr("Tap: switch to ACC")
    else:
      self._hint_text = tr("Tap: switch to E2E")

  def _do_switch(self):
    if self._onroad_mode:
      self.params.put_bool("ExperimentalMode", False)
      self.params.put_bool("AlphaLongitudinalEnabled", False)
      self.params.put_bool("Mads", False)
    else:
      self.params.put_bool("ExperimentalMode", True)
      self.params.put_bool("AlphaLongitudinalEnabled", True)
      self.params.put_bool("SmartCruiseControlVision", True)
      self.params.put_bool("Mads", True)
    self._refresh_params()

  def _handle_mouse_release(self, mouse_pos):
    if rl.check_collision_point_rec(mouse_pos, self._rect):
      self._do_switch()
      return True
    return False

  def _render(self, rect):
    self._rect = rect

    # Periodic refresh (every 60 frames = ~3s), display uses cached values
    self._frame += 1
    if self._frame % 60 == 1:
      self._refresh_params()

    rl.draw_rectangle_rounded(rect, 0.2, 10, self._color)

    font_size = 36 if self._onroad_mode else 40
    tw = rl.measure_text(self._mode_text, font_size)
    tx = rect.x + (rect.width - tw) / 2
    ty = rect.y + (rect.height - font_size) / 2 - 2
    rl.draw_text_ex(self._font_bold, self._mode_text,
                    rl.Vector2(int(tx), int(ty)), font_size, 0, rl.WHITE)

    hint_fs = 24
    hw = rl.measure_text(self._hint_text, hint_fs)
    hx = rect.x + (rect.width - hw) / 2
    hy = ty + font_size + 4
    rl.draw_text_ex(self._font_normal, self._hint_text,
                    rl.Vector2(int(hx), int(hy)), hint_fs, 0, rl.Color(255, 255, 255, 180))
