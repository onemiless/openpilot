"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from openpilot.common.params import Params
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.sunnypilot.widgets.list_view import button_item_sp, toggle_item_sp
from openpilot.system.ui.widgets.scroller_tici import Scroller
from openpilot.system.ui.widgets import Widget


class NavigationLayout(Widget):
  def __init__(self):
    super().__init__()

    self._params = Params()
    items = self._initialize_items()
    self._scroller = Scroller(items, line_separator=True, spacing=0)

  def _initialize_items(self):
    self.status_item = button_item_sp(
      title=tr("NavAssist Status"),
      button_text=tr("Status"),
      description=tr("Shows the current Carrot/CP connection and control-data state."),
      enabled=False)
    items = [
      self.status_item,
      toggle_item_sp(
        title=tr("NavAssist (Experimental)"),
        description=tr("Receive Carrot/CP navigation guidance. Control remains disabled unless its individual switches are enabled."),
        param="NavAssistEnabled"),
      toggle_item_sp(
        title=tr("NavAssist Shadow Mode"),
        description=tr("Receive and calculate navigation actions without changing vehicle control."),
        param="NavAssistShadowMode"),
      toggle_item_sp(
        title=tr("NavAssist Speed Control"),
        description=tr("Apply validated maneuver, speed-camera and section-speed targets through the existing longitudinal planner."),
        param="NavAssistSpeedControl"),
      toggle_item_sp(
        title=tr("NavAssist Route Curve Speed"),
        description=tr("Use the navigation route only to reduce speed for curves. It never directly controls steering."),
        param="NavAssistRouteSpeedControl"),
      toggle_item_sp(
        title=tr("NavAssist Driver-Confirmed Turns"),
        description=tr("At low speed, send one model turn request only after the driver activates the matching turn signal."),
        param="NavAssistTurnControl"),
    ]
    return items

  def _render(self, rect):
    self._scroller.render(rect)

  def show_event(self):
    self._scroller.show_event()

  def _update_state(self):
    super()._update_state()
    if not ui_state.sm.seen["navAssistSP"]:
      status = tr("Not running")
    else:
      nav = ui_state.sm["navAssistSP"]
      if nav.source == "amapCompanionV1":
        source = tr("AMap Companion")
      elif nav.source == "carrotV2":
        source = tr("Carrot V2")
      else:
        source = tr("Navigation")
      if not nav.connected:
        status = tr("Waiting for phone")
      elif nav.dataValid:
        status = tr("Navigation active")
      else:
        status = tr("Connected, no valid guidance")
      status = f"{source} · {status}"
    self.status_item.action_item.set_value(status)
