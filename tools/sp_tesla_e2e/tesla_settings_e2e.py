#!/usr/bin/env python3
"""Actual native Tesla settings callbacks with isolated persisted Params; no device."""
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch
import uuid

os.environ['OPENPILOT_PREFIX'] = 'tesla-settings-' + uuid.uuid4().hex[:8]
os.environ['BIG'] = '0'
from openpilot.common.prefix import OpenpilotPrefix


def main():
  out = Path('artifacts/tesla-implementation-20261005/settings.json')
  out.parent.mkdir(parents=True, exist_ok=True)
  results = []
  with OpenpilotPrefix(prefix=os.environ['OPENPILOT_PREFIX']):
    from openpilot.selfdrive.ui.ui_state import ui_state
    from openpilot.selfdrive.ui.sunnypilot.mici.layouts.tesla import TeslaSettingsMici, CHOICES
    from openpilot.selfdrive.ui.sunnypilot.layouts.settings.vehicle.brands.tesla import TeslaSettings
    from openpilot.selfdrive.ui.sunnypilot.layouts.settings.vehicle.brands.tesla_control import TeslaControlSettingsLayout
    from openpilot.selfdrive.ui.sunnypilot.layouts.settings.vehicle.brands.tesla_planner import TeslaPlannerSettingsLayout
    from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_backends.registry import ordered_backends
    from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_backends.tuning import DEFAULT_VALUES, backend_values
    from openpilot.system.ui.lib.application import gui_app
    from openpilot.system.ui.lib.multilang import multilang
    ui_state.started = False
    ui_state.params.put_bool('IsOffroad', True, block=True)
    multilang.change_language('zh-CHS')
    gui_app.init_window('Tesla settings E2E', fps=20)
    try:
      with patch.object(gui_app, 'push_widget') as pushed, patch.object(gui_app, 'pop_widget'):
        mici = TeslaSettingsMici()
        for key, value, label in [('TeslaARS408Radar', 1, 'ARS408'), ('DynamicAutoStockSpeedLowKph', 115, '115 km/h'),
                                  ('TeslaBlindspotAmbientBrightness', 60, '60%'), ('TeslaTrafficStopReference', 55, '5.5 m')]:
          mici._choose_param(key, CHOICES[key])
          page = pushed.call_args.args[0]
          index = next(i for i, (_, choice) in enumerate(CHOICES[key]) if choice == value)
          page._scroller._items[index + 1]._click_callback()
          assert ui_state.params.get(key) == value
          assert mici.choice_buttons[key].value == label
          results.append({'case': 'choice-' + key, 'value': value, 'label': label})
        control = TeslaControlSettingsLayout(lambda: None)
        brand = TeslaSettings()
        for item, minimum, maximum, step in [(control.speed_high, 40, 120, 5), (control.speed_low, 20, 115, 5),
                                            (brand.control_profile.traffic_control_max_speed, 20, 120, 5),
                                            (brand.blindspot_ambient_brightness, 0, 100, 1)]:
          action = item.action_item
          assert (action.min_value, action.max_value, action.value_change_step) == (minimum, maximum, step)
        assert all('Validation' not in key for key, _ in mici.toggles)
        assert not hasattr(control, 'turn_signal_validation') and not hasattr(control, 'speed_button_validation')
        results.append({'case': 'shared-ranges-and-retired-controls'})
        for invalid in ({'schemaVersion': 999, 'backends': {}}, {'schemaVersion': 1, 'shared': {}, 'backends': {'unexpected': {}}},
                        {'schemaVersion': 1, 'revision': 3, 'shared': {'following.time.standard_s': 1.55},
                         'backends': {'official': {'profile': 2, 'values': dict(DEFAULT_VALUES), 'customValues': dict(DEFAULT_VALUES)}}}):
          ui_state.params.put('LongitudinalTuningConfig', invalid, block=True)
          for backend in ordered_backends():
            mici._tuning_page(backend)
            assert mici.tuning_error
            page = pushed.call_args.args[0]
            assert not any(button.enabled for button in page._scroller._items[1:])
            mici._value_page(backend, 'comfort_brake')
            value_page = pushed.call_args.args[0]
            assert not any(button.enabled for button in value_page._scroller._items[1:])
            for profile in (0, 1, 2):
              mici._apply_profile(backend, profile)
              value_page._scroller._items[-1]._click_callback()
              assert ui_state.params.get('LongitudinalTuningConfig') == invalid
            ui_state.params.put('LongitudinalPlannerMode', int(backend.id), block=True)
            c3 = TeslaPlannerSettingsLayout(lambda: None)
            assert c3.tuning_error and not c3.profile.action_item.enabled
            assert c3.status.title == "配置无效，原值已保留"
            assert c3.status.is_visible and c3.status.description_visible
            assert c3.status.action_item is None
            assert all(not option.action_item.enabled and not option.is_visible for option in c3.options)
            for profile in (0, 1, 2):
              c3._on_profile_changed(profile)
              c3._on_tuning_changed(300)
              assert ui_state.params.get('LongitudinalTuningConfig') == invalid
            results.append({'case': 'invalid-config-preserved', 'version': invalid['schemaVersion'], 'backend': backend.slug})
        ui_state.params.remove('LongitudinalTuningConfig')
        for backend in ordered_backends():
          mici._apply_profile(backend, 2)
          values = backend_values(ui_state.params, backend).as_dict()
          mici._value_page(backend, 'comfort_brake')
          page = pushed.call_args.args[0]
          next(button for button in page._scroller._items if button.get_text().startswith('+'))._click_callback()
          assert backend_values(ui_state.params, backend).comfort_brake > values['comfort_brake']
          ui_state.params.put('LongitudinalPlannerMode', int(backend.id), block=True)
          c3 = TeslaPlannerSettingsLayout(lambda: None)
          c3._on_profile_changed(2)
          assert not c3.tuning_error and c3.profile.action_item.enabled
          assert all(option.is_visible for option in c3.options)
          if backend.tuning_notice:
            assert backend.tuning_notice in c3.status_description
            assert c3.status.title == "Official部分参数为近似调节"
            assert c3.status.is_visible and c3.status.description_visible
          else:
            assert not c3.status.is_visible
          for field, option in zip(("stop_distance", "comfort_brake", "lead_danger_factor", "t_follow_relaxed",
                                    "t_follow_standard", "t_follow_aggressive", "x_ego_obstacle_cost", "j_ego_cost",
                                    "jerk_factor_relaxed", "a_change_cost", "danger_zone_cost"), c3.options, strict=True):
            assert ("近似" in option.title) == (field in backend.approximate_tuning_fields)
          action = next(option.action_item for option in c3.options if option.action_item.param_key == 'MpcComfortBrake')
          before = backend_values(ui_state.params, backend).comfort_brake
          action.set_value(round(before * 100) + action.value_change_step)
          assert backend_values(ui_state.params, backend).comfort_brake > before
          mici._tuning_page(backend)
          page = pushed.call_args.args[0]
          page._scroller._items[3]._click_callback()  # CrazyMax preset through native button
          current = backend_values(ui_state.params, backend).comfort_brake
          shown = next(button.value for button in page._scroller._items if button.get_text().startswith('舒适制动'))
          assert shown == f'{current:.2f} m/s²'
          results.append({'case': 'valid-three-backend-native-write', 'backend': backend.slug})
        saved = ui_state.params.get('LongitudinalPlannerMode')
        ui_state.started = True
        mici._set_param('LongitudinalPlannerMode', (saved + 1) % 3)
        c3._on_planner_changed((saved + 1) % 3)
        assert ui_state.params.get('LongitudinalPlannerMode') == saved
        results.append({'case': 'active-session-selection-held'})
    finally:
      gui_app.close()
  sources = [Path('openpilot/selfdrive/ui/sunnypilot/mici/layouts/tesla.py'),
             Path('openpilot/selfdrive/ui/sunnypilot/layouts/settings/vehicle/brands/tesla_planner.py'),
             Path('openpilot/selfdrive/ui/sunnypilot/tesla_settings.py'),
             Path('openpilot/selfdrive/ui/sunnypilot/layouts/settings/vehicle/brands/tesla.py'),
             Path('openpilot/selfdrive/ui/sunnypilot/layouts/settings/vehicle/brands/tesla_control.py'), Path(__file__)]
  out.write_text(json.dumps({'passed': True, 'scenarios': results,
                            'scope': 'native constructors/callbacks + isolated Params; window initialized, no device',
                            'gui_layout_acceptance': 'pending separate render proof',
                            'repeat_command': 'PYTHONPATH=. /Users/mile/Desktop/mo-op/.venv/bin/python tools/sp_tesla_e2e/tesla_settings_e2e.py',
                            'sha256': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}}, indent=2) + '\n')
  print(out)


if __name__ == '__main__':
  main()
