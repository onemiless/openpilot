from collections.abc import Callable

import pyray as rl

from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_backends.registry import BackendId, ordered_backends
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_backends.tuning import (
  DEFAULT_VALUES, VALUE_SPECS, backend_profile,
)
from openpilot.sunnypilot.selfdrive.traffic_control import planner_session_is_active
from openpilot.selfdrive.ui.sunnypilot.tesla_settings import CHOICES, TITLES, TUNING_ITEMS, apply_tuning_profile, load_tuning, save_tuning, tuning_notice
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.sunnypilot.widgets.list_view import ListItemSP, multiple_button_item_sp, option_item_sp, toggle_item_sp
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.network import NavButton
from openpilot.system.ui.widgets.scroller_tici import Scroller


class TeslaPlannerSettingsLayout(Widget):
  """Old three-planner layout backed by the current shared solver adapter."""
  def __init__(self, back_btn_callback: Callable):
    super().__init__()
    self._back_button = NavButton(tr("Back"))
    self._back_button.set_click_callback(back_btn_callback)
    self.backends = ordered_backends()
    self._setting_values = False
    self.tuning_error = ""
    self.status_description = ""

    self.planner = multiple_button_item_sp(
      title=lambda: tr("Longitudinal Planner"),
      description=lambda: tr("Official remains the upstream default. Planner changes take effect next onroad session; tuning changes ramp in while driving."),
      buttons=[lambda label=backend.label: tr(label) for backend in self.backends],
      callback=self._on_planner_changed,
      inline=False,
    )
    self.profile = multiple_button_item_sp(
      title=lambda: tr("MPC Tuning Profile"),
      description=lambda: tr("Default preserves official values. CrazyMax is the retained fixed preset. Custom values are saved separately for each planner."),
      buttons=[lambda: tr("Default"), lambda: tr("CrazyMax"), lambda: tr("Custom")],
      param="MpcTuningProfile",
      callback=self._on_profile_changed,
      inline=False,
    )
    self.tn_accel_enabled = toggle_item_sp(
      title=tr(TITLES["AccelPersonalityEnabled"]), param="AccelPersonalityEnabled",
      description=tr("Enable TN's acceleration profile controller."),
    )
    self.tn_accel_profile = multiple_button_item_sp(
      title=lambda: tr(TITLES["AccelPersonality"]),
      description=lambda: tr("Choose Eco, Normal, or Sport acceleration limits for TN-NoDEC."),
      buttons=[lambda label=label: tr(label) for label, _ in CHOICES["AccelPersonality"]],
      param="AccelPersonality", inline=False,
    )

    self.options = []
    for field, param, title, unit in TUNING_ITEMS:
      minimum, maximum, step, _ = VALUE_SPECS[field]
      self.options.append(option_item_sp(
        title=tr(title), param=param,
        min_value=round(minimum * 100), max_value=round(maximum * 100), value_change_step=round(step * 100),
        description=tr("Adjust this MPC value for the selected planner. Changes are validated and applied gradually."),
        label_callback=lambda value, suffix=unit: f"{value / 100.0:.2f} {suffix}".strip(),
        on_value_changed=self._on_tuning_changed, enabled=lambda: True, inline=True,
      ))

    self.status = ListItemSP(description_visible=True)
    self.items = [self.status, self.planner, self.profile, self.tn_accel_enabled, self.tn_accel_profile, *self.options]
    self._scroller = Scroller(self.items, line_separator=True, spacing=0)
    self._load_selected_backend()

  def _backend_index(self) -> int:
    selected = int(ui_state.params.get("LongitudinalPlannerMode", return_default=True))
    return next((index for index, backend in enumerate(self.backends) if int(backend.id) == selected), 0)

  def _backend(self):
    return self.backends[self._backend_index()]

  def _show_values(self, values):
    self._setting_values = True
    try:
      by_param = {param: round(values.as_dict()[field] * 100) for field, param, _, _ in TUNING_ITEMS}
      for option in self.options:
        option.action_item.set_value(by_param[option.action_item.param_key])
    finally:
      self._setting_values = False

  def _load_selected_backend(self):
    backend = self._backend()
    values, self.tuning_error = load_tuning(ui_state.params, backend)
    self.planner.action_item.set_selected_button(self._backend_index())
    if values is not None:
      profile = backend_profile(ui_state.params, backend)
      ui_state.params.put("MpcTuningProfile", profile, block=True)
      self.profile.action_item.set_selected_button(profile)
      self._show_values(values)
    self._update_visibility()

  def _on_planner_changed(self, index: int):
    if not ui_state.is_offroad() or planner_session_is_active(ui_state.sm):
      return
    if 0 <= index < len(self.backends):
      ui_state.params.put("LongitudinalPlannerMode", int(self.backends[index].id), block=True)
      self._load_selected_backend()

  def _on_profile_changed(self, profile: int):
    values, self.tuning_error = apply_tuning_profile(ui_state.params, self._backend(), profile)
    if values is not None:
      ui_state.params.put("MpcTuningProfile", profile, block=True)
      self.profile.action_item.set_selected_button(profile)
      self._show_values(values)
    self._update_visibility()

  def _on_tuning_changed(self, _value):
    if self._setting_values or self.tuning_error or int(ui_state.params.get("MpcTuningProfile", return_default=True)) != 2:
      return
    values = dict(DEFAULT_VALUES)
    by_param = {option.action_item.param_key: option.action_item.get_value() / 100.0 for option in self.options}
    for field, param, _, _ in TUNING_ITEMS:
      values[field] = by_param[param]
    self.tuning_error = save_tuning(ui_state.params, self._backend(), values)
    if self.tuning_error:
      self._load_selected_backend()
    self._update_visibility()

  def _update_visibility(self):
    tn = self._backend().id == BackendId.TN_NO_DEC
    custom = not self.tuning_error and int(ui_state.params.get("MpcTuningProfile", return_default=True)) == 2
    self.profile.action_item.set_enabled(not self.tuning_error)
    self.status_description = self.tuning_error or tuning_notice(self._backend())
    self.status.set_title(tr("配置无效，原值已保留") if self.tuning_error else tr("Official部分参数为近似调节"))
    self.status.set_description(self.status_description)
    self.status.show_description(True)
    self.status.set_visible(bool(self.status_description))
    self.tn_accel_enabled.set_visible(tn)
    self.tn_accel_profile.set_visible(tn and ui_state.params.get_bool("AccelPersonalityEnabled"))
    for (field, _, title, _), option in zip(TUNING_ITEMS, self.options, strict=True):
      option.set_title(tr(title) + (tr("（近似）") if field in self._backend().approximate_tuning_fields else ""))
      option.set_visible(not self.tuning_error)
      option.action_item.set_enabled(custom)

  def _update_state(self):
    super()._update_state()
    self.planner.action_item.set_enabled(not planner_session_is_active(ui_state.sm))
    self._update_visibility()

  def _render(self, rect):
    self._back_button.set_position(self._rect.x, self._rect.y + 20)
    self._back_button.render()
    self._scroller.render(rl.Rectangle(rect.x, rect.y + self._back_button.rect.height + 40,
                                       rect.width, rect.height - self._back_button.rect.height - 40))

  def show_event(self):
    self._load_selected_backend()
    self._scroller.show_event()
