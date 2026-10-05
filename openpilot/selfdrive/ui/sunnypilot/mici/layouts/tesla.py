"""Native small-screen Tesla settings; metadata and tuning recovery are shared."""
from openpilot.selfdrive.ui.mici.widgets.button import BigButton, BigToggle
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.widgets.scroller import NavScroller
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_backends.registry import ordered_backends
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_backends.tuning import VALUE_SPECS
from openpilot.selfdrive.ui.sunnypilot.tesla_settings import (
  BOOL_KEYS, CHOICES, LABELS, TUNING_UNITS, apply_tuning_profile, load_tuning, save_tuning, setting_label, tuning_notice,
)
from openpilot.sunnypilot.selfdrive.traffic_control import planner_session_is_active


def _page() -> NavScroller:
  page = NavScroller()
  back = BigButton('返回')
  back.set_click_callback(gui_app.pop_widget)
  page._scroller.add_widget(back)
  return page


class TeslaSettingsMici(NavScroller):
  def __init__(self):
    super().__init__()
    self.toggles = []
    self.choice_buttons = {}
    self.tuning_error = ''
    back = BigButton('返回')
    back.set_click_callback(gui_app.pop_widget)
    self._scroller.add_widget(back)
    for key in BOOL_KEYS:
      toggle = BigToggle(LABELS[key], initial_state=bool(ui_state.params.get(key, return_default=True)),
                         toggle_callback=lambda value, k=key: self._set_param(k, value))
      toggle.set_enabled(ui_state.is_offroad)
      self.toggles.append((key, toggle))
      self._scroller.add_widget(toggle)
    for key, choices in CHOICES.items():
      button = BigButton(LABELS[key])
      button.set_click_callback(lambda k=key, c=choices: self._choose_param(k, c))
      button.set_enabled(ui_state.is_offroad)
      self.choice_buttons[key] = button
      self._scroller.add_widget(button)
    self.mode = BigButton('纵向规划器')
    self.mode.set_click_callback(lambda: self._choose_param('LongitudinalPlannerMode', [(b.label, int(b.id)) for b in ordered_backends()]))
    self.mode.set_enabled(lambda: ui_state.is_offroad() and not planner_session_is_active(ui_state.sm))
    self._scroller.add_widget(self.mode)
    for backend in ordered_backends():
      button = BigButton(f'{backend.label} 独立调节')
      button.set_click_callback(lambda b=backend: self._tuning_page(b))
      self._scroller.add_widget(button)
    self.show_event()

  def _set_param(self, key, value):
    if ui_state.is_offroad() and (key != 'LongitudinalPlannerMode' or not planner_session_is_active(ui_state.sm)):
      ui_state.params.put(key, value, block=True)
    self.show_event()

  def _choose_param(self, key, choices):
    page = _page()
    for label, value in choices:
      button = BigButton(tr(label))
      button.set_enabled(ui_state.is_offroad)
      button.set_click_callback(lambda v=value: (self._set_param(key, v), gui_app.pop_widget()))
      page._scroller.add_widget(button)
    gui_app.push_widget(page)

  def _apply_profile(self, backend, profile):
    _, self.tuning_error = apply_tuning_profile(ui_state.params, backend, profile)
    return not self.tuning_error

  def _tuning_page(self, backend):
    page = _page()
    values, self.tuning_error = load_tuning(ui_state.params, backend)
    notice = BigButton('调参状态', self.tuning_error or tuning_notice(backend) or '配置有效', scroll=True)
    notice.set_enabled(False)
    page._scroller.add_widget(notice)
    preset_buttons = []
    tuning_buttons = {}

    def refresh():
      current, self.tuning_error = load_tuning(ui_state.params, backend)
      notice.set_value(self.tuning_error or tuning_notice(backend) or '配置有效')
      for button in preset_buttons:
        button.set_enabled(current is not None)
      for field, button in tuning_buttons.items():
        button.set_enabled(current is not None)
        button.set_value(f'{getattr(current, field):.2f} {TUNING_UNITS[field]}'.strip() if current is not None else '不可用')

    def apply_profile(profile):
      self._apply_profile(backend, profile)
      refresh()

    for profile, label in enumerate(('Default', 'CrazyMax', 'Custom')):
      button = BigButton(label)
      button.set_enabled(values is not None)
      button.set_click_callback(lambda p=profile: apply_profile(p))
      preset_buttons.append(button)
      page._scroller.add_widget(button)
    for key in VALUE_SPECS:
      label = LABELS[key] + ('（近似）' if key in backend.approximate_tuning_fields else '')
      button = BigButton(label, f'{getattr(values, key):.2f} {TUNING_UNITS[key]}'.strip() if values is not None else '不可用')
      button.set_enabled(values is not None)
      button.set_click_callback(lambda k=key: self._value_page(backend, k, refresh))
      tuning_buttons[key] = button
      page._scroller.add_widget(button)
    gui_app.push_widget(page)

  def _value_page(self, backend, key, on_saved=None):
    page = _page()
    minimum, maximum, step, _ = VALUE_SPECS[key]
    values, self.tuning_error = load_tuning(ui_state.params, backend)
    status = BigButton('调参状态', self.tuning_error or tuning_notice(backend) or '配置有效', scroll=True)
    status.set_enabled(False)
    page._scroller.add_widget(status)
    value = BigButton(LABELS[key], f'{getattr(values, key):.2f} {TUNING_UNITS[key]}'.strip() if values is not None else '不可用')
    value.set_enabled(False)
    page._scroller.add_widget(value)

    def adjust(delta):
      current, self.tuning_error = load_tuning(ui_state.params, backend)
      if current is None:
        status.set_value(self.tuning_error)
        return
      updated = current.as_dict()
      updated[key] = round(max(minimum, min(maximum, updated[key] + delta)), 2)
      self.tuning_error = save_tuning(ui_state.params, backend, updated)
      status.set_value(self.tuning_error or tuning_notice(backend) or '配置有效')
      if not self.tuning_error:
        value.set_value(f'{updated[key]:.2f} {TUNING_UNITS[key]}'.strip())
        if on_saved:
          on_saved()

    for delta in (-step * 10, -step, step, step * 10):
      button = BigButton(f'{delta:+.2f}')
      button.set_enabled(values is not None)
      button.set_click_callback(lambda d=delta: adjust(d))
      page._scroller.add_widget(button)
    gui_app.push_widget(page)

  def show_event(self):
    super().show_event()
    for key, toggle in self.toggles:
      toggle.set_checked(bool(ui_state.params.get(key, return_default=True)))
    for key, button in self.choice_buttons.items():
      button.set_value(tr(setting_label(key, ui_state.params.get(key, return_default=True))))
    selected = ui_state.params.get('LongitudinalPlannerMode', return_default=True)
    self.mode.set_value(next((b.label for b in ordered_backends() if int(b.id) == selected), str(selected)))
