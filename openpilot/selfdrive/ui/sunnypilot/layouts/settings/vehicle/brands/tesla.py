"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from collections.abc import Callable

import pyray as rl

from opendbc.sunnypilot.car.tesla.values import MadsScreenButtonType, TeslaFlagsSP
from openpilot.selfdrive.ui.sunnypilot.layouts.settings.vehicle.brands.base import BrandSettings
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.modes import (
  LONGITUDINAL_PLANNER_DEFAULT, get_longitudinal_planner_mode,
)
from openpilot.selfdrive.controls.lib.longitudinal_backends.registry import BACKENDS, PARAM_SPECS_BY_ID, BackendId, ordered_backends
from openpilot.selfdrive.controls.lib.longitudinal_backends.tuning import LEGACY_TO_SEMANTIC, write_backend_overrides
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.tuning_presets import (
  MPC_TUNING_KEYS, OFFICIAL_MPC_TUNING_KEYS, apply_profile, get_mpc_tuning_profile, get_profile_values,
  save_profile_values, write_live_values,
)
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.lib.multilang import tr, tr_noop
from openpilot.system.ui.sunnypilot.widgets.list_view import button_item_sp, multiple_button_item_sp, option_item_sp, toggle_item_sp
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.network import NavButton
from openpilot.system.ui.widgets.scroller_tici import Scroller

MPC_TUNING_PRESENTATION = [
  ("MpcStopDistance", tr_noop("Stop Distance"),
   tr_noop("Higher values make the car target a farther stop and brake earlier. Lower values stop closer to the lead and can feel later."),
   lambda v: f"{v / 100.0:.2f} m"),
  ("MpcComfortBrake", tr_noop("Comfort Brake"),
   tr_noop("Higher values assume stronger comfortable braking and can allow closer, later braking. Lower values reserve more distance and feel gentler."),
   lambda v: f"{v / 100.0:.2f} m/s^2"),
  ("MpcLeadDangerFactor", tr_noop("Lead Danger Factor"),
   tr_noop("Higher values add more safety pressure near a lead and brake sooner. Lower values allow following closer before the danger cost rises."),
   lambda v: f"{v / 100.0:.2f}"),
  ("MpcTFollowRelaxed", tr_noop("T Follow Relaxed"),
   tr_noop("Higher values increase the relaxed following gap. Lower values reduce the relaxed gap and follow closer."),
   lambda v: f"{v / 100.0:.2f} s"),
  ("MpcTFollowStandard", tr_noop("T Follow Standard"),
   tr_noop("Higher values increase the standard following gap. Lower values reduce the standard gap and follow closer."),
   lambda v: f"{v / 100.0:.2f} s"),
  ("MpcTFollowAggressive", tr_noop("T Follow Aggressive"),
   tr_noop("Higher values increase the aggressive following gap. Lower values reduce the aggressive gap and follow closer."),
   lambda v: f"{v / 100.0:.2f} s"),
  ("MpcXObstacleCost", tr_noop("Obstacle Cost"),
   tr_noop("Higher values prioritize keeping the desired obstacle distance. Lower values allow smoother speed tracking but may hold a closer gap."),
   lambda v: f"{v / 100.0:.2f}"),
  ("MpcJerkCost", tr_noop("Jerk Cost"),
   tr_noop("Higher values make acceleration and braking smoother but slower to react. Lower values react faster and can feel sharper."),
   lambda v: f"{v / 100.0:.2f}"),
  ("MpcJerkFactorStandard", tr_noop("Relaxed Jerk Factor"),
   tr_noop("Higher values make relaxed mode smoother and less eager to change acceleration. Lower values make relaxed mode more responsive."),
   lambda v: f"{v / 100.0:.2f}"),
  ("MpcAccelChangeCost", tr_noop("Accel Change Cost"),
   tr_noop("Higher values resist acceleration changes and smooth the plan. Lower values let the car change acceleration more quickly."),
   lambda v: f"{v / 100.0:.0f}"),
  ("MpcDangerZoneCost", tr_noop("Danger Zone Cost"),
   tr_noop("Higher values strongly avoid getting too close to a lead. Lower values reduce that penalty and can allow closer following."),
   lambda v: f"{v / 100.0:.0f}"),
]

