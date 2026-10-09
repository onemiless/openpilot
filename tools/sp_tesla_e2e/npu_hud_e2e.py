#!/usr/bin/env python3
"""Native full C3 HUD pixel E2E with synthetic model selection, no device/CAN actions."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import traceback

os.environ['BIG'] = '1'
os.environ['SCALE'] = '1'
os.environ['SUNNYPILOT_UI'] = '1'
from openpilot.common.basedir import BASEDIR
ROOT = Path(BASEDIR)


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--output', type=Path, required=True)
  args = parser.parse_args()
  args.output = args.output.resolve()
  args.output.parent.mkdir(parents=True, exist_ok=True)
  report = {'passed': False, 'platform': platform.platform(), 'scope': 'full native C3 HudRendererSP; synthetic SubMaster fields; pixel proof, no phone or vehicle', 'cases': []}
  from openpilot.common.prefix import OpenpilotPrefix
  with OpenpilotPrefix():
    import pyray as rl
    from openpilot.cereal import messaging
    from openpilot.selfdrive.ui.ui_state import ui_state
    from openpilot.selfdrive.ui.sunnypilot.onroad.hud_renderer import HudRendererSP
    from openpilot.selfdrive.ui.sunnypilot.onroad.alert_renderer import AlertRendererSP
    from openpilot.selfdrive.ui.sunnypilot.onroad.developer_ui import DeveloperUiState, get_bottom_dev_ui_offset
    from openpilot.system.ui.lib.application import gui_app
    gui_app.init_window('NPU HUD E2E', fps=20)
    target = rl.load_render_texture(2160, 1080)
    try:
      ui_state.update_params()
      sm = ui_state.sm
      for name in sm.data:
        sm.recv_frame[name] = 20
        sm.alive[name] = sm.valid[name] = sm.updated[name] = True
      ui_state.started_frame = 10
      sm.data['carState'] = messaging.new_message('carState').carState
      sm.data['selfdriveState'] = messaging.new_message('selfdriveState').selfdriveState
      sm.data['modelV2'] = messaging.new_message('modelV2').modelV2
      ui_state.rocket_fuel = False
      ui_state.torque_bar = False
      hud, alerts = HudRendererSP(), AlertRendererSP()
      cases = [
        ('local_before', {}, 'grey'),
        ('phone', {'big': True}, 'green'),
        ('local_after', {}, 'grey'),
        ('invalid', {'big': True, 'valid': False}, 'grey'),
        ('stale', {'big': True, 'alive': False}, 'grey'),
        ('previous_trip', {'big': True, 'recv_frame': 9}, 'grey'),
        ('no_data', {'big': True, 'alive': False, 'valid': False, 'recv_frame': 0}, 'grey'),
        ('switch_off', {'big': True, 'enabled': False}, 'grey'),
        ('offroad', {'big': True, 'started': False}, 'hidden'),
        ('bottom_developer', {'big': True, 'developer': DeveloperUiState.BOTTOM}, 'green'),
        ('both_developer', {'big': True, 'developer': DeveloperUiState.BOTH}, 'green'),
        ('shifted_rect', {'big': True, 'rect': (40, 30, 2060, 980)}, 'green'),
        ('critical_alert', {'big': True, 'alert': True}, 'covered'),
      ]
      for name, config, expected in cases:
        ui_state.started = config.get('started', True)
        ui_state.bigmodel_enabled = config.get('enabled', True)
        ui_state.developer_ui = config.get('developer', DeveloperUiState.OFF)
        sm.alive['modelV2'] = config.get('alive', True)
        sm.valid['modelV2'] = config.get('valid', True)
        sm.recv_frame['modelV2'] = config.get('recv_frame', 20)
        sm['modelV2'].big = config.get('big', False)
        rect = rl.Rectangle(*config.get('rect', (0, 0, 2160, 1080)))
        rl.begin_texture_mode(target)
        rl.clear_background(rl.BLACK)
        hud.render(rect)
        if config.get('alert'):
          ss = sm['selfdriveState']
          ss.alertSize, ss.alertStatus, ss.alertText1 = 'full', 'critical', 'TAKE CONTROL'
          alerts.render(rect)
        rl.rl_draw_render_batch_active()
        rl.end_texture_mode()
        image = rl.load_image_from_texture(target.texture)
        screenshot = args.output.with_name(args.output.stem + '-' + name + '.png')
        try:
          rl.image_flip_vertical(rl.ffi.addressof(image))
          x, y = int(rect.x + 30), int(rect.y + rect.height - 106 - 60 - get_bottom_dev_ui_offset())
          pixels = {'green': 0, 'grey': 0, 'red': 0}
          for yy in range(y, y + 106):
            for xx in range(x, x + 144):
              color = rl.get_image_color(image, xx, yy)
              rgb = (color.r, color.g, color.b)
              pixels['green'] += rgb == (128, 216, 166)
              pixels['grey'] += rgb == (166, 166, 166)
              pixels['red'] += color.r > color.g * 2 and color.r > color.b * 2
          passed = pixels[expected] > 2000 if expected in ('green', 'grey') else pixels['green'] == pixels['grey'] == 0
          if expected == 'green':
            passed &= pixels['grey'] == 0
          if expected == 'grey':
            passed &= pixels['green'] == 0
          if expected == 'covered':
            passed &= pixels['red'] > 2000
          assert rl.export_image(image, str(screenshot))
          report['cases'].append({'case': name, 'expected': expected, 'passed': bool(passed), 'pixels': pixels,
                                  'icon_rect': [x, y, 144, 106], 'screenshot': str(screenshot),
                                  'sha256': hashlib.sha256(screenshot.read_bytes()).hexdigest()})
        finally:
          rl.unload_image(image)
      mici = 'openpilot/selfdrive/ui/sunnypilot/mici/onroad/hud_renderer.py'
      report['c4_unchanged'] = subprocess.check_output(['git', 'show', 'HEAD:' + mici], cwd=ROOT) == (ROOT / mici).read_bytes()
      report['passed'] = all(c['passed'] for c in report['cases']) and report['c4_unchanged']
    except Exception:
      report['error'] = traceback.format_exc()
    finally:
      rl.unload_render_texture(target)
      gui_app.close()
  path = ROOT / 'openpilot/selfdrive/ui/sunnypilot/onroad/hud_renderer.py'
  report['source_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
  args.output.write_text(json.dumps(report, indent=2) + '\n')
  print(json.dumps(report))
  return 0 if report['passed'] else 1


if __name__ == '__main__':
  raise SystemExit(main())
