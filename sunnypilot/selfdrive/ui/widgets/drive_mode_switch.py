"""
Drive mode quick switch — toggles between E2E (experimental+alpha) and stock ACC.
"""

import pyray as rl
from openpilot.common.params import Params
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import gui_app, FontWeight, FONT_SCALE
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.widgets import Widget

from cereal import custom

MADSState = custom.ModularAssistiveDrivingSystem.ModularAssistiveDrivingSystemState


class DriveModeSwitch(Widget):
  """Toggle button: offroad sets E2E, onroad switches to stock ACC."""

  def __init__(self, onroad: bool = False):
    super().__init__()
    self.params = Params()
    self._onroad_mode = onroad
    self._clicked = False

    self.img_width = 64
    self.padding = 20
    self.button_height = 110

  def _do_switch(self):
    if self._onroad_mode:
      # Switch TO stock ACC: disable E2E features
      self.params.put_bool_nonblocking("ExperimentalMode", False)
      self.params.put_bool_nonblocking("AlphaLongitudinalEnabled", False)
      # Disengage MADS
      self.params.put_bool_nonblocking("Mads", False)
      self._clicked = True
    else:
      # Switch TO E2E: enable full features
      self.params.put_bool_nonblocking("ExperimentalMode", True)
      self.params.put_bool_nonblocking("AlphaLongitudinalEnabled", True)
      self.params.put_bool_nonblocking("SmartCruiseControlVision", True)
      self.params.put_bool_nonblocking("Mads", True)
      self._clicked = True

  def get_mode_text(self) -> str:
    exp = self.params.get_bool("ExperimentalMode")
    alpha = self.params.get_bool("AlphaLongitudinalEnabled")
    if exp and alpha:
      return tr("E2E MODE")
    elif exp and not alpha:
      return tr("EXP (ACC)")
    elif alpha and not exp:
      return tr("ALPHA (ACC)")
    else:
      return tr("STOCK ACC")

  def get_color(self) -> rl.Color:
    exp = self.params.get_bool("ExperimentalMode")
    alpha = self.params.get_bool("AlphaLongitudinalEnabled")
    if exp and alpha:
      return rl.Color(219, 56, 34, 220)   # red-orange for E2E
    elif exp or alpha:
      return rl.Color(255, 155, 63, 220)  # orange for partial
    else:
      return rl.Color(35, 149, 255, 220)  # blue for stock ACC

  def _handle_mouse_release(self, mouse_pos):
    if rl.check_collision_point_rec(mouse_pos, self._rect):
      self._do_switch()
      return True
    return False

  def _render(self, rect):
    self._rect = rect
    color = self.get_color()
    text = self.get_mode_text()

    rl.draw_rectangle_rounded(rect, 0.2, 10, color)

    # center text
    font_size = 36 if self._onroad_mode else 40
    text_width = rl.measure_text(text, font_size)
    tx = rect.x + (rect.width - text_width) / 2
    ty = rect.y + (rect.height - font_size) / 2 - 2
    rl.draw_text_ex(gui_app.font(FontWeight.BOLD), text,
                    rl.Vector2(int(tx), int(ty)), font_size, 0, rl.WHITE)

    # icon hint
    hint = tr("Tap: switch to E2E") if not (self.params.get_bool("ExperimentalMode")
          and self.params.get_bool("AlphaLongitudinalEnabled")) else tr("Tap: switch to ACC")
    if self._onroad_mode:
      hint = tr("Tap: exit E2E → ACC")
    hint_fs = 24
    hint_w = rl.measure_text(hint, hint_fs)
    hx = rect.x + (rect.width - hint_w) / 2
    hy = ty + font_size + 4
    rl.draw_text_ex(gui_app.font(FontWeight.NORMAL), hint,
                    rl.Vector2(int(hx), int(hy)), hint_fs, 0, rl.Color(255, 255, 255, 180))