# Backend labels are data-driven, so mark them explicitly for translation extraction.
MPC_BACKEND_LABELS = (tr_noop("Default"), tr_noop("CrazyMax"), tr_noop("TN-NoDEC"))

MPC_TUNING_ITEMS = [
  (key, title, description,
   int(round(PARAM_SPECS_BY_ID[LEGACY_TO_SEMANTIC[key]].minimum * 100)),
   int(round(PARAM_SPECS_BY_ID[LEGACY_TO_SEMANTIC[key]].maximum * 100)),
   int(round(PARAM_SPECS_BY_ID[LEGACY_TO_SEMANTIC[key]].step * 100)), label_callback)
  for key, title, description, label_callback in MPC_TUNING_PRESENTATION
]


class TeslaMpcSettingsLayout(Widget):
  def __init__(self, back_btn_callback: Callable):
    super().__init__()
    self._back_button = NavButton(tr("Back"))
    self._back_button.set_click_callback(back_btn_callback)
    self._applying_mpc_profile = False
    self.mpc_tuning_options = []
    self._initialize_items()
    self._scroller = Scroller(self.items, line_separator=True, spacing=0)

  def _initialize_items(self):
    self._planner_item = multiple_button_item_sp(
      title=lambda: tr("Longitudinal Planner"),
      description=lambda: tr("Default follows the current SP lead-based MPC structure. CrazyMax preserves the Moumou cruise-obstacle MPC. TN-NoDEC is experimental. Changes take effect next onroad session."),
      buttons=[lambda label=backend.label: tr(label) for backend in ordered_backends()],
      param="LongitudinalPlannerMode",
      callback=self._on_planner_changed,
      inline=False,
    )
    self._profile_item = multiple_button_item_sp(
      title=lambda: tr("MPC Tuning Profile"),
      description=lambda: tr("Parameter presets are independent from the planner implementation. Default uses current SP values; CrazyMax uses the verified Moumou baseline."),
      buttons=[lambda: tr("Default"), lambda: tr("CrazyMax"), lambda: tr("Current"), lambda: tr("Custom")],
      param="MpcTuningProfile",
      callback=self._on_profile_changed,
      inline=False,
    )
    self._tn_accel_enabled = toggle_item_sp(
      title=tr("TN Accel Personality"), param="AccelPersonalityEnabled",
      description=tr("Enable the TN backend-native acceleration profile controller."),
      callback=lambda value: write_backend_overrides(
        ui_state.params, BACKENDS[BackendId.TN_NO_DEC], {"tn.accel_personality.enabled": bool(value)},
      ),
    )
    self._tn_accel_profile = multiple_button_item_sp(
      title=lambda: tr("TN Accel Profile"),
      description=lambda: tr("Backend-native Eco, Normal, or Sport acceleration limits."),
      buttons=[lambda: tr("Eco"), lambda: tr("Normal"), lambda: tr("Sport")],
      param="AccelPersonality",
      callback=lambda value: write_backend_overrides(
        ui_state.params, BACKENDS[BackendId.TN_NO_DEC], {"tn.accel_personality.profile": int(value)},
      ),
      inline=False,
    )

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
        enabled=lambda: True,
        inline=True,
      ))

    self.items = [self._planner_item, self._profile_item, self._tn_accel_enabled, self._tn_accel_profile,
                  *self.mpc_tuning_options]
    self._apply_mpc_profile(get_mpc_tuning_profile(ui_state.params), update_profile_storage=False)

  @staticmethod
  def _profile_values(profile):
    return get_profile_values(ui_state.params, profile)

  @staticmethod
  def _save_profile_values(profile, values):
    save_profile_values(ui_state.params, profile, values)

  @staticmethod
  def _write_live_mpc_values(values):
    write_live_values(ui_state.params, values)

  def _on_planner_changed(self, _mode):
    self._update_tuning_enablement()

  def _on_profile_changed(self, profile):
    self._apply_mpc_profile(profile)

  def _apply_mpc_profile(self, profile, update_profile_storage=True):
    values = apply_profile(ui_state.params, profile)
    self._applying_mpc_profile = True
    try:
      for option in self.mpc_tuning_options:
        value = values[option.action_item.param_key]
        option.action_item.set_value(value)
      self._write_live_mpc_values(values)
      if update_profile_storage:
        self._save_profile_values(profile, values)
    finally:
      self._applying_mpc_profile = False

  def _on_mpc_tuning_changed(self, _value):
    if self._applying_mpc_profile:
      return

    profile = get_mpc_tuning_profile(ui_state.params)
    values = self._profile_values(profile)
    for option in self.mpc_tuning_options:
      values[option.action_item.param_key] = option.action_item.get_value()
    assert set(values) == set(MPC_TUNING_KEYS)
    self._write_live_mpc_values(values)
    self._save_profile_values(profile, values)

  def _update_tuning_enablement(self):
    official = get_longitudinal_planner_mode(ui_state.params) == LONGITUDINAL_PLANNER_DEFAULT
    tn = get_longitudinal_planner_mode(ui_state.params) == int(BackendId.TN_NO_DEC)
    self._tn_accel_enabled.set_visible(tn)
    self._tn_accel_profile.set_visible(tn)
    for option in self.mpc_tuning_options:
      supported = not official or option.action_item.param_key in OFFICIAL_MPC_TUNING_KEYS
      option.action_item.set_enabled(supported)

  def _update_state(self):
    super()._update_state()
    self._planner_item.action_item.set_enabled(ui_state.is_offroad())
    self._profile_item.action_item.set_enabled(True)
    self._update_tuning_enablement()

  def _render(self, rect):
    self._back_button.set_position(self._rect.x, self._rect.y + 20)
    self._back_button.render()
    content_rect = rl.Rectangle(
      rect.x,
      rect.y + self._back_button.rect.height + 40,
      rect.width,
      rect.height - self._back_button.rect.height - 40,
    )
    self._scroller.render(content_rect)

  def show_event(self):
    self._scroller.show_event()


