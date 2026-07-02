"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from openpilot.selfdrive.ui.sunnypilot.layouts.settings.vehicle.brands.base import BrandSettings
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.sunnypilot.widgets.list_view import button_item_sp, option_item_sp, toggle_item_sp

MPC_PRESET_MOUMOU = 0
MPC_PRESET_CURRENT = 1
MPC_PRESET_CUSTOM = 2

MPC_PRESETS = {
  MPC_PRESET_MOUMOU: {
    "MpcXObstacleCost": 300,
    "MpcJerkCost": 500,
    "MpcAccelChangeCost": 20000,
    "MpcDangerZoneCost": 10000,
    "MpcLeadDangerFactor": 75,
    "MpcComfortBrake": 250,
    "MpcStopDistance": 600,
    "MpcJerkFactorStandard": 100,
    "MpcTFollowRelaxed": 175,
    "MpcTFollowStandard": 145,
    "MpcTFollowAggressive": 125,
  },
  MPC_PRESET_CURRENT: {
    "MpcXObstacleCost": 500,
    "MpcJerkCost": 300,
    "MpcAccelChangeCost": 10000,
    "MpcDangerZoneCost": 8000,
    "MpcLeadDangerFactor": 35,
    "MpcComfortBrake": 270,
    "MpcStopDistance": 450,
    "MpcJerkFactorStandard": 80,
    "MpcTFollowRelaxed": 165,
    "MpcTFollowStandard": 135,
    "MpcTFollowAggressive": 100,
  },
}

MPC_TUNING_ITEMS = [
  ("MpcStopDistance", "Stop Distance",
   "Higher values make the car target a farther stop and brake earlier. Lower values stop closer to the lead and can feel later.",
   100, 1200, 25, lambda v: f"{v / 100.0:.2f} m"),
  ("MpcComfortBrake", "Comfort Brake",
   "Higher values assume stronger comfortable braking and can allow closer, later braking. Lower values reserve more distance and feel gentler.",
   50, 500, 5, lambda v: f"{v / 100.0:.2f} m/s^2"),
  ("MpcLeadDangerFactor", "Lead Danger Factor",
   "Higher values add more safety pressure near a lead and brake sooner. Lower values allow following closer before the danger cost rises.",
   1, 500, 5, lambda v: f"{v / 100.0:.2f}"),
  ("MpcTFollowRelaxed", "T Follow Relaxed",
   "Higher values increase the relaxed following gap. Lower values reduce the relaxed gap and follow closer.",
   50, 400, 5, lambda v: f"{v / 100.0:.2f} s"),
  ("MpcTFollowStandard", "T Follow Standard",
   "Higher values increase the standard following gap. Lower values reduce the standard gap and follow closer.",
   50, 400, 5, lambda v: f"{v / 100.0:.2f} s"),
  ("MpcTFollowAggressive", "T Follow Aggressive",
   "Higher values increase the aggressive following gap. Lower values reduce the aggressive gap and follow closer.",
   50, 400, 5, lambda v: f"{v / 100.0:.2f} s"),
  ("MpcXObstacleCost", "Obstacle Cost",
   "Higher values prioritize keeping the desired obstacle distance. Lower values allow smoother speed tracking but may hold a closer gap.",
   1, 1000, 25, lambda v: f"{v / 100.0:.2f}"),
  ("MpcJerkCost", "Jerk Cost",
   "Higher values make acceleration and braking smoother but slower to react. Lower values react faster and can feel sharper.",
   1, 1000, 25, lambda v: f"{v / 100.0:.2f}"),
  ("MpcJerkFactorStandard", "Standard Jerk Factor",
   "Higher values make standard mode smoother and less eager to change acceleration. Lower values make standard mode more responsive.",
   1, 300, 5, lambda v: f"{v / 100.0:.2f}"),
  ("MpcAccelChangeCost", "Accel Change Cost",
   "Higher values resist acceleration changes and smooth the plan. Lower values let the car change acceleration more quickly.",
   1, 50000, 500, lambda v: f"{v / 100.0:.0f}"),
  ("MpcDangerZoneCost", "Danger Zone Cost",
   "Higher values strongly avoid getting too close to a lead. Lower values reduce that penalty and can allow closer following.",
   1, 50000, 500, lambda v: f"{v / 100.0:.0f}"),
]

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
    self.speed_limit_cruise_buttons = toggle_item_sp(
      title=tr("Speed Limit Cruise Buttons"),
      param="TeslaSpeedLimitCruiseButtons",
      description=tr("Use Tesla steering-wheel speed buttons to adjust the stock ACC set speed to the active speed limit target."),
    )
    self._applying_mpc_preset = False
    self.mpc_moumou_preset = button_item_sp(
      title=tr("MPC Preset: dev260628XL"),
      button_text=tr("Apply"),
      description=tr("Apply the moumou/dev260628XL-tici longitudinal MPC values."),
      callback=lambda: self._apply_mpc_preset(MPC_PRESET_MOUMOU),
      enabled=ui_state.is_offroad,
    )
    self.mpc_current_preset = button_item_sp(
      title=tr("MPC Preset: Current"),
      button_text=tr("Apply"),
      description=tr("Apply the current branch longitudinal MPC values."),
      callback=lambda: self._apply_mpc_preset(MPC_PRESET_CURRENT),
      enabled=ui_state.is_offroad,
    )
    self.mpc_tuning_options = []
    for param, title, description, min_value, max_value, step, label_callback in MPC_TUNING_ITEMS:
      self.mpc_tuning_options.append(option_item_sp(
        title=tr(title),
        param=param,
        min_value=min_value,
        max_value=max_value,
        value_change_step=step,
        description=tr(description),
        label_callback=label_callback,
        on_value_changed=self._on_mpc_tuning_changed,
        enabled=ui_state.is_offroad,
        inline=True,
      ))
    self.items = [self.coop_steering_toggle, self.dynamic_auto_stock_toggle, self.dyn_auto_speed,
                  self.dyn_auto_speed_low, self.stop_line_deceleration,
                  self.speed_limit_cruise_buttons,
                  self.mpc_moumou_preset, self.mpc_current_preset,
                  *self.mpc_tuning_options]

  def _on_dyn_auto_stock_toggle(self, state):
    show = state
    self.dyn_auto_speed.set_visible(show)
    self.dyn_auto_speed_low.set_visible(show)

  def _apply_mpc_preset(self, preset):
    values = MPC_PRESETS[preset]
    self._applying_mpc_preset = True
    try:
      for option in self.mpc_tuning_options:
        value = values[option.action_item.param_key]
        option.action_item.set_value(value)
      ui_state.params.put("MpcTuningPreset", preset, block=True)
    finally:
      self._applying_mpc_preset = False

  def _on_mpc_tuning_changed(self, _value):
    if self._applying_mpc_preset:
      return
    ui_state.params.put("MpcTuningPreset", MPC_PRESET_CUSTOM, block=True)

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
    self.speed_limit_cruise_buttons.action_item.set_enabled(ui_state.is_offroad())

    self._on_dyn_auto_stock_toggle(self.dynamic_auto_stock_toggle.action_item.get_state())
