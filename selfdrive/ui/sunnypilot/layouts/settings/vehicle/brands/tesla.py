"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from openpilot.selfdrive.ui.sunnypilot.layouts.settings.vehicle.brands.base import BrandSettings
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.sunnypilot.widgets.list_view import option_item_sp, toggle_item_sp

class TeslaSettings(BrandSettings):
  def __init__(self):
    super().__init__()
    self.coop_steering_toggle = toggle_item_sp(tr("Cooperative Steering"), "", param="TeslaCoopSteering")
    self.dynamic_auto_stock_toggle = toggle_item_sp(
      title=tr("Dynamic Auto Stock ACC"),
      param="DynamicAutoStock",
      description=lambda: tr("Auto switch to stock ACC when above speed, close to lead, and ego not decelerating."),
      callback=self._on_dyn_auto_stock_toggle,
    )
    self.dyn_auto_speed = option_item_sp(
      title=tr("Speed Threshold High"), param="DynamicAutoStockSpeedKph",
      min_value=40, max_value=120, value_change_step=5,
      label_callback=lambda v: f"{v} km/h",
      description=tr("Switch to stock ACC above this speed."),
    )
    self.dyn_auto_speed_low = option_item_sp(
      title=tr("Speed Threshold Low"), param="DynamicAutoStockSpeedLowKph",
      min_value=20, max_value=100, value_change_step=5,
      label_callback=lambda v: f"{v} km/h",
      description=tr("Switch back to SP longitudinal below this speed."),
    )
    self.stop_line_deceleration = option_item_sp(
      title=tr("Stop Line Deceleration"),
      description=tr("Extra deceleration at traffic light and stop sign stops. Higher values stop earlier; 0 disables the extra deceleration."),
      param="StopLineDeceleration",
      min_value=0, max_value=10, value_change_step=1,
      label_callback=lambda value: f"{value / 10.0:.1f} m/s^2",
      inline=True,
    )
    self.items = [self.coop_steering_toggle, self.dynamic_auto_stock_toggle, self.dyn_auto_speed,
                  self.dyn_auto_speed_low, self.stop_line_deceleration]

  def _on_dyn_auto_stock_toggle(self, state):
    show = state
    self.dyn_auto_speed.set_visible(show)
    self.dyn_auto_speed_low.set_visible(show)

  def update_settings(self):
    coop_steering_desc = (
      f"{tr('Converts light steering input into steering-wheel rotation.')}<br>" +
      f"{tr('The faster you go, the stiffer the steering gets.')}"
    )

    enable_offroad_msg = tr("Enable \"Always Offroad\" in Device panel, or turn vehicle off to toggle.")
    if not ui_state.is_offroad():
      coop_steering_desc = f"<b>{enable_offroad_msg}</b><br><br>{coop_steering_desc}"

    self.coop_steering_toggle.set_description(coop_steering_desc)

    self.coop_steering_toggle.action_item.set_enabled(ui_state.is_offroad())
    self.stop_line_deceleration.action_item.set_enabled(ui_state.has_longitudinal_control)

    self._on_dyn_auto_stock_toggle(self.dynamic_auto_stock_toggle.action_item.get_state())
