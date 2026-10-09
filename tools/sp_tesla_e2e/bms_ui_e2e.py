#!/usr/bin/env python3
"""Native BMS entry/render/back E2E with isolated Params and synthetic battery values."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
import traceback
from unittest.mock import patch

os.environ['BIG'] = '1'
os.environ['SCALE'] = '1'


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--output', type=Path, required=True)
  args = parser.parse_args()
  args.output = args.output.resolve()
  args.output.parent.mkdir(parents=True, exist_ok=True)
  result = {'scope': 'native BMS UI; synthetic battery values/CP; mocked passive CAN subscription; no device or CAN TX',
            'passed': False, 'failures': [], 'screenshots': {}, 'cases': []}
  from openpilot.common.prefix import OpenpilotPrefix
  with OpenpilotPrefix():
    import pyray as rl
    from opendbc.car import structs
    from openpilot.cereal import messaging
    from openpilot.selfdrive.ui.ui_state import ui_state
    from openpilot.selfdrive.ui.sunnypilot.layouts.settings.bms import BmsLayout
    from openpilot.selfdrive.ui.sunnypilot.layouts.settings.vehicle import VehicleLayout
    from openpilot.system.ui.lib.application import gui_app, FontWeight, FONT_SCALE
    from openpilot.system.ui.lib.multilang import multilang
    from openpilot.system.ui.lib.text_measure import measure_text_cached
    gui_app.init_window('BMS UI E2E', fps=20)
    try:
      gui_app._render_texture = rl.load_render_texture(2160, 1080)
      ui_state.started = False
      ui_state.params.put_bool('IsOffroad', True, block=True)
      cp = structs.CarParams.new_message()
      cp.brand, cp.carFingerprint = 'tesla', 'TESLA_MODEL_Y'
      ui_state.CP = cp
      parent = VehicleLayout()
      gui_app.push_widget(parent)
      parent._update_state()
      subscribed = []
      texts = []
      original_text = BmsLayout._text

      def subscribe(service, **kwargs):
        assert service == 'can' and kwargs.get('timeout') == 0
        sock = object()
        subscribed.append(sock)
        return sock

      def draw_text(text, x, y, size, color, bold=False):
        width = measure_text_cached(gui_app.font(FontWeight.BOLD if bold else FontWeight.NORMAL), text, size).x
        texts.append((text, x, y, width, size * FONT_SCALE))
        original_text(text, x, y, size, color, bold)

      with patch.object(messaging, 'sub_sock', side_effect=subscribe), \
           patch.object(messaging, 'recv_one_or_none', return_value=None), \
           patch.object(BmsLayout, '_text', side_effect=draw_text):
        parent._brand_settings.items[-1].callback()
        bms = gui_app._nav_stack[-1]
        assert isinstance(bms, BmsLayout) and bms.sock is subscribed[-1]
        result['cases'].append('actual Tesla entry opens supported BMS')
        renderer = gui_app.render()
        for language in ('en-US', 'zh-CHS'):
          multilang.change_language(language)
          for page in range(3):
            assert [tab._label._text for tab in bms.tabs] == ['Overview', 'Cells', 'Diagnostics']
            bms.tabs[page]._click_callback()
            now = time.monotonic()
            bms.state.values.update({k: (v, now) for k, v in {
              'soc': 80.3, 'soc_display': 80, 'voltage': 400.4, 'current': -12.2, 'power': -4.9,
              'temp_min': 22.1, 'temp_max': 24.5, 'cell_min': 3.941, 'cell_max': 3.948,
              'capacity': 76.3, 'remaining': 61.1, 'charged': 23456.7, 'discharged': 21234.5,
              'drive_power_low': 1, 'support_power_low': 1}.items()})
            bms.state._trip = (25., .1)
            bms._display = (float('-inf'), None, None)
            texts.clear()
            for _ in range(3):
              next(renderer)
            invalid = [t[0] for t in texts if not t[0].isascii()]
            if invalid:
              result['failures'].append({'case': 'English labels', 'language': language, 'page': page, 'labels': sorted(set(invalid))})
            overflow = [t[0] for t in texts if t[1] < 0 or t[1] + t[3] > 2160 or t[2] < 0 or t[2] + t[4] > 1080]
            if overflow:
              result['failures'].append({'case': 'canvas text bounds', 'page': page, 'labels': sorted(set(overflow))})
            if language == 'en-US':
              rl.rl_draw_render_batch_active()
              image = rl.load_image_from_texture(gui_app._render_texture.texture)
              screenshot = args.output.with_name(args.output.stem + f'-tab{page}.png')
              try:
                rl.image_flip_vertical(rl.ffi.addressof(image))
                assert rl.export_image(image, str(screenshot))
              finally:
                rl.unload_image(image)
              result['screenshots'][str(page)] = {'path': str(screenshot), 'sha256': hashlib.sha256(screenshot.read_bytes()).hexdigest()}
            # Same live widget at the former panel size, before the normal render loop restores the canvas.
            texts.clear()
            bms.render(rl.Rectangle(0, 0, 1560, 1030))
            overflow = [t[0] for t in texts if t[1] < 0 or t[1] + t[3] > 1560 or t[2] < 0 or t[2] + t[4] > 1030]
            if overflow:
              result['failures'].append({'case': 'panel text bounds', 'page': page, 'labels': sorted(set(overflow))})
        result['cases'].append('three tabs in en-US/zh-CHS; ASCII labels and bounds at 2160x1080 and 1560x1030')
        if not hasattr(bms, '_back_button'):
          result['failures'].append({'case': 'Back control missing'})
        else:
          assert bms._back_button.text == 'Back'
          bms._back_button._click_callback()
          assert gui_app._nav_stack[-1] is parent and len(gui_app._nav_stack) == 1
          assert bms.sock is None and not bms._visible and not bms.state.values
          result['cases'].append('Back restores parent and releases subscription/data')
          parent._brand_settings.items[-1].callback()
          assert gui_app._nav_stack[-1].sock is subscribed[-1] and len(subscribed) == 2
          gui_app._nav_stack[-1]._back_button._click_callback()
          ui_state.CP = None
          # Invoke the previously obtained entry to check unknown-car lifecycle.
          parent._brand_settings.items[-1].callback()
          assert gui_app._nav_stack[-1].sock is None and len(subscribed) == 2
          gui_app._nav_stack[-1]._back_button._click_callback()
          cp.brand, cp.carFingerprint = 'toyota', 'TOYOTA_COROLLA'
          ui_state.CP = cp
          parent._brand_settings.items[-1].callback()
          assert gui_app._nav_stack[-1].sock is None and len(subscribed) == 2
          gui_app._nav_stack[-1]._back_button._click_callback()
          result['cases'].append('reopen uses new subscription; unknown and Toyota cars remain unsubscribed')
        result['passed'] = not result['failures']
    except Exception:
      result['error'] = traceback.format_exc()
    finally:
      gui_app.close()
  result['source_sha256'] = hashlib.sha256((Path(__file__).resolve().parents[2] / 'openpilot/selfdrive/ui/sunnypilot/layouts/settings/bms.py').read_bytes()).hexdigest()
  args.output.write_text(json.dumps(result, indent=2) + '\n')
  print(json.dumps(result))
  return 0 if result['passed'] else 1


if __name__ == '__main__':
  raise SystemExit(main())