class TeslaFeatureSettingsLayout(Widget):
  def __init__(self, back_btn_callback: Callable):
    super().__init__()
    self._back_button = NavButton(tr("Back"))
    self._back_button.set_click_callback(back_btn_callback)
    self.touch_longitudinal_switch_toggle = toggle_item_sp(
      title=tr("4-Finger Longitudinal Switch"),
      param="TeslaTouchLongitudinalSwitch",
      description=tr("A 4-finger touch on the infotainment screen toggles longitudinal control " +
                     "between sunnypilot and Tesla stock ACC while engaged. Restart after changing."),
      enabled=ui_state.is_offroad,
    )
    self.dynamic_auto_stock_toggle = toggle_item_sp(
      title=tr("Dynamic Auto Stock ACC"),
      param="DynamicAutoStock",
      description=lambda: tr("Auto switch to stock ACC when above speed, close to lead, and ego not decelerating."),
      callback=self._on_dyn_auto_stock_toggle,
    )
    self.dynamic_auto_stock_blinker_to_sp_toggle = toggle_item_sp(
      title=tr("Turn Signal → SP Longitudinal"),
      param="DynamicAutoStockBlinkerToSP",
      description=tr("When Dynamic ACC is using Tesla ACC, switch longitudinal control to sunnypilot after a confirmed turn signal."),
    )
    self.dynamic_auto_stock_curve_to_sp_toggle = toggle_item_sp(
      title=tr("Curve → SP Longitudinal"),
      param="DynamicAutoStockCurveToSP",
      description=tr("When Dynamic ACC is using Tesla ACC, switch longitudinal control to sunnypilot when vision or map curve control becomes active."),
    )
    self.ap_hybrid_toggle = toggle_item_sp(
      title=tr("AP Hybrid Control (Experimental)"),
      param="TeslaApHybrid",
      description=tr("Keeps a Tesla AP session active while sunnypilot arbitrates lateral and longitudinal control. " +
                     "The optional Dynamic AP mode selects both control sources by speed."),
      enabled=ui_state.is_offroad,
    )
    self.dynamic_ap_longitudinal_toggle = toggle_item_sp(
      title=tr("Dynamic AP Control (Experimental)"),
      param="TeslaDynamicApLongitudinal",
      description=tr("Below the low-speed threshold, sunnypilot controls steering and speed. Above the high-speed threshold, Tesla AP controls both. " +
                     "Driver steering input or a turn signal immediately hands steering to sunnypilot; Tesla steering resumes after one stable second."),
      callback=self._on_dynamic_ap_longitudinal_toggle,
      enabled=ui_state.is_offroad,
    )
    self.dyn_auto_speed = option_item_sp(
      title=tr("Speed Threshold High"), param="DynamicAutoStockSpeedKph",
      min_value=40, max_value=120, value_change_step=5,
      label_callback=lambda v: f"{v} km/h",
      description=tr("Switch to Tesla control above this speed in Dynamic ACC or Dynamic AP mode."),
    )
    self.dyn_auto_speed_low = option_item_sp(
      title=tr("Speed Threshold Low"), param="DynamicAutoStockSpeedLowKph",
      min_value=20, max_value=100, value_change_step=5,
      label_callback=lambda v: f"{v} km/h",
      description=tr("Switch back to sunnypilot control below this speed in Dynamic ACC or Dynamic AP mode."),
    )
    self.stop_line_deceleration = option_item_sp(
      title=tr("Stop Line Deceleration"),
      description=tr("Extra deceleration at traffic light and stop sign stops. Higher values stop earlier; 0 disables the extra deceleration."),
      param="StopLineDeceleration",
      min_value=0, max_value=10, value_change_step=1,
      label_callback=lambda value: f"{value / 10.0:.1f} m/s^2",
      inline=True,
    )
    self.mpc_settings = button_item_sp(
      title=tr("MPC Params"),
      button_text=tr("Customize"),
      description=tr("Adjust longitudinal MPC presets and detailed tuning parameters."),
      callback=self._show_mpc_settings,
      enabled=ui_state.is_offroad,
    )
    self.items = [self.touch_longitudinal_switch_toggle, self.ap_hybrid_toggle, self.dynamic_ap_longitudinal_toggle,
                  self.dynamic_auto_stock_toggle,
                  self.dynamic_auto_stock_blinker_to_sp_toggle,
                  self.dynamic_auto_stock_curve_to_sp_toggle,
                  self.dyn_auto_speed,
                  self.dyn_auto_speed_low, self.stop_line_deceleration,
                  self.mpc_settings]
    self._scroller = Scroller(self.items, line_separator=True, spacing=0)

  def _on_dyn_auto_stock_toggle(self, state):
    self._update_dynamic_speed_visibility()

  def _on_dynamic_ap_longitudinal_toggle(self, state):
    self._update_dynamic_speed_visibility()

  def _update_dynamic_speed_visibility(self):
    dynamic_acc_enabled = ui_state.params.get_bool("DynamicAutoStock")
    show = (dynamic_acc_enabled or
            ui_state.params.get_bool("TeslaDynamicApLongitudinal"))
    self.dynamic_auto_stock_blinker_to_sp_toggle.set_visible(dynamic_acc_enabled)
    self.dynamic_auto_stock_curve_to_sp_toggle.set_visible(dynamic_acc_enabled)
    self.dyn_auto_speed.set_visible(show)
    self.dyn_auto_speed_low.set_visible(show)

  def _show_mpc_settings(self):
    gui_app.push_widget(TeslaMpcSettingsLayout(lambda: gui_app.pop_widget()))

  def _update_state(self):
    super()._update_state()
    self.touch_longitudinal_switch_toggle.action_item.set_enabled(ui_state.is_offroad())
    self.ap_hybrid_toggle.action_item.set_enabled(ui_state.is_offroad() and ui_state.has_longitudinal_control)
    self.dynamic_ap_longitudinal_toggle.action_item.set_enabled(
      ui_state.is_offroad() and ui_state.has_longitudinal_control and ui_state.params.get_bool("TeslaApHybrid")
    )
    self._update_dynamic_speed_visibility()

    self.stop_line_deceleration.action_item.set_enabled(ui_state.has_longitudinal_control)
    self.mpc_settings.action_item.set_enabled(ui_state.is_offroad())

    self._on_dyn_auto_stock_toggle(self.dynamic_auto_stock_toggle.action_item.get_state())

  def _render(self, rect):
    self._back_button.set_position(self._rect.x, self._rect.y + 20)
    self._back_button.render()
    content_rect = rl.Rectangle(
      rect.x,
      rect.y + self._back_button.rect.height + 40,
      rect.width,
      rect.height - self._back_button.rect.height - 40,
    )
    self._scroller.render(content_rect)

  def show_event(self):
    self._scroller.show_event()


