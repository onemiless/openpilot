#!/usr/bin/env python3
"""LoggingEnabled toggle: real process_config/save_bootlog/params_keys.h -> which processes run. Plain python3, no openpilot env."""
import argparse
import ast
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KEY = 'LoggingEnabled'
LOGGING = {'loggerd', 'encoderd', 'logmessaged', 'proclogd', 'journald', 'tombstoned', 'uploader', 'sunnylink_uploader', 'statsd', 'statsd_sp'}
KEEP_ONROAD = {'camerad', 'stream_encoderd', 'deleter', 'ui', 'modeld', 'controlsd', 'selfdrived', 'card', 'pandad', 'qcomgpsd',
               'manage_athenad', 'hardwared', 'locationd', 'plannerd', 'radard'}
DEVELOPER = ROOT / 'openpilot/selfdrive/ui/sunnypilot/layouts/settings/developer.py'
FONT = 'openpilot/selfdrive/assets/fonts/NotoSansCJKsc-Regular.otf'
KEYS = {m[0]: (m[1], m[2], m[3]) for m in re.findall(r'\{"(\w+)",\s*\{([^,}]+),\s*(\w+)(?:,\s*"([^"]*)")?\}\}',
                                                      (ROOT / 'openpilot/common/params_keys.h').read_text())}


class Params:
  store: dict = {}

  def __init__(self, *a):
    pass

  def _k(self, k):
    if k not in KEYS:
      raise KeyError(f'UnknownKeyName {k}')
    return k

  def get_bool(self, k, block=False):
    return self.store.get(self._k(k)) == '1'

  def get(self, k, block=False, return_default=False):
    v = self.store.get(self._k(k), KEYS[k][2] if return_default else None)
    return None if v is None else (v == '1' if KEYS[k][1] == 'BOOL' else v)

  def put_bool(self, k, v, block=False):
    self.store[self._k(k)] = '1' if v else '0'

  def get_param_path(self):
    return PARAM_DIR


PARAM_DIR = tempfile.mkdtemp()


def stub(name, **attrs):
  mod = types.ModuleType(name)
  mod.__path__ = []
  mod.__dict__.update(attrs)
  sys.modules[name] = mod


class Proc:
  def __init__(self, name, _module, should_run=None, enabled=True, **_):
    self.name, self.should_run, self.enabled = name, should_run, enabled


class Native(Proc):
  def __init__(self, name, cwd, cmdline, should_run, enabled=True, **_):
    super().__init__(name, cwd, should_run, enabled)


class Daemon(Proc):
  def __init__(self, name, module, param_name, enabled=True):
    super().__init__(name, module, lambda *a: True, enabled)


def install_stubs():
  sys.path.insert(0, str(ROOT))
  runner = types.SimpleNamespace(stock='stock', tinygrad='tinygrad')
  for n in ('opendbc', 'opendbc.car'):
    stub(n)
  stub('opendbc.car.structs', car=types.SimpleNamespace(CarParams=object))
  stub('openpilot.cereal', custom=types.SimpleNamespace(ModelManagerSP=types.SimpleNamespace(Runner=runner)))
  stub('openpilot.common.params', Params=Params)
  stub('openpilot.common.hardware', PC=False, COMMA_HARDWARE=True)
  stub('openpilot.common.hardware.hw', Paths=types.SimpleNamespace(mapd_root=lambda: '/nonexistent/mapd'))
  stub('openpilot.system.manager.process', PythonProcess=Proc, NativeProcess=Native, DaemonProcess=Daemon)
  for n in ('openpilot.sunnypilot', 'openpilot.sunnypilot.mapd', 'openpilot.sunnypilot.models', 'openpilot.sunnypilot.hardware',
            'openpilot.sunnypilot.sunnylink'):
    stub(n)
  stub('openpilot.sunnypilot.mapd.mapd_manager', MAPD_PATH='/nonexistent/mapd')
  stub('openpilot.sunnypilot.models.helpers', get_active_model_runner=lambda params, offroad: 'stock')
  stub('openpilot.sunnypilot.hardware.driver_monitoring', driver_monitoring_enabled=lambda p: True)
  stub('openpilot.sunnypilot.hardware.profile', has_audio_output=lambda: True, has_microphone=lambda: True,
       HardwareProfile=types.SimpleNamespace(C3XL='c3xl'), get_hardware_profile=lambda: 'c3')
  stub('openpilot.sunnypilot.sunnylink.utils', sunnylink_need_register=lambda p: False, sunnylink_ready=lambda p: True,
       use_sunnylink_uploader=lambda p: True)


def load(name, source):
  spec = importlib.util.spec_from_loader(name, loader=None)
  mod = importlib.util.module_from_spec(spec)
  exec(compile(source, name, 'exec'), mod.__dict__)
  return mod


def running(pc, started, not_car=False):
  cp = types.SimpleNamespace(notCar=not_car)
  return sorted(p.name for p in pc.procs if p.enabled and p.should_run(started, Params(), cp))


def defaults(**over):
  Params.store = {k: v[2] for k, v in KEYS.items() if v[2] is not None}
  Params.store.update(IsLiveStreaming='1', EnableSunnylinkUploader='1')
  Params.store.update(over)


