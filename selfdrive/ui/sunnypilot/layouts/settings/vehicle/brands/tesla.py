"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from collections.abc import Callable
import json
import os
import subprocess
import sys
import threading

import pyray as rl

from opendbc.sunnypilot.car.tesla.values import TeslaFlagsSP
from openpilot.selfdrive.ui.sunnypilot.layouts.settings.vehicle.brands.base import BrandSettings
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.sunnypilot.widgets.list_view import button_item_sp, multiple_button_item_sp, option_item_sp, toggle_item_sp
from openpilot.system.ui.widgets import DialogResult, Widget
from openpilot.system.ui.widgets.confirm_dialog import ConfirmDialog, alert_dialog
from openpilot.system.ui.widgets.network import NavButton
from openpilot.system.ui.widgets.option_dialog import MultiOptionDialog
from openpilot.system.ui.widgets.scroller_tici import Scroller

MPC_PRESET_MOUMOU = 0
MPC_PRESET_CURRENT = 1
MPC_PRESET_LABELS = {
  MPC_PRESET_MOUMOU: "dev260628XL",
  MPC_PRESET_CURRENT: "Current",
}
MPC_PRESET_VALUE_PARAMS = {
  MPC_PRESET_MOUMOU: "MpcTuningMoumouValues",
  MPC_PRESET_CURRENT: "MpcTuningCurrentValues",
}
TURN_SIGNAL_TEST_SCRIPT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../../../debug/tesla_turn_signal_test.py"))
SPEED_BUTTON_TEST_SCRIPT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../../../debug/tesla_speed_button_test.py"))

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