class TeslaSettings(BrandSettings):
  def __init__(self):
    super().__init__()
    screen_button = int(ui_state.params.get("TeslaMadsScreenButton", return_default=True))
    if screen_button == 3:
      # Legacy 5-finger value from when the 4-finger option existed.
      ui_state.params.put("TeslaMadsScreenButton", MadsScreenButtonType.FIVE_FINGER, block=True)

    self.coop_steering_toggle = toggle_item_sp(
      tr("Cooperative Steering"), "", param="TeslaCoopSteering",
    )
    self.mads_screen_button = multiple_button_item_sp(
      title=lambda: tr("MADS Screen Activation"),
      description="",
      buttons=[lambda: tr("Off"), lambda: tr("3-Finger"), lambda: tr("5-Finger")],
      param="TeslaMadsScreenButton",
      inline=False,
    )
    self._settings_layout = TeslaFeatureSettingsLayout(lambda: gui_app.pop_widget())
    self._settings_button = button_item_sp(
      title=tr("Tesla Settings"),
      button_text=tr("Customize"),
      description=tr("Configure Tesla-specific steering, MADS screen controls, longitudinal handoff, and stop-line behavior."),
      callback=self._show_settings,
    )
    self.items = [self.coop_steering_toggle, self.mads_screen_button, self._settings_button]

  def _show_settings(self):
    gui_app.push_widget(self._settings_layout)

  def update_settings(self):
    offroad = ui_state.is_offroad()
    enable_offroad_msg = tr("Enable \"Always Offroad\" in Device panel, or turn vehicle off to toggle.")
    coop_steering_desc = (
      f"{tr('Converts light steering input into steering-wheel rotation.')}<br>" +
      f"{tr('The faster you go, the stiffer the steering gets.')}"
    )
    if not offroad:
      coop_steering_desc = f"<b>{enable_offroad_msg}</b><br><br>{coop_steering_desc}"
    self.coop_steering_toggle.set_description(coop_steering_desc)
    self.coop_steering_toggle.action_item.set_enabled(offroad)

    has_vehicle_bus = ui_state.CP_SP is not None and bool(ui_state.CP_SP.flags & TeslaFlagsSP.HAS_VEHICLE_BUS)
    mads_screen_button_desc = (
      f"{tr('Use a multi-finger press on the infotainment screen to toggle MADS.')} " +
      f"{tr('This allows the use of full MADS functionality when enabled.')}<br><br>" +
      f"{tr('Selecting a higher finger count may reduce accidental activations.')}<br><br>" +
      f"<b>{tr('Note: Setting this to Off will reset your MADS settings to default.')}</b>"
    )
    if not has_vehicle_bus:
      limited_msg = tr("This platform supports limited MADS settings.")
      mads_screen_button_desc = f"<b>{limited_msg}</b><br><br>{mads_screen_button_desc}"
    elif not offroad:
      disabled_msg = tr("Enable \"Always Offroad\" in Device panel, or turn vehicle off to change.")
      mads_screen_button_desc = f"<b>{disabled_msg}</b><br><br>{mads_screen_button_desc}"
    self.mads_screen_button.set_description(mads_screen_button_desc)
    self.mads_screen_button.action_item.set_enabled(offroad and has_vehicle_bus)

    self._settings_button.action_item.set_enabled(True)
