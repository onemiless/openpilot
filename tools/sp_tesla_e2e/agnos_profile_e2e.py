#!/usr/bin/env python3
"""Actual shell profile -> updater -> validated manifest, without partition IO."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

from openpilot.common.hardware.comma import agnos
from openpilot.sunnypilot.hardware.agnos import UnsafeBootChainManifest

ROOT = Path(__file__).resolve().parents[2]


def run(output):
  records = []

  def check(name, action):
    try:
      records.append({'scenario': name, 'passed': True, 'evidence': action()})
    except (AssertionError, subprocess.CalledProcessError, FileNotFoundError) as exc:
      records.append({'scenario': name, 'passed': False, 'error': repr(exc)})

  def shell(root, env):
    script = 'source ./launch_env.sh; printf "%s\\n%s\\n" "$AGNOS_VERSION" "$AGNOS_MANIFEST_FILE"'
    return subprocess.check_output(['bash', '-c', script], cwd=root, env=env, text=True).splitlines()

  with tempfile.TemporaryDirectory() as temp:
    directory = Path(temp)
    for value, expected in (('standard', '19.9'), ('c3xl', '19.9')):
      for inherited in ('', '19.7', '19.9') if value == 'c3xl' else ('', '19.9'):
        def selected(v=value, e=expected, i=inherited):
          env = {**os.environ, 'SUNNYPILOT_HARDWARE_PROFILE': v, 'AGNOS_VERSION': i}
          result = shell(ROOT, env)
          manifest = f'openpilot/common/hardware/comma/agnos{"-c3xl" if v == "c3xl" else ""}.json'
          assert result == [e, manifest], result
          with patch.dict(os.environ, {'SUNNYPILOT_HARDWARE_PROFILE': v}):
            agnos.load_agnos_manifest(str(ROOT / result[1]))
          return {'version': result[0], 'manifest': result[1], 'inherited_version': i}
        check(f'shell_{value}_inherited_{inherited or "unset"}', selected)

    def profile_file():
      physical = directory / 'hardware_profile'
      physical.write_text('c3xl\n')
      env = {**os.environ, 'SUNNYPILOT_HARDWARE_PROFILE': '', 'SUNNYPILOT_HARDWARE_PROFILE_FILE': str(physical), 'AGNOS_VERSION': ''}
      result = shell(ROOT, env)
      assert result == ['19.9', 'openpilot/common/hardware/comma/agnos-c3xl.json'], result
      return {'physical_profile_file': str(physical), 'version': result[0], 'manifest': result[1]}
    check('shell_persistent_profile_override', profile_file)

    def invalid_profile():
      env = {**os.environ, 'SUNNYPILOT_HARDWARE_PROFILE': 'c3xl-unknown', 'AGNOS_VERSION': ''}
      result = subprocess.run(['bash', '-c', 'source ./launch_env.sh; printf "%s" "$AGNOS_MANIFEST_FILE"'],
                              cwd=ROOT, env=env, text=True, capture_output=True)
      assert result.returncode != 0 and not result.stdout, 'invalid physical profile silently selected standard images'
      return {'returncode': result.returncode, 'stderr': result.stderr}
    check('invalid_profile_never_defaults_to_standard', invalid_profile)

    def invalid_profile_file(unreadable):
      physical = directory / 'invalid_hardware_profile'
      physical.write_text('c3xl' if unreadable else '')
      if unreadable:
        physical.chmod(0)
      env = {**os.environ, 'SUNNYPILOT_HARDWARE_PROFILE': '', 'SUNNYPILOT_HARDWARE_PROFILE_FILE': str(physical), 'AGNOS_VERSION': ''}
      try:
        result = subprocess.run(['bash', '-c', 'source ./launch_env.sh; printf "%s" "$AGNOS_MANIFEST_FILE"'],
                                cwd=ROOT, env=env, text=True, capture_output=True)
        assert result.returncode != 0 and not result.stdout, 'invalid profile file silently selected standard images'
        return {'returncode': result.returncode, 'stderr': result.stderr, 'unreadable': unreadable}
      finally:
        physical.chmod(0o600)
    check('empty_persistent_profile_rejected', lambda: invalid_profile_file(False))
    check('unreadable_persistent_profile_rejected', lambda: invalid_profile_file(True))

    def c3xl_system():
      with patch.dict(os.environ, {'SUNNYPILOT_HARDWARE_PROFILE': 'c3xl'}):
        parts = agnos.load_agnos_manifest(str(ROOT / 'openpilot/common/hardware/comma/agnos-c3xl.json'))
      stock = json.loads((ROOT / 'openpilot/common/hardware/comma/agnos.json').read_text())
      system = next(p for p in parts if p['name'] == 'system')
      assert system == next(p for p in stock if p['name'] == 'system'), 'C3XL must use the same official 19.9 system'
      return {'system_sha256': system['hash_raw'], 'boot_chain_guard_passed': True}
    check('c3xl_official_19_9_system_with_guarded_boot_chain', c3xl_system)

    try:
      from openpilot.system.updated import updated
    except SyntaxError as exc:
      records.append({'scenario': 'updater_import', 'passed': False, 'error': repr(exc)})
      updated = None

    if updated is not None:
      def upgrade(name, hardware_profile, current_version, manifest_relative, *, missing=False, corrupt=False):
        staged = directory / name
        staged.mkdir()
        shutil.copyfile(ROOT / 'launch_env.sh', staged / 'launch_env.sh')
        selected = staged / manifest_relative
        if not missing:
          selected.parent.mkdir(parents=True, exist_ok=True)
          source = ROOT / f'openpilot/common/hardware/comma/agnos{"-c3xl" if hardware_profile == "c3xl" else ""}.json'
          partitions = json.loads(source.read_text())
          if corrupt:
            next(p for p in partitions if p['name'] == 'boot')['hash'] = '0' * 64
          selected.write_text(json.dumps(partitions))
        if hardware_profile == 'c3xl':
          standard = staged / 'openpilot/common/hardware/comma/agnos.json'
          standard.parent.mkdir(parents=True, exist_ok=True)
          shutil.copyfile(ROOT / 'openpilot/common/hardware/comma/agnos.json', standard)
        flashed, consistent = [], []

        def validate_only(path, slot, _log):
          manifest = agnos.load_agnos_manifest(path)
          flashed.append({'manifest': str(Path(path).relative_to(staged)), 'slot': slot,
                          'partitions': len(manifest), 'sha256': hashlib.sha256(Path(path).read_bytes()).hexdigest()})

        with patch.dict(os.environ, {'SUNNYPILOT_HARDWARE_PROFILE': hardware_profile}), \
             patch.object(updated, 'OVERLAY_MERGED', str(staged)), \
             patch.object(updated.HARDWARE, 'get_os_version', return_value=current_version), \
             patch.object(updated, 'set_consistent_flag', side_effect=consistent.append), \
             patch.object(agnos, 'get_target_slot_number', return_value=1), \
             patch.object(agnos, 'flash_agnos_update', side_effect=validate_only):
          if missing:
            try:
              updated.handle_agnos_update()
            except FileNotFoundError:
              pass
            else:
              raise AssertionError('missing C3XL manifest must fail instead of using standard images')
          elif corrupt:
            try:
              updated.handle_agnos_update()
            except UnsafeBootChainManifest:
              pass
            else:
              raise AssertionError('modified C3XL boot chain was accepted')
          else:
            updated.handle_agnos_update()
        expected_version = '19.9'
        skip = current_version == expected_version
        assert len(flashed) == (0 if skip or missing or corrupt else 1), flashed
        if flashed:
          assert flashed[0]['manifest'] == manifest_relative, flashed
        if skip:
          assert not consistent, 'installed OS must not mutate update consistency'
        return {'profile': hardware_profile, 'installed': current_version, 'target': expected_version,
                'flashed_boundary': flashed, 'consistency_boundary': consistent, 'missing_rejected': missing,
                'unsafe_manifest_rejected': corrupt}

      for name, hardware_profile, current_version, manifest, missing, corrupt in (
        ('c3xl_already_installed', 'c3xl', '19.9', 'openpilot/common/hardware/comma/agnos-c3xl.json', False, False),
        ('standard_already_installed', 'standard', '19.9', 'openpilot/common/hardware/comma/agnos.json', False, False),
        ('c3xl_upgrade_from_19_7', 'c3xl', '19.7', 'openpilot/common/hardware/comma/agnos-c3xl.json', False, False),
        ('c3xl_upgrade_validated', 'c3xl', '18.4', 'openpilot/common/hardware/comma/agnos-c3xl.json', False, False),
        ('standard_upgrade_common', 'standard', '19.7', 'openpilot/common/hardware/comma/agnos.json', False, False),
        ('standard_upgrade_old_openpilot_system', 'standard', '19.7', 'openpilot/system/hardware/comma/agnos.json', False, False),
        ('standard_upgrade_pre_move', 'standard', '19.7', 'system/hardware/tici/agnos.json', False, False),
        ('c3xl_missing_manifest_no_standard_fallback', 'c3xl', '18.4', 'openpilot/common/hardware/comma/agnos-c3xl.json', True, False),
        ('c3xl_modified_boot_chain', 'c3xl', '18.4', 'openpilot/common/hardware/comma/agnos-c3xl.json', False, True),
      ):
        check(name, lambda n=name, p=hardware_profile, v=current_version, m=manifest, a=missing, b=corrupt:
              upgrade(n, p, v, m, missing=a, corrupt=b))

  paths = [ROOT / p for p in ('launch_env.sh', 'openpilot/system/updated/updated.py',
                             'openpilot/common/hardware/comma/agnos.json', 'openpilot/common/hardware/comma/agnos-c3xl.json')]
  result = {'passed': all(record['passed'] for record in records), 'scope': 'actual shell/updater/profile/manifest validation; physical IO boundaries stubbed',
            'source_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            'source_sha256': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}, 'cases': records}
  output.parent.mkdir(parents=True, exist_ok=True)
  output.write_text(json.dumps(result, indent=2) + '\n')
  print(json.dumps({'passed': result['passed'], 'cases': len(records), 'failed': [r['scenario'] for r in records if not r['passed']],
                    'output': str(output)}))
  return result['passed']


if __name__ == '__main__':
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--output', type=Path, required=True)
  raise SystemExit(not run(parser.parse_args().output))