def bootlog_called(value):
  Params.store = {} if value is None else {KEY: value}
  calls = []
  real = subprocess.call
  subprocess.call = lambda *a, **k: calls.append(a[0]) or 0
  try:
    helpers = load('helpers_cur', (ROOT / 'openpilot/system/manager/helpers.py').read_text())
    helpers.save_bootlog()
    for t in threading.enumerate():
      if t is not threading.current_thread() and t.daemon:
        t.join(5)
  finally:
    subprocess.call = real
  return calls == ['./bootlog']


def ui_check():
  tree = ast.parse(DEVELOPER.read_text(encoding='utf-8'))
  call = next((n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, 'id', '') == 'toggle_item_sp'
               and any(k.arg == 'param' and getattr(k.value, 'value', None) == KEY for k in n.keywords)), None)
  if call is None:
    return {'toggle_present': False}
  text = ''.join(n.value for n in ast.walk(call) if isinstance(n, ast.Constant) and isinstance(n.value, str))
  font_commit = subprocess.check_output(['git', '-C', str(ROOT), 'log', '-1', '--format=%H', '--', FONT], text=True).strip()
  with tempfile.TemporaryDirectory() as d:
    subprocess.run(f'git -C {ROOT} archive {font_commit} openpilot/selfdrive/ui | tar -x -C {d}', shell=True, check=True)
    ui = Path(d) / 'openpilot/selfdrive/ui'
    glyphs = set((ui / 'translations/app_zh-CHS.po').read_text(encoding='utf-8'))
    for src in ui.rglob('*.py'):
      if 'tests' not in src.parts:
        glyphs.update(c for n in ast.walk(ast.parse(src.read_text(encoding='utf-8')))
                      if isinstance(n, ast.Constant) and isinstance(n.value, str) for c in n.value)
  missing = sorted({c for c in text if ord(c) > 127} - glyphs)
  return {'toggle_present': True, 'text': text, 'font_build_commit': font_commit, 'missing_glyphs': missing}


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--output', type=Path, required=True)
  args = parser.parse_args()
  install_stubs()
  os.chdir(ROOT / 'openpilot/system/manager')  # sunnylink_uploader existence check is cwd-relative, as on device
  head_src = subprocess.check_output(['git', '-C', str(ROOT), 'show', 'HEAD:openpilot/system/manager/process_config.py'], text=True)
  head = load('process_config_head', head_src)
  checks, scenarios = {}, {}
  checks['key_registered_persistent_bool_default_on'] = KEY in KEYS and 'PERSISTENT' in KEYS[KEY][0] and KEYS[KEY][1:] == ('BOOL', '1')
  try:
    cur = load('process_config_cur', (ROOT / 'openpilot/system/manager/process_config.py').read_text())
    for started in (False, True):
      tag = 'onroad' if started else 'offroad'
      defaults()
      base = running(head, started)
      on = running(cur, started)
      defaults(**{KEY: '0'})
      off = running(cur, started)
      scenarios[tag] = {'head': base, 'on': on, 'off': off, 'disabled': sorted(set(on) - set(off))}
      checks[f'{tag}_on_equals_head'] = on == base
      checks[f'{tag}_off_drops_only_logging'] = set(off) == set(on) - LOGGING
      checks[f'{tag}_off_runs_no_logging'] = not (set(off) & LOGGING)
    checks['onroad_on_runs_all_logging'] = LOGGING <= set(scenarios['onroad']['on'])
    checks['onroad_off_keeps_driving_ui_stream_deleter'] = KEEP_ONROAD <= set(scenarios['onroad']['off'])
    defaults(DisableLogging='1')
    checks['notcar_disablelogging_still_stops_loggerd'] = 'loggerd' not in running(cur, True, not_car=True)
  except Exception as e:  # baseline: key missing -> manager would crash the same way
    checks['process_config_evaluates'] = f'FAIL {type(e).__name__}: {e}'
  try:
    boot = {'unset': bootlog_called(None), 'on': bootlog_called('1'), 'off': bootlog_called('0')}
    checks['bootlog_gated'] = boot == {'unset': True, 'on': True, 'off': False}
  except Exception as e:
    boot = None
    checks['bootlog_gated'] = f'FAIL {type(e).__name__}: {e}'
  ui = ui_check()
  checks['ui_toggle_present_glyphs_in_font'] = ui['toggle_present'] and not ui['missing_glyphs']
  files = ['openpilot/common/params_keys.h', 'openpilot/system/manager/process_config.py', 'openpilot/system/manager/helpers.py',
           str(DEVELOPER.relative_to(ROOT))]
  passed = all(v is True for v in checks.values())
  artifact = {
    'source_commit': subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
    'sha256': {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in files},
    'checks': checks, 'scenarios': scenarios, 'bootlog': boot, 'ui': ui, 'passed': passed,
  }
  args.output.parent.mkdir(parents=True, exist_ok=True)
  args.output.write_text(json.dumps(artifact, indent=1, ensure_ascii=False))
  for k, v in checks.items():
    print(('PASS ' if v is True else 'FAIL ') + k + ('' if v in (True, False) else f' -> {v}'))
  print(('PASSED' if passed else 'FAILED') + f' artifact={args.output}')
  sys.exit(0 if passed else 1)


if __name__ == '__main__':
  main()