class TeslaMpcSettingsLayout(Widget):
  def __init__(self, back_btn_callback: Callable):
    super().__init__()
    self._back_button = NavButton(tr("Back"))
    self._back_button.set_click_callback(back_btn_callback)
    self._preset_dialog: MultiOptionDialog | None = None
    self._applying_mpc_preset = False
    self.mpc_tuning_options = []
    self._initialize_items()
    self._scroller = Scroller(self.items, line_separator=True, spacing=0)

  def _initialize_items(self):
    self._preset_item = button_item_sp(
      title=lambda: tr("MPC Preset"),
      button_text=lambda: tr("SELECT"),
      description=lambda: tr("Choose which MPC preset to use. Changes made below are saved back to the selected preset."),
      callback=self._show_preset_dialog,
      enabled=ui_state.is_offroad,
    )
    self._preset_item.action_item.set_value(self._preset_label(self._active_preset()))

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

    self.items = [self._preset_item, *self.mpc_tuning_options]
    self._apply_mpc_preset(self._active_preset(), update_preset_storage=False)

  @staticmethod
  def _preset_label(preset):
    return tr(MPC_PRESET_LABELS.get(preset, MPC_PRESET_LABELS[MPC_PRESET_MOUMOU]))

  @staticmethod
  def _active_preset():
    try:
      return int(ui_state.params.get("MpcTuningPreset", return_default=True))
    except (TypeError, ValueError):
      return MPC_PRESET_MOUMOU

  @staticmethod
  def _preset_values(preset):
    values = dict(MPC_PRESETS[preset])
    saved = ui_state.params.get(MPC_PRESET_VALUE_PARAMS[preset])
    if saved:
      if isinstance(saved, dict):
        saved_values = saved
      else:
        try:
          saved_values = json.loads(saved)
        except (TypeError, json.JSONDecodeError):
          saved_values = {}
      if not isinstance(saved_values, dict):
        saved_values = {}
      for key, value in saved_values.items():
        if key in values:
          values[key] = int(value)
    return values

  @staticmethod
  def _save_preset_values(preset, values):
    ui_state.params.put(MPC_PRESET_VALUE_PARAMS[preset], values)

  @staticmethod
  def _write_live_mpc_values(values):
    for key in MPC_PRESETS[MPC_PRESET_MOUMOU]:
      ui_state.params.put(key, int(values[key]))

  def _show_preset_dialog(self):
    labels = [self._preset_label(preset) for preset in MPC_PRESET_LABELS]
    current = self._preset_label(self._active_preset())

    def handle_selection(result):
      if result != DialogResult.CONFIRM or self._preset_dialog is None:
        return

      selected_label = self._preset_dialog.selection
      for preset in MPC_PRESET_LABELS:
        if selected_label == self._preset_label(preset):
          self._apply_mpc_preset(preset)
          break
      self._preset_dialog = None

    self._preset_dialog = MultiOptionDialog(tr("Select MPC Preset"), labels, current, callback=handle_selection)
    gui_app.push_widget(self._preset_dialog)

  def _apply_mpc_preset(self, preset, update_preset_storage=True):
    values = self._preset_values(preset)
    self._applying_mpc_preset = True
    try:
      for option in self.mpc_tuning_options:
        value = values[option.action_item.param_key]
        option.action_item.set_value(value)
      self._write_live_mpc_values(values)
      ui_state.params.put("MpcTuningPreset", preset)
      self._preset_item.action_item.set_value(self._preset_label(preset))
      if update_preset_storage:
        self._save_preset_values(preset, values)
    finally:
      self._applying_mpc_preset = False

  def _on_mpc_tuning_changed(self, _value):
    if self._applying_mpc_preset:
      return

    preset = self._active_preset()
    values = self._preset_values(preset)
    for option in self.mpc_tuning_options:
      values[option.action_item.param_key] = option.action_item.get_value()
    self._write_live_mpc_values(values)
    self._save_preset_values(preset, values)

  def _update_state(self):
    super()._update_state()
    self._preset_item.action_item.set_enabled(ui_state.is_offroad())
    self._preset_item.action_item.set_value(self._preset_label(self._active_preset()))
    for option in self.mpc_tuning_options:
      option.action_item.set_enabled(ui_state.is_offroad())

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
    self._turn_signal_test_busy = False
    self._turn_signal_test_result: str | None = None
    self._speed_button_test_busy = False
    self._speed_button_test_result: str | None = None
    self.coop_steering_toggle = toggle_item_sp(tr("Cooperative Steering"), "", param="TeslaCoopSteering")
    self.mads_screen_button = multiple_button_item_sp(
      title=lambda: tr("MADS Screen Button"),
      description="",
      buttons=[lambda: tr("Off"), lambda: tr("3 Finger"), lambda: tr("4 Finger"), lambda: tr("5 Finger")],
      param="TeslaMadsScreenButton",
      inline=False,
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
    self.camera_offset = option_item_sp(
      title=tr("Lane Center Offset"),
      param="CameraOffset",
      min_value=-20, max_value=20, value_change_step=1,
      use_float_scaling=True,
      label_callback=lambda value: f"{value / 100.0:+.2f} m",
      description=tr("Virtually shifts the camera model: positive moves the planned center left and negative moves it right. " +
                     "Changes fade in gradually and can take up to about 10 seconds. Adjust only while parked, then verify on a straight road " +
                     "with clear lane lines. Curves and lane changes may not behave like a simple path translation."),
      enabled=ui_state.is_offroad,
      inline=True,
    )
    self.reset_camera_offset = button_item_sp(
      title=tr("Reset Lane Center Offset"),
      button_text=tr("RESET"),
      description=tr("Restore the camera model offset to 0.00 m."),
      callback=lambda: self.camera_offset.action_item.set_value(0),
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
    self.can_validation_logging = toggle_item_sp(
      title=tr("Tesla CAN Validation Logging"),
      param="TeslaCanValidationLogging",
      description=tr("Record turn-stalk, AP body-control, speed-wheel, and AP-state CAN frames for validation. " +
                     "This is read-only and takes effect after restart."),
      enabled=ui_state.is_offroad,
    )
    self.turn_signal_validation = toggle_item_sp(
      title=tr("Turn Signal CAN Validation"),
      param="TeslaTurnSignalValidation",
      description=tr("Allow one-shot left/right DAS body-control requests cloned from a fresh original vehicle 0x3E9 frame. " +
                     "No signal is sent automatically; restart after changing this option."),
    )
    self.speed_button_validation = toggle_item_sp(
      title=tr("Speed Button CAN Validation"),
      param="TeslaSpeedButtonValidation",
      description=tr("Allow one-shot speed increase/decrease tests built from a fresh original vehicle 0x3C2 right-scroll frame."),
    )
    self.auto_speed_limit = toggle_item_sp(
      title=tr("Automatic Tesla Set Speed"),
      param="TeslaAutoSpeedLimit",
      description=tr("While sunnypilot is engaged, adjust Tesla's set speed one wheel tick at a time until it reaches " +
                     "the resolved Speed Limit target from Cruise settings, including the configured fixed or percentage offset. " +
                     "Restart after changing this option."),
      enabled=ui_state.is_offroad,
    )
    self.test_speed_increase = button_item_sp(
      title=tr("Test Speed Increase"),
      button_text=lambda: tr("WAIT") if self._speed_button_test_busy else tr("TEST"),
      description=tr("Submit one short increase pulse cloned from the latest original vehicle frame and record the result."),
      callback=lambda: self._confirm_speed_button_test("increase"),
      enabled=self._speed_button_test_enabled,
    )
    self.test_speed_decrease = button_item_sp(
      title=tr("Test Speed Decrease"),
      button_text=lambda: tr("WAIT") if self._speed_button_test_busy else tr("TEST"),
      description=tr("Submit one short decrease pulse cloned from the latest original vehicle frame and record the result."),
      callback=lambda: self._confirm_speed_button_test("decrease"),
      enabled=self._speed_button_test_enabled,
    )
    self.test_left_turn_signal = button_item_sp(
      title=tr("Test Left Turn Signal"),
      button_text=lambda: tr("WAIT") if self._turn_signal_test_busy else tr("TEST"),
      description=tr("Send one guarded left-turn validation pulse and save CAN echo, rejection, and vehicle feedback to the validation log."),
      callback=lambda: self._confirm_turn_signal_test("left"),
      enabled=self._turn_signal_test_enabled,
    )
    self.test_right_turn_signal = button_item_sp(
      title=tr("Test Right Turn Signal"),
      button_text=lambda: tr("WAIT") if self._turn_signal_test_busy else tr("TEST"),
      description=tr("Send one guarded right-turn validation pulse and save CAN echo, rejection, and vehicle feedback to the validation log."),
      callback=lambda: self._confirm_turn_signal_test("right"),
      enabled=self._turn_signal_test_enabled,
    )
    self.mpc_settings = button_item_sp(
      title=tr("MPC Params"),
      button_text=tr("Customize"),
      description=tr("Adjust longitudinal MPC presets and detailed tuning parameters."),
      callback=self._show_mpc_settings,
      enabled=ui_state.is_offroad,
    )
    self.items = [self.coop_steering_toggle, self.mads_screen_button,
                  self.camera_offset, self.reset_camera_offset,
                  self.ap_hybrid_toggle, self.dynamic_ap_longitudinal_toggle,
                  self.dynamic_auto_stock_toggle,
                  self.dynamic_auto_stock_blinker_to_sp_toggle,
                  self.dynamic_auto_stock_curve_to_sp_toggle,
                  self.dyn_auto_speed,
                  self.dyn_auto_speed_low, self.stop_line_deceleration,
                  self.can_validation_logging,
                  self.auto_speed_limit, self.turn_signal_validation, self.speed_button_validation,
                  self.test_speed_increase, self.test_speed_decrease, self.test_left_turn_signal,
                  self.test_right_turn_signal, self.mpc_settings]

  def _turn_signal_test_enabled(self):
    return ui_state.params.get_bool("TeslaTurnSignalValidation") and not self._turn_signal_test_busy

  def _speed_button_test_enabled(self):
    return ui_state.params.get_bool("TeslaSpeedButtonValidation") and not self._speed_button_test_busy

  def _confirm_speed_button_test(self, action):
    label = tr("increase") if action == "increase" else tr("decrease")
    message = tr("Run one speed-button CAN validation now? The test accepts only a fresh original 0x3C2 wheel-status frame from bus 1, " +
                 "clones it, changes only one signed right-scroll tick, and logs whether Panda and the vehicle respond. " +
                 "Watch the vehicle set-speed display and run only one test at a time.")

    def handle_confirmation(result):
      if result == DialogResult.CONFIRM:
        self._run_speed_button_test(action)

    gui_app.push_widget(ConfirmDialog(message, f"{tr('Test')} {label}", callback=handle_confirmation))

  def _run_speed_button_test(self, action):
    if self._speed_button_test_busy:
      return
    self._speed_button_test_busy = True

    def run():
      try:
        result = subprocess.run(
          [sys.executable, SPEED_BUTTON_TEST_SCRIPT, action],
          capture_output=True,
          text=True,
          timeout=20,
          check=False,
        )
        output = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
        if result.returncode == 0:
          status = tr("PASS")
        elif result.returncode == 3:
          status = tr("SENT - CHECK VEHICLE")
        elif result.returncode == 2:
          status = tr("FAIL")
        else:
          status = tr("BLOCKED")
        self._speed_button_test_result = (
          f"{status}\n\n{output[-1800:]}\n\n{tr('Saved to:')} /data/tesla_speed_button_validation.log"
        )
      except Exception as error:
        self._speed_button_test_result = (
          f"{tr('Error')}\n\n{error}\n\n{tr('Saved to:')} /data/tesla_speed_button_validation.log"
        )
      finally:
        self._speed_button_test_busy = False

    threading.Thread(target=run, daemon=True).start()

  def _confirm_turn_signal_test(self, direction):
    label = tr("left") if direction == "left" else tr("right")
    message = tr("Run one turn-signal CAN test now? Python carState/carControl, gear, brake, and standstill state are not required. " +
                 "The test clones a fresh original 0x3E9 frame and changes only the DAS request, reason, counter, and checksum. " +
                 "The result and raw CAN evidence will be saved.")

    def handle_confirmation(result):
      if result == DialogResult.CONFIRM:
        self._run_turn_signal_test(direction)

    gui_app.push_widget(ConfirmDialog(message, f"{tr('Test')} {label}", callback=handle_confirmation))

  def _run_turn_signal_test(self, direction):
    if self._turn_signal_test_busy:
      return
    self._turn_signal_test_busy = True

    def run():
      try:
        result = subprocess.run(
          [sys.executable, TURN_SIGNAL_TEST_SCRIPT, direction],
          capture_output=True,
          text=True,
          timeout=20,
          check=False,
        )
        output = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
        status = tr("PASS") if result.returncode == 0 else tr("FAIL") if result.returncode == 2 else tr("BLOCKED")
        self._turn_signal_test_result = f"{status}\n\n{output[-1800:]}\n\n{tr('Saved to:')} /data/tesla_turn_signal_validation.log"
      except Exception as error:
        self._turn_signal_test_result = f"{tr('Error')}\n\n{error}\n\n{tr('Saved to:')} /data/tesla_turn_signal_validation.log"
      finally:
        self._turn_signal_test_busy = False

    threading.Thread(target=run, daemon=True).start()

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
    self.camera_offset.action_item.set_enabled(ui_state.is_offroad())
    self.reset_camera_offset.action_item.set_enabled(ui_state.is_offroad())
    self.ap_hybrid_toggle.action_item.set_enabled(ui_state.is_offroad() and ui_state.has_longitudinal_control)
    self.dynamic_ap_longitudinal_toggle.action_item.set_enabled(
      ui_state.is_offroad() and ui_state.has_longitudinal_control and ui_state.params.get_bool("TeslaApHybrid")
    )
    self._update_dynamic_speed_visibility()

    has_vehicle_bus = ui_state.CP_SP is not None and bool(ui_state.CP_SP.flags & TeslaFlagsSP.HAS_VEHICLE_BUS)
    self.mads_screen_button.set_visible(has_vehicle_bus)
    self.test_left_turn_signal.set_visible(has_vehicle_bus)
    self.test_right_turn_signal.set_visible(has_vehicle_bus)
    self.test_speed_increase.set_visible(has_vehicle_bus)
    self.test_speed_decrease.set_visible(has_vehicle_bus)
    self.auto_speed_limit.set_visible(has_vehicle_bus)

    mads_screen_button_desc = tr("Use a multi-finger press on the infotainment display as a MADS button.\n" +
                                 "This allows the use of full MADS functionality when enabled.\n" +
                                 "<b>Note: Setting this to Off may reset your MADS settings to default.</b>")
    mads_screen_button_desc += "<br><br>" + tr("Dynamic Auto Stock ACC uses 4 Finger for stock ACC switching. " +
                                               "Use 3 Finger or 5 Finger for the MADS button when Dynamic Auto Stock ACC is enabled.")
    if not ui_state.is_offroad():
      mads_screen_button_disabled_msg = tr("Enable \"Always Offroad\" in Device panel, or turn vehicle off to change.")
      mads_screen_button_desc = f"<b>{mads_screen_button_disabled_msg}</b><br><br>{mads_screen_button_desc}"
    self.mads_screen_button.set_description(mads_screen_button_desc)
    self.mads_screen_button.action_item.set_enabled(ui_state.is_offroad())

    self.stop_line_deceleration.action_item.set_enabled(ui_state.has_longitudinal_control)
    self.speed_button_validation.action_item.set_enabled(True)
    self.auto_speed_limit.action_item.set_enabled(ui_state.is_offroad() and ui_state.has_longitudinal_control)
    self.test_speed_increase.action_item.set_enabled(self._speed_button_test_enabled())
    self.test_speed_decrease.action_item.set_enabled(self._speed_button_test_enabled())
    self.test_left_turn_signal.action_item.set_enabled(self._turn_signal_test_enabled())
    self.test_right_turn_signal.action_item.set_enabled(self._turn_signal_test_enabled())
    self.mpc_settings.action_item.set_enabled(ui_state.is_offroad())

    if self._turn_signal_test_result is not None:
      message = self._turn_signal_test_result
      self._turn_signal_test_result = None
      gui_app.push_widget(alert_dialog(message))

    if self._speed_button_test_result is not None:
      message = self._speed_button_test_result
      self._speed_button_test_result = None
      gui_app.push_widget(alert_dialog(message))

    self._on_dyn_auto_stock_toggle(self.dynamic_auto_stock_toggle.action_item.get_state())
