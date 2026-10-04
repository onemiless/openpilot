"""Native small-screen Tesla settings; control and tuning stay in shared modules."""
from openpilot.selfdrive.ui.mici.widgets.button import BigButton, BigToggle
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.widgets.scroller import NavScroller
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_backends.registry import ordered_backends
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_backends.tuning import (
  VALUE_SPECS, apply_backend_profile, backend_values, save_backend_values,
)

LABELS = {
 'TeslaCoopSteering': '协同转向', 'TeslaTouchLongitudinalSwitch': '四指切换纵向',
 'TeslaApHybrid': 'AP 混合控制', 'TeslaDynamicApLongitudinal': '动态 AP 控制',
 'DynamicAutoStock': '动态原车 ACC', 'DynamicAutoStockBlinkerToSP': '转向灯切回 SP 纵向',
 'DynamicAutoStockCurveToSP': '弯道切回 SP 纵向', 'TeslaTurnSignalValidation': '转向灯 CAN 验证',
 'TeslaSpeedButtonValidation': '速度按钮 CAN 验证', 'TeslaTrafficSignalControlEnabled': '交通灯控制',
 'TeslaBlindspotAmbientEnabled': '盲区氛围灯联动', 'AccelPersonalityEnabled': 'TN 加速风格',
 'TeslaARS408Radar': '雷达来源', 'TeslaMadsScreenButton': 'MADS 触屏手势',
 'AccelPersonality': 'TN 加速模式', 'DynamicAutoStockSpeedKph': '原车 ACC 切入速度',
 'DynamicAutoStockSpeedLowKph': '原车 ACC 退出速度', 'TeslaTrafficStopReference': '交通灯停车距离',
 'TeslaTrafficControlMaxSpeed': '交通灯控制最高速度',
 'TeslaBlindspotAmbientDayBrightness': '盲区灯白天亮度', 'TeslaBlindspotAmbientBrightness': '盲区灯夜间亮度',
 't_follow_relaxed': '舒适跟车时间', 't_follow_standard': '标准跟车时间', 't_follow_aggressive': '激进跟车时间',
 'x_ego_obstacle_cost': '障碍物权重', 'j_ego_cost': '加加速度权重', 'a_change_cost': '加速度变化权重',
 'danger_zone_cost': '危险区域权重', 'lead_danger_factor': '前车危险系数',
 'comfort_brake': '舒适制动', 'stop_distance': '停车距离', 'jerk_factor_relaxed': '舒适模式加加速度系数',
}

BOOL_KEYS = (
  'TeslaCoopSteering', 'TeslaTouchLongitudinalSwitch', 'TeslaApHybrid',
  'TeslaDynamicApLongitudinal', 'DynamicAutoStock', 'DynamicAutoStockBlinkerToSP',
  'DynamicAutoStockCurveToSP', 'TeslaTurnSignalValidation', 'TeslaSpeedButtonValidation',
  'TeslaTrafficSignalControlEnabled', 'TeslaBlindspotAmbientEnabled', 'AccelPersonalityEnabled',
)
CHOICES = {
  'TeslaARS408Radar': [('OEM', 0), ('ARS408', 1), ('关闭', 2)],
  'TeslaMadsScreenButton': [('关闭', 0), ('三指', 1), ('五指', 2)],
  'AccelPersonality': [('Eco', 0), ('Normal', 1), ('Sport', 2)],
  'DynamicAutoStockSpeedKph': [(str(x), x) for x in range(40, 121, 5)],
  'DynamicAutoStockSpeedLowKph': [(str(x), x) for x in range(20, 116, 5)],
  'TeslaTrafficStopReference': [(f'{x/10:.1f} m', x) for x in range(20, 121, 5)],
  'TeslaTrafficControlMaxSpeed': [(f'{x} km/h', x) for x in range(20, 121, 5)],
  'TeslaBlindspotAmbientDayBrightness': [(f'{x}%', x) for x in range(101)],
  'TeslaBlindspotAmbientBrightness': [(f'{x}%', x) for x in range(101)],
}


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
      button = BigButton(LABELS[key], str(ui_state.params.get(key, return_default=True)))
      button.set_click_callback(lambda k=key, c=choices: self._choose_param(k, c))
      button.set_enabled(ui_state.is_offroad)
      self._scroller.add_widget(button)
    mode = BigButton('纵向规划器')
    mode.set_click_callback(lambda: self._choose_param('LongitudinalPlannerMode', [(b.label, int(b.id)) for b in ordered_backends()]))
    mode.set_enabled(ui_state.is_offroad)
    self._scroller.add_widget(mode)
    for backend in ordered_backends():
      button = BigButton(f'{backend.label} 独立调节')
      button.set_click_callback(lambda b=backend: self._tuning_page(b))
      self._scroller.add_widget(button)

  def _set_param(self, key, value):
    if ui_state.is_offroad():
      ui_state.params.put(key, value, block=True)
    self.show_event()

  def _choose_param(self, key, choices):
    page = _page()
    for label, value in choices:
      button = BigButton(label)
      button.set_enabled(ui_state.is_offroad)
      button.set_click_callback(lambda v=value: (self._set_param(key, v), gui_app.pop_widget()))
      page._scroller.add_widget(button)
    gui_app.push_widget(page)

  def _tuning_page(self, backend):
    page = _page()
    for profile, label in enumerate(('Default', 'CrazyMax', 'Custom')):
      button = BigButton(label)
      button.set_click_callback(lambda p=profile: apply_backend_profile(ui_state.params, backend, p))
      page._scroller.add_widget(button)
    for key in VALUE_SPECS:
      button = BigButton(LABELS[key], f'{getattr(backend_values(ui_state.params, backend), key):.2f}')
      button.set_click_callback(lambda k=key: self._value_page(backend, k))
      page._scroller.add_widget(button)
    gui_app.push_widget(page)

  def _value_page(self, backend, key):
    page = _page()
    minimum, maximum, step, _ = VALUE_SPECS[key]
    value = BigButton(LABELS[key], f'{getattr(backend_values(ui_state.params, backend), key):.2f}')
    page._scroller.add_widget(value)
    def adjust(delta):
      values = backend_values(ui_state.params, backend).as_dict()
      values[key] = round(max(minimum, min(maximum, values[key] + delta)), 2)
      try:
        save_backend_values(ui_state.params, backend, values, 2)
      except ValueError:
        return  # Shared validation retains the previous following-time ordering.
      value.set_value(f'{values[key]:.2f}')
    for delta in (-step * 10, -step, step, step * 10):
      button = BigButton(f'{delta:+.2f}')
      button.set_click_callback(lambda d=delta: adjust(d))
      page._scroller.add_widget(button)
    gui_app.push_widget(page)

  def show_event(self):
    super().show_event()
    for key, toggle in self.toggles:
      toggle.set_checked(bool(ui_state.params.get(key, return_default=True)))
