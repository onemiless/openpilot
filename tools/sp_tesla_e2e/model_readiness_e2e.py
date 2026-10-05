#!/usr/bin/env python3
"""Temporary artifact -> actual Params/selector -> UI state + hardware alerts."""
import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from openpilot.common.params import Params
from openpilot.common.file_chunker import get_chunk_name, get_manifest_path, open_file_chunked
from openpilot.common.hardware.usb import CHESTNUT_USB_PRODUCT, CHESTNUT_USB_IDS
from openpilot.selfdrive.modeld import helpers as stock
from openpilot.sunnypilot.models import helpers as models
from openpilot.selfdrive.ui.ui_state import UIState
from openpilot.system.hardware.chestnut.status import ChestnutStatus

POINTER = b'version https://git-lfs.github.com/spec/v1\noid sha256:0000\n'


def run(output):
  subprocess.run([sys.executable, '-c',
                  'import sys; from openpilot.selfdrive.modeld.helpers import chestnut_compiled; '
                  + 'assert "openpilot.sunnypilot.models.helpers" not in sys.modules'], check=True)
  records = []
  with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    defaults = root / 'defaults'
    defaults.mkdir()
    selected = root / 'selected'
    selected.mkdir()
    params = Params(str(root / 'params'))
    drive = defaults / 'big_driving_tinygrad.pkl'
    warps = [defaults / f'big_driving_warp_{size}_tinygrad.pkl' for size in ('1344x760', '1928x1208')]
    for path in warps:
      path.write_bytes(b'compiled warp')
    bundle = {'internalName': 'fixture', 'ref': 'fixture', 'minimumSelectorVersion': models.REQUIRED_JSON_VERSION,
              'runner': 'tinygrad', 'models': [{'type': 'supercombo', 'artifact': {'fileName': 'fixture.pkl',
              'downloadUri': {'uri': 'https://example.invalid/fixture.pkl', 'sha256': 'abc'}}}]}
    ui = object.__new__(UIState)
    ui.params = params
    ui.started = False
    ui.chestnut_present = True
    ui.chestnut_active = None
    ui.chestnut_loading = False
    ui.sm = {'deviceState': SimpleNamespace(chestnutPresent=True)}
    ui.CP = None
    ui.CP_SP = None
    ui.has_longitudinal_control = False
    ui._sp_initialized = True
    ui.usb_connected = False
    usb = [{'vendorId': CHESTNUT_USB_IDS[0][0], 'productId': CHESTNUT_USB_IDS[0][1], 'product': CHESTNUT_USB_PRODUCT, 'speedMbps': 5000}]

    def check(name, default, ready):
      actual_default = stock.chestnut_compiled()
      actual = models.selected_chestnut_compiled(params)
      assert (actual_default, actual) == (default, ready), (name, actual_default, actual)
      ui.update_params()
      assert ui.chestnut_compiled == ready, (name, "UI runner override")
      ui._update_chestnut_state()
      assert ui.chestnut_state.value == ('ready' if ready else 'uncompiled'), (name, ui.chestnut_state)
      alerts = {}
      ChestnutStatus().update(True, 'dev-sp', usb, False, False, None, None,
                             lambda key, enabled, *args: alerts.update({key: enabled}))
      assert alerts['Offroad_ChestnutUncompiled'] == (not ready), (name, alerts)
      records.append({'scenario': name, 'default_compiled': actual_default, 'selected_compiled': actual,
                      'ui_state': ui.chestnut_state.value, 'uncompiled_alert': alerts['Offroad_ChestnutUncompiled']})

    with patch.object(stock, 'MODELS_DIR', defaults), patch.object(models.Paths, 'model_root', return_value=str(selected)), \
         patch.object(models, 'Params', return_value=params), patch('openpilot.system.hardware.chestnut.status.MODELS_DIR', defaults), \
         patch('openpilot.system.hardware.chestnut.status.get_build_metadata', return_value=SimpleNamespace(channel='dev-sp')), \
         patch('openpilot.selfdrive.ui.ui_state.read_int', return_value=0), \
         patch.object(models, '_compute_hash', side_effect=AssertionError('periodic readiness must not hash')):
      check('absent_default', False, False)
      drive.write_bytes(POINTER)
      check('lfs_default', False, False)
      drive.write_bytes(b'compiled default')
      check('no_selection_default', True, True)
      params.put('ModelManager_ActiveBundleChestnut', {'minimumSelectorVersion': 1}, block=True)
      check('stale_selection_default', True, True)
      params.put('ModelManager_ActiveBundleChestnut', bundle, block=True)
      check('missing_selected_no_default_fallback', True, False)
      path = selected / 'fixture.pkl'
      path.write_bytes(POINTER)
      check('selected_lfs', True, False)
      path.write_bytes(b'')
      check('selected_empty', True, False)
      path.write_bytes(b'compiled selected')
      check('selected_complete', True, True)
      path.unlink()
      check('deletion_after_ready', True, False)
      chunks = [Path(get_chunk_name(path, i, 2)) for i in range(2)]
      bundle['models'][0]['artifact']['chunks'] = [{'sha256': 'abc'}, {'sha256': 'def'}]
      params.put('ModelManager_ActiveBundleChestnut', bundle, block=True)
      for chunk in chunks:
        chunk.write_bytes(b'chunk data')
      manifest = Path(get_manifest_path(path))
      check('chunks_without_manifest', True, False)
      for count in ('bad', '0', '-1', '1', '3'):
        manifest.write_text(count)
        check(f'bad_selected_manifest_{count}', True, False)
      manifest.write_text('2')
      check('complete_selected_chunks', True, True)
      outside_chunk = root / 'outside-chunk'
      outside_chunk.write_bytes(b'chunk data')
      chunks[1].unlink()
      chunks[1].symlink_to(outside_chunk)
      check('chunk_symlink_escape', True, False)
      chunks[1].unlink()
      chunks[1].write_bytes(b'chunk data')
      path.write_bytes(b'compiled base')
      manifest.unlink()
      with open_file_chunked(path) as loaded:
        assert loaded.read() == b'compiled base'
      check('assembled_bundle_without_manifest', True, True)
      manifest.write_text('1')
      check('complete_file_precedes_mismatched_manifest', True, True)
      path.unlink()
      manifest.write_text('2')
      chunks[1].unlink()
      check('missing_selected_chunk', True, False)
      chunks[1].write_bytes(b'chunk data')
      path.write_bytes(POINTER)
      check('base_pointer_shadows_valid_chunks', True, False)
      path.unlink()
      warps[1].write_bytes(POINTER)
      check('warp_pointer', False, False)
      warps[1].write_bytes(b'compiled warp')
      params.put('ModelManager_ActiveBundleChestnut', {**bundle, 'models': []}, block=True)
      check('empty_bundle', True, False)
      incomplete = {**bundle, 'models': [{'type': 'supercombo', 'artifact': {'fileName': 'fixture.pkl'}}]}
      params.put('ModelManager_ActiveBundleChestnut', incomplete, block=True)
      check('artifact_without_hash', True, False)
      missing_hash = json.loads(json.dumps(bundle))
      missing_hash['models'][0]['artifact']['chunks'][1]['sha256'] = ''
      params.put('ModelManager_ActiveBundleChestnut', missing_hash, block=True)
      check('chunk_without_hash', True, False)
      outside = root / 'outside.pkl'
      outside.write_bytes(b'compiled outside')
      for name in ('../outside.pkl', str(outside)):
        unsafe = json.loads(json.dumps(incomplete))
        unsafe['models'][0]['artifact']['fileName'] = name
        unsafe['models'][0]['artifact']['downloadUri'] = {'sha256': 'abc'}
        params.put('ModelManager_ActiveBundleChestnut', unsafe, block=True)
        check('artifact_path_escape_' + ('absolute' if Path(name).is_absolute() else 'relative'), True, False)
      (selected / 'escape.pkl').symlink_to(outside)
      unsafe['models'][0]['artifact']['fileName'] = 'escape.pkl'
      params.put('ModelManager_ActiveBundleChestnut', unsafe, block=True)
      check('artifact_symlink_escape', True, False)
      params.remove('ModelManager_ActiveBundleChestnut')
      params.put('ModelManager_ActiveBundle', bundle, block=True)
      check('qcom_slot_is_independent', True, True)
      drive.unlink()
      default_manifest = Path(get_manifest_path(drive))
      default_manifest.write_text('2')
      default_chunks = [Path(get_chunk_name(drive, i, 2)) for i in range(2)]
      default_chunks[0].write_bytes(b'compiled chunk')
      check('default_manifest_incomplete', False, False)
      default_chunks[1].write_bytes(b'compiled chunk')
      check('default_manifest_complete', True, True)
      default_manifest.write_text('1000000000')
      with patch.object(stock, '_compiled_file', wraps=stock._compiled_file) as probe:
        check('default_manifest_oversized', False, False)
        assert probe.call_count == 0, 'oversized manifests must be rejected before chunk probes'
      default_manifest.write_text('nonsense')
      check('default_manifest_malformed', False, False)
    with patch.object(models.Paths, 'model_root', return_value=str(selected)), patch.object(models, 'chestnut_present', return_value=True):
      activation = json.loads(json.dumps(bundle))
      artifact = activation['models'][0]['artifact']
      artifact['fileName'] = 'activation.pkl'
      payloads = [b'activation one', b'activation two']
      artifact['downloadUri']['sha256'] = hashlib.sha256(b''.join(payloads)).hexdigest()
      artifact['chunks'] = [{'sha256': hashlib.sha256(payload).hexdigest()} for payload in payloads]
      base = selected / artifact['fileName']
      manifest = Path(get_manifest_path(base))
      chunks = [Path(get_chunk_name(base, i, 2)) for i in range(2)]

      def activate(name, kept, catalog_hash=None):
        activation['ref'] = name  # Force the existing once-per-selection validation cache to inspect each fixture.
        params.put('ModelManager_ActiveBundleChestnut', activation, block=True)
        current = models.get_selected_bundle(params, 'chestnut')
        if catalog_hash is not None:
          catalog = json.loads(json.dumps(activation))
          catalog['models'][0]['artifact']['downloadUri']['sha256'] = catalog_hash
          current = models.ModelManager.ModelBundle(**catalog)
        models.validate_active_bundles(params, {'chestnut': [current]})
        retained = params.get('ModelManager_ActiveBundleChestnut') is not None
        assert retained == kept, (name, retained)
        records.append({'scenario': name, 'activation_retained': retained, 'actual_activation_flow': True})

      base.write_bytes(b''.join(payloads))
      activate('activation_assembled_only', True)
      activate('activation_catalog_aggregate_sha_changed', False, catalog_hash='0' * 64)
      for chunk, payload in zip(chunks, payloads, strict=True):
        chunk.write_bytes(payload)
      manifest.write_text('2')
      base.write_bytes(b'corrupt shadow base')
      activate('activation_corrupt_base_shadows_correct_chunks', False)
      base.write_bytes(POINTER)
      activate('activation_pointer_shadows_correct_chunks', False)
      base.unlink()
      activate('activation_complete_chunks', True)
      manifest.unlink()
      activate('activation_missing_manifest', False)
      manifest.write_text('1')
      activate('activation_wrong_manifest_count', False)
      manifest.write_text('2')
      chunks[1].write_bytes(b'corrupt chunk')
      activate('activation_corrupt_chunk', False)
      chunks[1].unlink()
      outside = root / 'activation-outside'
      outside.write_bytes(payloads[1])
      chunks[1].symlink_to(outside)
      activate('activation_chunk_symlink_escape', False)
      chunks[1].unlink()
      chunks[1].write_bytes(payloads[1])
      manifest.unlink()
      outside_manifest = root / 'activation-manifest-outside'
      outside_manifest.write_text('2')
      manifest.symlink_to(outside_manifest)
      activate('activation_manifest_symlink_escape', False)
  result = {'passed': True, 'scope': 'local artifact/Params/UI state/hardware alert integration; no physical inference',
            'stock_import_independent': True, 'periodic_hashing': False, 'cases': records}
  output.parent.mkdir(parents=True, exist_ok=True)
  output.write_text(json.dumps(result, indent=2) + '\n')
  print(output)


if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument('--output', type=Path, required=True)
  run(parser.parse_args().output)
